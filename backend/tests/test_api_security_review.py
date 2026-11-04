"""Security review of the API: each test pins down a defect found in review
(or a guard the review asked for). All data is SYNTHETIC."""
from __future__ import annotations

import email.message
import importlib.util
import json
import pathlib
import re
from pathlib import Path
from urllib.parse import unquote

import pytest
import uvicorn
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.auth.service import LoginRateLimiter, require_user
from backend.main import create_app
from backend.settings import PROJECT_ROOT
from backend.tests.test_api_app import SECRET_TEXT, _asgi_get, frontend  # noqa: F401 (fixture)
from backend.tests.test_api_sessions import FakeClock
from backend.tests.test_api_support import (
    SYNTHETIC_PASSWORD,
    TEST_CLIENT_HOSTS,
    FakeServices,
    fast_password_hash,
    login,
    make_client,
    make_report,
    make_settings,
    upload,
)

MB = 1024 * 1024
MSG_REQUEST_TOO_LARGE = "This request is too large to process."


# --------------------------------------------------------------------------- #
# Every API route except the public ones needs a signed-in user
# --------------------------------------------------------------------------- #
PUBLIC_API_ROUTES = {("/api/health", "GET"), ("/api/auth/login", "POST")}
CONTRACT_PROTECTED = {
    ("/api/auth/logout", "POST"),
    ("/api/auth/me", "GET"),
    ("/api/workbook", "POST"),
    ("/api/workbook", "DELETE"),
    ("/api/report", "GET"),
    ("/api/report/pdf", "GET"),
    ("/api/report/email", "POST"),
}


def _dependency_calls(dependant):
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from _dependency_calls(dependency)


def _all_api_routes(routes, prefix: str = "", inherited: tuple = ()):
    """Yield (full path, APIRoute, router-level dependency calls), including routers
    added with include_router (FastAPI 0.14x keeps those as nested router objects)."""
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            context = route.include_context
            extra = tuple(d.dependency for d in getattr(context, "dependencies", []))
            yield from _all_api_routes(included.routes, prefix + context.prefix, inherited + extra)
        elif isinstance(route, APIRoute):
            yield prefix + route.path, route, inherited


def _concrete_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "SYNTHETIC", path)


@pytest.mark.parametrize("auth_mode", ["local", "databricks"])
def test_every_api_route_requires_sign_in_except_public_ones(auth_mode):
    services = FakeServices()
    client = make_client(make_settings(auth_mode=auth_mode), services)
    protected, seen = set(), 0
    for path, route, inherited in _all_api_routes(client.app.routes):
        if not (path == "/api" or path.startswith("/api/")):
            continue
        for method in sorted(route.methods):
            seen += 1
            if (path, method) in PUBLIC_API_ROUTES:
                continue
            response = client.request(method, _concrete_path(path))
            if route.endpoint.__name__ == "api_not_found":
                # The catch-all only ever says "not found".
                assert response.status_code == 404, (path, method)
                continue
            calls = set(_dependency_calls(route.dependant)) | set(inherited)
            assert require_user in calls, (path, method)
            assert response.status_code == 401, (path, method, response.status_code)
            protected.add((path, method))
    assert seen > len(PUBLIC_API_ROUTES)
    assert CONTRACT_PROTECTED <= protected
    assert services.build_calls == [] and services.render_calls == 0


# --------------------------------------------------------------------------- #
# Login rate limit: X-Forwarded-For spoofing (local mode)
# --------------------------------------------------------------------------- #
def _load_app_py():
    spec = importlib.util.spec_from_file_location("fmea_app_entrypoint_review", Path(PROJECT_ROOT) / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _uvicorn_options(monkeypatch, settings) -> dict:
    module = _load_app_py()
    captured: dict = {}
    monkeypatch.setattr(module.uvicorn, "run", lambda target, **kwargs: captured.update(kwargs))
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(module.logging, "basicConfig", lambda **kwargs: None)
    module.main()
    return captured


def _as_served_by_uvicorn(app, options: dict):
    """Wrap ``app`` in the middleware uvicorn adds for these ``uvicorn.run`` options."""
    relevant = {k: v for k, v in options.items() if k in ("proxy_headers", "forwarded_allow_ips")}
    config = uvicorn.Config(app, log_config=None, **relevant)
    config.load()
    return config.loaded_app


def test_forwarded_for_cannot_bypass_login_rate_limit_in_local_mode(monkeypatch):
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    settings = make_settings(admin_password_hash=fast_password_hash())
    options = _uvicorn_options(monkeypatch, settings)
    app = create_app(
        settings=settings,
        services=FakeServices(),
        frontend_dist=Path("SYNTHETIC-missing"),
        extra_local_hosts=TEST_CLIENT_HOSTS,
    )
    # The local browser connects from 127.0.0.1, the address uvicorn trusts by default.
    client = TestClient(_as_served_by_uvicorn(app, options), client=("127.0.0.1", 50000))

    for _ in range(5):
        assert login(client, "admin", "SYNTHETIC-wrong").status_code == 401
    assert login(client, "admin", "SYNTHETIC-wrong").status_code == 429
    for n in range(5):
        spoofed = {"X-Forwarded-For": f"198.51.100.{n + 1}"}
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "SYNTHETIC-wrong"}, headers=spoofed
        )
        assert response.status_code == 429, "a made-up X-Forwarded-For must not reset the limit"


def test_databricks_mode_keeps_uvicorn_proxy_header_support(monkeypatch):
    options = _uvicorn_options(monkeypatch, make_settings(auth_mode="databricks"))
    assert options.get("proxy_headers", True) is True
    assert _uvicorn_options(monkeypatch, make_settings(auth_mode="local"))["proxy_headers"] is False


# --------------------------------------------------------------------------- #
# Login rate limit: memory and username spraying
# --------------------------------------------------------------------------- #
def test_rate_limit_key_size_does_not_grow_with_username():
    key = LoginRateLimiter.key_for("SYNTHETIC" * 200_000, "127.0.0.1")
    assert len(key) <= 200
    # Case and surrounding spaces still map to the same key.
    assert key == LoginRateLimiter.key_for("  " + "synthetic" * 200_000 + " ", "127.0.0.1")
    assert key != LoginRateLimiter.key_for("SYNTHETIC" * 200_000, "127.0.0.2")


def test_username_spraying_cannot_evict_a_blocked_account():
    settings = make_settings(admin_password_hash=fast_password_hash())
    client = make_client(settings)
    clock = FakeClock()
    client.app.state.login_limiter = LoginRateLimiter(clock=clock, max_keys=100)

    for _ in range(5):
        assert login(client, "admin", "SYNTHETIC-wrong").status_code == 401
    assert login(client, "admin", "SYNTHETIC-wrong").status_code == 429

    # Enough different usernames to push "admin" out of a 100-entry table.
    for n in range(150):
        assert login(client, f"SYNTHETIC-spray-{n}", "SYNTHETIC-wrong").status_code in (401, 429)
    assert login(client, "admin", SYNTHETIC_PASSWORD).status_code == 429

    # Another computer is not affected by this client's attempts.
    other = TestClient(client.app, client=("198.51.100.20", 50000))
    assert login(other, "admin", SYNTHETIC_PASSWORD).status_code == 200

    clock.advance(5 * 60 + 1)
    assert login(client, "admin", SYNTHETIC_PASSWORD).status_code == 200


# --------------------------------------------------------------------------- #
# Request bodies outside the upload are small
# --------------------------------------------------------------------------- #
def test_login_body_size_is_limited():
    client = make_client()
    big = json.dumps({"username": "SYNTHETIC" * (MB // 4), "password": "SYNTHETIC"}).encode()

    response = client.post("/api/auth/login", content=big, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json() == {"detail": MSG_REQUEST_TOO_LARGE}

    def chunks():  # no Content-Length header
        for start in range(0, len(big), 64 * 1024):
            yield big[start:start + 64 * 1024]

    response = client.post("/api/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json() == {"detail": MSG_REQUEST_TOO_LARGE}

    assert login(client).status_code == 200
    # The workbook upload keeps its own, much larger limit.
    assert upload(client, data=b"x" * (2 * MB)).status_code == 200


# --------------------------------------------------------------------------- #
# Static files: the lookup never touches the filesystem outside frontend/dist
# --------------------------------------------------------------------------- #
OUTSIDE_PATHS = [
    "///SYNTHETIC-host.invalid/share/SYNTHETIC.js",
    "/assets///SYNTHETIC-host.invalid/share/SYNTHETIC.js",
    "/\\\\SYNTHETIC-host.invalid\\share\\SYNTHETIC.js",
    "/assets/\\\\SYNTHETIC-host.invalid\\share\\SYNTHETIC.js",
    "/assets/C:/SYNTHETIC-outside/SYNTHETIC.js",
    "/C:\\SYNTHETIC-outside\\SYNTHETIC.js",
    "/assets/index-SYNTHETIC.js::$DATA",
    "/assets/..//SYNTHETIC_secret.txt",
]


@pytest.mark.parametrize("raw_path", OUTSIDE_PATHS)
def test_static_lookup_never_touches_paths_outside_dist(frontend, monkeypatch, raw_path):  # noqa: F811
    app = make_client(frontend_dist=frontend).app
    dist = str(frontend.resolve())
    touched: list[str] = []

    def spy(name):
        original = getattr(pathlib.Path, name)

        def wrapper(self, *args, **kwargs):
            touched.append(str(self))
            if "SYNTHETIC-host" in str(self) or "SYNTHETIC-outside" in str(self):
                # Never really open a network share or a made-up drive path.
                return self if name == "resolve" else False
            return original(self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, name, wrapper)

    for name in ("resolve", "is_file", "exists"):
        spy(name)

    status, body = _asgi_get(app, raw_path)
    assert SECRET_TEXT.encode() not in body
    assert status in (200, 404)
    outside = [p for p in touched if not p.lower().startswith(dist.lower())]
    assert outside == [], f"filesystem lookups outside dist for {raw_path!r}: {outside}"


# --------------------------------------------------------------------------- #
# PDF download names: RFC 5987 filename* for names that are not plain ASCII
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "pdf_filename",
    [
        "FMEA_Report_SYNTHETIC_Stesen_Ĉ_2026-01-15.pdf",
        'FMEA Report "SYNTHETIC" A.pdf',
        "FMEA_Report_SYNTHETIC_发电站_2026-01-15.pdf",
    ],
)
def test_pdf_content_disposition_keeps_non_ascii_names(pdf_filename):
    services = FakeServices()
    client = make_client(services=services)
    assert login(client).status_code == 200
    services.next_report = make_report(pdf_filename=pdf_filename)
    assert upload(client).status_code == 200

    for query, disposition in (("?download=0", "inline"), ("?download=1", "attachment")):
        response = client.get("/api/report/pdf" + query)
        assert response.status_code == 200
        header = response.headers["content-disposition"]
        header.encode("ascii")  # header stays plain ASCII
        parsed = email.message.Message()
        parsed["content-disposition"] = header
        assert parsed.get_content_disposition() == disposition
        # ASCII fallback for old clients: quoted, no quotes or separators inside.
        fallback = parsed.get_filename()
        assert fallback.isascii() and fallback.endswith(".pdf") and '"' not in fallback
        # Browsers use filename* (RFC 6266 / RFC 5987) when present.
        match = re.fullmatch(rf"""{disposition}; filename="[^"]*"; filename\*=UTF-8''([A-Za-z0-9%!#$&+\-.^_`|~]+)""", header)
        assert match, header
        assert unquote(match.group(1), encoding="utf-8", errors="strict") == pdf_filename


def test_pdf_content_disposition_plain_ascii_name_is_unchanged():
    client = make_client()
    assert login(client).status_code == 200
    assert upload(client).status_code == 200
    header = client.get("/api/report/pdf?download=1").headers["content-disposition"]
    assert header == 'attachment; filename="FMEA_Report_SYNTHETIC_Station_2026-01-15.pdf"'


# --------------------------------------------------------------------------- #
# Configuration mistakes fail at startup with a plain message
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cookie_name", ["SYNTHETIC bad name", "SYNTHETIC;name", ""])
def test_invalid_cookie_name_fails_at_startup(cookie_name):
    with pytest.raises(ValueError, match="SESSION_COOKIE_NAME"):
        create_app(settings=make_settings(cookie_name=cookie_name), services=FakeServices())


# --------------------------------------------------------------------------- #
# No plaintext credentials outside the documented initial-setup note
# --------------------------------------------------------------------------- #
_TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt", ".yaml", ".yml",
    ".html", ".css", ".ini", ".toml", ".cfg", ".example", ".env",
}
_SKIPPED_DIRS = {"node_modules", "__pycache__", ".pytest_cache", ".git", ".venv", ".vite"}


def _documented_dev_password() -> str:
    note = (Path(PROJECT_ROOT) / "backend" / "settings.py").read_text(encoding="utf-8")
    match = re.search(r'initial development password \("([^"]+)"\)', note)
    assert match, "settings.py should document the initial development password"
    return match.group(1)


def test_dev_password_appears_only_in_the_settings_note():
    password = _documented_dev_password()
    # README.md documents the initial development account for the first local
    # sign-in (with the instruction to replace it); nowhere else may it appear.
    allowed = {
        (Path(PROJECT_ROOT) / "backend" / "settings.py").resolve(),
        (Path(PROJECT_ROOT) / "README.md").resolve(),
    }
    found = []
    for path in Path(PROJECT_ROOT).rglob("*"):
        if any(part in _SKIPPED_DIRS for part in path.parts) or not path.is_file():
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES and path.name != ".env.example":
            continue
        if path.resolve() in allowed:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if password.lower() in text.lower():
            found.append(str(path.relative_to(PROJECT_ROOT)))
    assert found == []


# --------------------------------------------------------------------------- #
# Databricks mode: one user without a cookie cannot push everyone else out
# --------------------------------------------------------------------------- #
def test_databricks_cookieless_requests_do_not_evict_other_users():
    services = FakeServices()
    client = make_client(make_settings(auth_mode="databricks", max_sessions=20), services)
    colleague = {"X-Forwarded-Email": "SYNTHETIC.colleague@example.com"}
    assert upload(client, headers=colleague).status_code == 200

    flooder = TestClient(client.app)
    for _ in range(60):
        flooder.cookies.clear()  # e.g. a script, or a browser that drops the cookie
        assert flooder.get("/api/auth/me", headers={"X-Forwarded-Email": "SYNTHETIC.flood@example.com"}).status_code == 200

    report = client.get("/api/report", headers=colleague)
    assert report.status_code == 200
    assert len(client.app.state.sessions) <= 20


# --------------------------------------------------------------------------- #
# Smaller wiring checks
# --------------------------------------------------------------------------- #
def test_too_large_response_has_security_headers():
    response = make_client().post(
        "/api/auth/login", content=b"{" + b" " * (MB) + b"}", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_index_html_is_never_cached_however_requested(frontend):  # noqa: F811
    client = make_client(frontend_dist=frontend)
    for path in ("/", "/index.html", "/review"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "no-cache", path


def test_app_py_listens_on_databricks_app_port(monkeypatch):
    from backend import settings as settings_module

    for name in ("HOST", "PORT", "AUTH_MODE", "SESSION_COOKIE_NAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABRICKS_APP_PORT", "8765")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("AUTH_MODE", "databricks")
    settings_module.get_settings.cache_clear()
    try:
        options = _uvicorn_options(monkeypatch, settings_module.get_settings())
    finally:
        settings_module.get_settings.cache_clear()
    assert options["port"] == 8765
    assert options["host"] == "0.0.0.0"
    assert options["workers"] == 1
    assert options["proxy_headers"] is True
