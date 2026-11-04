"""A locally run app (AUTH_MODE=local, loopback HOST) answers only to loopback names.

A web page on another site can point its own name at 127.0.0.1 (DNS
rebinding); the browser then treats that page and the app as one site. Those
requests carry the other name in the Host header and are refused. Requests
that change something must also come from a page on a loopback address when
they carry an Origin header. All data is SYNTHETIC; Outlook is never started.
"""
from __future__ import annotations

import pytest

from backend.main import LocalOnlyMiddleware, _host_name, _origin_host_name
from backend.tests.test_api_support import (
    SYNTHETIC_PASSWORD,
    FakeRunner,
    make_client,
    make_outlook,
    make_settings,
)

REBIND_HOST = "SYNTHETIC-rebind.example:8000"
REBIND_ORIGIN = "http://SYNTHETIC-rebind.example:8000"
NOT_LOCAL = "This app only answers on this computer's own address. Open it at http://127.0.0.1:8000."
LOGIN = {"username": "admin", "password": SYNTHETIC_PASSWORD}


def _strict_client(settings=None, **kwargs):
    """A test app that accepts loopback names only (not the test client's "testserver")."""
    return make_client(settings, extra_local_hosts=(), base_url="http://127.0.0.1:8000", **kwargs)


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "127.0.0.1", "localhost:8000", "LOCALHOST:5173", "[::1]:8000", "[::1]"])
def test_loopback_names_are_served(host):
    client = _strict_client()
    response = client.get("/api/health", headers={"Host": host})
    assert response.status_code == 200 and response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "host",
    [
        REBIND_HOST,
        "SYNTHETIC-rebind.example",
        "127.0.0.1.SYNTHETIC-rebind.example",
        "localhost.SYNTHETIC-rebind.example:8000",
        "192.0.2.10:8000",
        "::1",                     # IPv6 without brackets is not a valid Host header
        "127.0.0.1:SYNTHETIC",
        "[::1]SYNTHETIC",
        "",
    ],
)
def test_other_names_are_refused(host):
    client = _strict_client()
    response = client.get("/api/health", headers={"Host": host})
    assert response.status_code == 403
    assert response.json() == {"detail": NOT_LOCAL}
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_rebinding_page_cannot_sign_in_or_open_outlook():
    runner = FakeRunner()
    client = _strict_client(
        make_settings(outlook_email="on"), outlook=make_outlook(runner, platform="win32")
    )
    headers = {"Host": REBIND_HOST, "Origin": REBIND_ORIGIN}
    assert client.post("/api/auth/login", json=LOGIN, headers=headers).status_code == 403
    assert client.get("/", headers={"Host": REBIND_HOST}).status_code == 403
    # Even with a session from the real address, the other name gets nothing.
    assert client.post("/api/auth/login", json=LOGIN).status_code == 200
    assert client.post("/api/report/email", json={"to": ""}, headers=headers).status_code == 403
    assert runner.calls == []


@pytest.mark.parametrize("method", ["post", "delete"])
def test_changes_from_a_page_on_another_origin_are_refused(method):
    client = _strict_client()
    assert client.post("/api/auth/login", json=LOGIN).status_code == 200
    kwargs = {"json": LOGIN} if method == "post" else {}
    path = "/api/auth/login" if method == "post" else "/api/workbook"
    for origin in (REBIND_ORIGIN, "null", "file://", "http://127.0.0.1.SYNTHETIC-rebind.example"):
        response = getattr(client, method)(path, headers={"Origin": origin}, **kwargs)
        assert response.status_code == 403, origin


@pytest.mark.parametrize(
    "origin", ["http://127.0.0.1:8000", "http://localhost:5173", "http://[::1]:8000", "https://localhost"]
)
def test_changes_from_a_local_page_are_allowed(origin):
    client = _strict_client()
    assert client.post("/api/auth/login", json=LOGIN, headers={"Origin": origin}).status_code == 200
    assert client.delete("/api/workbook", headers={"Origin": origin}).status_code == 204


def test_reading_with_a_foreign_origin_on_the_local_name_is_allowed():
    # Cross-site reads are already blocked by the browser (CORS); only the name matters here.
    client = _strict_client()
    assert client.get("/api/health", headers={"Origin": REBIND_ORIGIN}).status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"host": "0.0.0.0"},                    # shared on the network: reached by other names
        {"host": "192.0.2.10"},
        {"auth_mode": "databricks"},            # behind the Databricks proxy
    ],
)
def test_check_applies_only_when_the_app_runs_locally(overrides):
    client = _strict_client(make_settings(**overrides))
    assert client.get("/api/health", headers={"Host": REBIND_HOST}).status_code == 200
    assert not any(m.cls is LocalOnlyMiddleware for m in client.app.user_middleware)


def test_local_app_installs_the_check():
    client = _strict_client()
    assert any(m.cls is LocalOnlyMiddleware for m in client.app.user_middleware)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("127.0.0.1:8000", "127.0.0.1"),
        ("LocalHost", "localhost"),
        ("[::1]:8000", "::1"),
        ("[::1]", "::1"),
        ("::1", None),
        ("[::1", None),
        ("host:", None),
        ("host:80x", None),
    ],
)
def test_host_name(value, expected):
    assert _host_name(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("http://127.0.0.1:8000", "127.0.0.1"),
        ("https://LOCALHOST", "localhost"),
        ("http://[::1]:5173", "::1"),
        ("null", None),
        ("file://", None),
        ("ftp://localhost", None),
        ("http://localhost:SYNTHETIC", None),
    ],
)
def test_origin_host_name(value, expected):
    assert _origin_host_name(value) == expected
