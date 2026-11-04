"""Sign-in, cookies, sessions over HTTP and the Databricks auth mode."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.auth.service import (
    MSG_IDENTITY_MISSING,
    MSG_LOGIN_FAILED,
    MSG_LOGIN_NOT_USED,
    MSG_LOGIN_RATE_LIMITED,
    MSG_NOT_SIGNED_IN,
    LoginRateLimiter,
)
from backend.sessions.store import SessionStore
from backend.tests.test_api_sessions import FakeClock
from backend.tests.test_api_support import (
    SYNTHETIC_PASSWORD,
    FakeServices,
    cookie_headers,
    cookie_value,
    login,
    make_client,
    make_settings,
    upload,
)

PROTECTED_ENDPOINTS = [
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/workbook"),
    ("GET", "/api/report"),
    ("DELETE", "/api/workbook"),
    ("GET", "/api/report/pdf"),
    ("GET", "/api/report/pdf?download=1"),
    ("POST", "/api/report/email"),
]
# make_client's Outlook launcher reports a non-Windows platform.
NO_FEATURES = {"outlook_email": False}


def _session_cookie_header(response) -> str:
    headers = [h for h in cookie_headers(response) if h.startswith("fmea_session=")]
    assert len(headers) == 1, headers
    return headers[0]


def _flags(header: str) -> set[str]:
    return {part.strip().lower() for part in header.split(";")[1:]}


# --------------------------------------------------------------------------- #
# Local sign-in
# --------------------------------------------------------------------------- #
def test_login_success_sets_session_cookie():
    client = make_client()
    response = login(client)
    assert response.status_code == 200
    assert response.json() == {"user": {"name": "admin"}, "auth_mode": "local", "features": NO_FEATURES}

    header = _session_cookie_header(response)
    flags = _flags(header)
    assert "httponly" in flags
    assert "samesite=lax" in flags
    assert "path=/" in flags
    assert "secure" not in flags
    assert "SameSite=Lax" in header
    assert len(cookie_value(response)) >= 43

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"user": {"name": "admin"}, "auth_mode": "local", "features": NO_FEATURES}


def test_cookie_secure_flag_follows_setting():
    client = make_client(make_settings(cookie_secure=True), base_url="https://testserver")
    response = login(client)
    assert response.status_code == 200
    assert "secure" in _flags(_session_cookie_header(response))
    assert client.get("/api/auth/me").status_code == 200


def test_custom_cookie_name():
    client = make_client(make_settings(cookie_name="SYNTHETIC_cookie"))
    response = login(client)
    assert cookie_value(response, "SYNTHETIC_cookie")
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize(
    "username,password",
    [("admin", "wrong"), ("admin", ""), ("someone", SYNTHETIC_PASSWORD), ("", ""), ("admin", "x" * 5000)],
)
def test_login_failure(username, password):
    client = make_client()
    response = login(client, username, password)
    assert response.status_code == 401
    assert response.json() == {"detail": MSG_LOGIN_FAILED}
    assert cookie_value(response) is None
    assert client.get("/api/auth/me").status_code == 401


def test_login_username_surrounding_spaces_are_ignored():
    assert login(make_client(), " admin ").status_code == 200


def test_login_with_malformed_body_gets_plain_message():
    client = make_client()
    response = client.post("/api/auth/login", content=b"not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_login_rate_limited_after_five_failures():
    client = make_client()
    clock = FakeClock()
    client.app.state.login_limiter = LoginRateLimiter(clock=clock)

    for _ in range(5):
        assert login(client, "admin", "wrong").status_code == 401
    blocked = login(client, "admin", "wrong")
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": MSG_LOGIN_RATE_LIMITED}
    assert int(blocked.headers["Retry-After"]) > 0

    # Even the right password is refused while blocked.
    assert login(client, "admin", SYNTHETIC_PASSWORD).status_code == 429
    # The limit is per username: another username is still checked normally.
    assert login(client, "other", "wrong").status_code == 401

    clock.advance(5 * 60 + 1)
    assert login(client, "admin", SYNTHETIC_PASSWORD).status_code == 200


def test_successful_login_resets_failure_count():
    client = make_client()
    for _ in range(4):
        assert login(client, "admin", "wrong").status_code == 401
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, "admin", "wrong").status_code == 401
    assert login(client).status_code == 200


def test_login_replaces_existing_session():
    client = make_client()
    first = cookie_value(login(client))
    second = cookie_value(login(client))
    assert first and second and first != second
    assert len(client.app.state.sessions) == 1
    other = TestClient(client.app)
    other.cookies.set("fmea_session", first)
    assert other.get("/api/auth/me").status_code == 401


# --------------------------------------------------------------------------- #
# Protected endpoints
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_protected_endpoints_require_session(method, path):
    services = FakeServices()
    client = make_client(services=services)
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.json() == {"detail": MSG_NOT_SIGNED_IN}
    assert services.build_calls == [] and services.render_calls == 0


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_unknown_session_token_is_rejected_and_cookie_cleared(method, path):
    client = make_client()
    client.cookies.set("fmea_session", "SYNTHETIC-made-up-token")
    response = client.request(method, path)
    assert response.status_code == 401
    header = _session_cookie_header(response)
    assert "max-age=0" in _flags(header)


def test_upload_without_session_is_rejected_before_parsing():
    services = FakeServices()
    client = make_client(services=services)
    response = upload(client)
    assert response.status_code == 401
    assert services.build_calls == []


def test_logout_destroys_session_and_report():
    services = FakeServices()
    client = make_client(services=services)
    token = cookie_value(login(client))
    assert upload(client).status_code == 200
    session = client.app.state.sessions.get(token)
    assert session.report is not None

    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    assert "max-age=0" in _flags(_session_cookie_header(response))
    assert session.report is None and session.pdf_bytes is None
    assert len(client.app.state.sessions) == 0

    assert client.get("/api/auth/me").status_code == 401
    # Replaying the old token does not bring the session or report back.
    replay = TestClient(client.app)
    replay.cookies.set("fmea_session", token)
    assert replay.get("/api/report").status_code == 401


def test_session_idle_expiry_over_http():
    settings = make_settings(session_idle_minutes=15)
    client = make_client(settings)
    clock = FakeClock()
    client.app.state.sessions = SessionStore(15, 200, clock=clock)

    assert login(client).status_code == 200
    clock.advance(14 * 60)
    assert client.get("/api/auth/me").status_code == 200
    clock.advance(14 * 60)
    assert client.get("/api/auth/me").status_code == 200   # activity kept it alive
    clock.advance(15 * 60 + 1)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": MSG_NOT_SIGNED_IN}


def test_lru_eviction_over_http():
    client_a = make_client(make_settings(max_sessions=2))
    app = client_a.app
    clock = FakeClock()
    app.state.sessions = SessionStore(60, 2, clock=clock)
    client_b, client_c = TestClient(app), TestClient(app)

    assert login(client_a).status_code == 200
    clock.advance(1)
    assert login(client_b).status_code == 200
    clock.advance(1)
    assert client_a.get("/api/auth/me").status_code == 200   # a used more recently than b
    clock.advance(1)
    assert login(client_c).status_code == 200

    assert client_b.get("/api/auth/me").status_code == 401
    assert client_a.get("/api/auth/me").status_code == 200
    assert client_c.get("/api/auth/me").status_code == 200


# --------------------------------------------------------------------------- #
# Local mode never trusts forwarded identity headers
# --------------------------------------------------------------------------- #
def test_local_mode_ignores_forwarded_headers():
    client = make_client()
    spoofed = {
        "X-Forwarded-Email": "SYNTHETIC.person@example.com",
        "X-Forwarded-Preferred-Username": "SYNTHETIC.person",
        "X-Forwarded-User": "SYNTHETIC-user",
    }
    response = client.get("/api/auth/me", headers=spoofed)
    assert response.status_code == 401
    assert cookie_value(response) is None
    assert upload(client, headers=spoofed).status_code == 401

    assert login(client).status_code == 200
    me = client.get("/api/auth/me", headers=spoofed)
    assert me.json() == {"user": {"name": "admin"}, "auth_mode": "local", "features": NO_FEATURES}


# --------------------------------------------------------------------------- #
# Databricks mode
# --------------------------------------------------------------------------- #
EMAIL = "SYNTHETIC.engineer@example.com"


def _databricks_client(services=None) -> TestClient:
    return make_client(make_settings(auth_mode="databricks"), services=services)


def test_databricks_identity_from_email_header_creates_session():
    client = _databricks_client()
    response = client.get("/api/auth/me", headers={"X-Forwarded-Email": EMAIL})
    assert response.status_code == 200
    assert response.json() == {"user": {"name": EMAIL}, "auth_mode": "databricks", "features": NO_FEATURES}
    header = _session_cookie_header(response)
    assert {"httponly", "samesite=lax", "path=/"} <= _flags(header)
    assert len(client.app.state.sessions) == 1

    again = client.get("/api/auth/me", headers={"X-Forwarded-Email": EMAIL})
    assert again.status_code == 200
    assert cookie_value(again) is None               # existing session reused
    assert len(client.app.state.sessions) == 1


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({"X-Forwarded-Preferred-Username": "SYNTHETIC.pref"}, "SYNTHETIC.pref"),
        ({"X-Forwarded-User": "SYNTHETIC-user-id"}, "SYNTHETIC-user-id"),
        (
            {"X-Forwarded-Email": "  ", "X-Forwarded-User": "SYNTHETIC-user-id"},
            "SYNTHETIC-user-id",
        ),
        (
            {"X-Forwarded-Email": EMAIL, "X-Forwarded-User": "SYNTHETIC-user-id"},
            EMAIL,
        ),
    ],
)
def test_databricks_identity_fallback_headers(headers, expected):
    response = _databricks_client().get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["user"]["name"] == expected


def test_databricks_without_identity_is_unauthorised():
    client = _databricks_client()
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": MSG_IDENTITY_MISSING}
    assert len(client.app.state.sessions) == 0


def test_databricks_login_endpoint_is_not_used():
    client = _databricks_client()
    response = login(client)
    assert response.status_code == 400
    assert response.json() == {"detail": MSG_LOGIN_NOT_USED}


def test_databricks_session_keeps_report_and_is_per_user():
    services = FakeServices()
    client = _databricks_client(services)
    who = {"X-Forwarded-Email": EMAIL}
    first_upload = upload(client, headers=who)
    assert first_upload.status_code == 200
    assert cookie_value(first_upload)                # session created on first request
    assert client.get("/api/report", headers=who).status_code == 200
    assert client.get("/api/report/pdf", headers=who).status_code == 200

    # A different Databricks user in the same browser must not see that report.
    someone_else = {"X-Forwarded-Email": "SYNTHETIC.other@example.com"}
    response = client.get("/api/report", headers=someone_else)
    assert response.status_code == 404
    assert cookie_value(response)                    # new session issued
    assert client.get("/api/auth/me", headers=someone_else).json()["user"]["name"] == (
        "SYNTHETIC.other@example.com"
    )


def test_databricks_logout_ends_server_session():
    client = _databricks_client()
    who = {"X-Forwarded-Email": EMAIL}
    assert upload(client, headers=who).status_code == 200
    assert client.post("/api/auth/logout", headers=who).status_code == 204
    assert client.get("/api/report", headers=who).status_code == 404
