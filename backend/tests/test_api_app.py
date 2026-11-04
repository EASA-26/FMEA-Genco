"""Application wiring: health, headers, error handling, frontend serving,
the lazy service indirection and the deployment files."""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import types
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.api.services import DEFAULT_OPEN_ERROR_MESSAGE, ReportServices
from backend.main import MSG_FRONTEND_MISSING, MSG_SERVER_ERROR, create_app
from backend.settings import PROJECT_ROOT
from backend.tests.test_api_support import (
    TEST_CLIENT_HOSTS,
    FakeServices,
    login,
    make_client,
    make_report,
    make_settings,
)

SECRET_TEXT = "SYNTHETIC-SECRET-CONTENT-must-never-be-served"
INDEX_HTML = "<!doctype html><html><head><title>SYNTHETIC SPA</title></head><body></body></html>"
SECURITY = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "SAMEORIGIN",
}


def _assert_security_headers(response):
    for name, value in SECURITY.items():
        assert response.headers.get(name) == value, name


# --------------------------------------------------------------------------- #
# Health and headers
# --------------------------------------------------------------------------- #
def test_health_needs_no_sign_in():
    response = make_client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    _assert_security_headers(response)
    assert response.headers["cache-control"] == "no-store"


def test_health_in_databricks_mode_needs_no_identity():
    response = make_client(make_settings(auth_mode="databricks")).get("/api/health")
    assert response.status_code == 200


def test_security_headers_on_errors():
    client = make_client()
    for response in (client.get("/api/report"), client.get("/api/nothing-here"), client.get("/")):
        _assert_security_headers(response)


def test_no_interactive_api_docs_exposed(tmp_path):
    client = make_client(frontend_dist=tmp_path / "missing")
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 404
        assert "swagger" not in response.text.lower()


def test_invalid_auth_mode_fails_at_startup():
    with pytest.raises(ValueError, match="AUTH_MODE"):
        create_app(settings=make_settings(auth_mode="ldap"), services=FakeServices())


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
def _app_with_crashing_route():
    client = make_client(raise_server_exceptions=False)

    async def crash():
        raise RuntimeError("SYNTHETIC password=hunter2 at C:\\secret\\module.py")

    # Put it first so the /api catch-all does not shadow it.
    client.app.router.routes.insert(0, APIRoute("/api/SYNTHETIC-crash", crash, methods=["GET"]))
    return client


def test_unhandled_exception_returns_plain_500_without_internals():
    response = _app_with_crashing_route().get("/api/SYNTHETIC-crash")
    assert response.status_code == 500
    assert response.json() == {"detail": MSG_SERVER_ERROR}
    for leaked in ("hunter2", "Traceback", "RuntimeError", "module.py"):
        assert leaked not in response.text
    _assert_security_headers(response)


def test_unknown_api_paths_are_json_404_for_every_method(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    client = make_client(frontend_dist=dist)
    for method in ("GET", "POST", "PUT", "DELETE"):
        for path in ("/api", "/api/", "/api/unknown", "/api/report/unknown/deeper"):
            response = client.request(method, path)
            assert response.status_code == 404, (method, path)
            assert response.json() == {"detail": "Not found."}


def test_validation_errors_are_plain_text():
    client = make_client()
    response = client.post("/api/auth/login", json=["not", "an", "object"])
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert "loc" not in response.text


# --------------------------------------------------------------------------- #
# Frontend serving
# --------------------------------------------------------------------------- #
@pytest.fixture
def frontend(tmp_path):
    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "index-SYNTHETIC.js").write_text("console.log('SYNTHETIC');", encoding="utf-8")
    (dist / "assets" / "index-SYNTHETIC.css").write_text("body{color:#0A2340}", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (dist / ".env").write_text(SECRET_TEXT, encoding="utf-8")
    (tmp_path / "frontend" / "SYNTHETIC_secret.txt").write_text(SECRET_TEXT, encoding="utf-8")
    (tmp_path / "SYNTHETIC_secret.txt").write_text(SECRET_TEXT, encoding="utf-8")
    return dist


def test_spa_index_and_client_routes(frontend):
    client = make_client(frontend_dist=frontend)
    for path in ("/", "/review", "/analysis/uoir/712", "/recommendation?tab=yes", "/missing.js"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text == INDEX_HTML
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-cache"
        _assert_security_headers(response)


def test_spa_assets_are_served_with_correct_types(frontend):
    client = make_client(frontend_dist=frontend)
    js = client.get("/assets/index-SYNTHETIC.js")
    assert js.status_code == 200
    assert js.text == "console.log('SYNTHETIC');"
    assert js.headers["content-type"].startswith("text/javascript")
    css = client.get("/assets/index-SYNTHETIC.css")
    assert css.headers["content-type"].startswith("text/css")
    icon = client.get("/favicon.svg")
    assert icon.status_code == 200 and icon.headers["content-type"].startswith("image/svg+xml")
    assert client.head("/assets/index-SYNTHETIC.js").status_code == 200


def test_missing_asset_is_404_not_index(frontend):
    response = make_client(frontend_dist=frontend).get("/assets/nope-SYNTHETIC.js")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}


def test_frontend_not_built_message(tmp_path):
    response = make_client(frontend_dist=tmp_path / "no-dist").get("/")
    assert response.status_code == 404
    assert response.json() == {"detail": MSG_FRONTEND_MISSING}
    assert make_client(frontend_dist=tmp_path / "no-dist").get("/assets/x.js").status_code == 404


TRAVERSAL_PATHS = [
    "/../SYNTHETIC_secret.txt",
    "/../../SYNTHETIC_secret.txt",
    "/assets/../../SYNTHETIC_secret.txt",
    "/assets/../../../SYNTHETIC_secret.txt",
    "/..\\SYNTHETIC_secret.txt",
    "/assets/..\\..\\SYNTHETIC_secret.txt",
    "/assets/..\\..\\..\\SYNTHETIC_secret.txt",
    "/.env",
    "/assets/../.env",
]


def _asgi_get(app, path: str) -> tuple[int, bytes]:
    """Call the app with an exact, un-normalised path (no HTTP client cleanup)."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8", "surrogateescape"),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body


@pytest.mark.parametrize("path", TRAVERSAL_PATHS)
def test_path_traversal_raw_paths_never_escape_dist(frontend, path):
    app = make_client(frontend_dist=frontend).app
    status, body = _asgi_get(app, path)
    assert SECRET_TEXT.encode() not in body
    assert status in (200, 404)


def test_absolute_paths_never_escape_dist(frontend, tmp_path):
    app = make_client(frontend_dist=frontend).app
    secret = (tmp_path / "SYNTHETIC_secret.txt").resolve()
    for path in ("/" + str(secret), "/" + secret.as_posix(), "/assets/" + secret.as_posix(), "/assets//" + secret.as_posix()):
        status, body = _asgi_get(app, path)
        assert SECRET_TEXT.encode() not in body, path


@pytest.mark.parametrize(
    "encoded",
    [
        "/..%2FSYNTHETIC_secret.txt",
        "/%2e%2e/%2e%2e/SYNTHETIC_secret.txt",
        "/assets/..%2F..%2F..%2FSYNTHETIC_secret.txt",
        "/assets/%2e%2e%5c%2e%2e%5cSYNTHETIC_secret.txt",
        "/%2e%2e%5cSYNTHETIC_secret.txt",
        "/%2Eenv",
    ],
)
def test_path_traversal_encoded_over_http(frontend, encoded):
    client = make_client(frontend_dist=frontend)
    response = client.get(encoded)
    assert SECRET_TEXT not in response.text
    assert response.status_code in (200, 404)


def test_api_is_not_shadowed_by_frontend(frontend):
    client = make_client(frontend_dist=frontend)
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 200
    assert client.get("/api/report").json() == {"detail": "No workbook uploaded yet."}


# --------------------------------------------------------------------------- #
# Lazy service indirection
# --------------------------------------------------------------------------- #
class _SyntheticOpenError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def test_default_services_import_builder_and_renderer_at_call_time(monkeypatch):
    calls = {}
    builder = types.ModuleType("backend.report.builder")
    builder.WorkbookOpenError = _SyntheticOpenError

    def fake_build(data, filename):
        calls["build"] = (data, filename)
        return make_report(source_filename=filename)

    builder.build_report = fake_build
    render = types.ModuleType("backend.pdf.render")

    def fake_render(report):
        calls["render"] = report.station
        return b"%PDF SYNTHETIC"

    render.render_pdf = fake_render
    monkeypatch.setitem(sys.modules, "backend.report.builder", builder)
    monkeypatch.setitem(sys.modules, "backend.pdf.render", render)

    services = ReportServices()
    report = services.build_report(b"SYNTHETIC", "SYNTHETIC.xlsx")
    assert calls["build"] == (b"SYNTHETIC", "SYNTHETIC.xlsx")
    assert services.render_pdf(report) == b"%PDF SYNTHETIC"
    assert calls["render"] == "SYNTHETIC Station"

    assert services.open_error_message(_SyntheticOpenError("SYNTHETIC plain message")) == "SYNTHETIC plain message"
    assert services.open_error_message(_SyntheticOpenError("")) == DEFAULT_OPEN_ERROR_MESSAGE
    assert services.open_error_message(ValueError("SYNTHETIC other")) is None


def test_default_services_through_the_api(monkeypatch):
    builder = types.ModuleType("backend.report.builder")
    builder.WorkbookOpenError = _SyntheticOpenError

    def fake_build(data, filename):
        if data == b"bad":
            raise _SyntheticOpenError("SYNTHETIC cannot open")
        return make_report(source_filename=filename)

    builder.build_report = fake_build
    monkeypatch.setitem(sys.modules, "backend.report.builder", builder)

    client = TestClient(
        create_app(settings=make_settings(), frontend_dist=Path("SYNTHETIC-missing"), extra_local_hosts=TEST_CLIENT_HOSTS)
    )
    assert login(client).status_code == 200
    bad = client.post("/api/workbook", files={"file": ("SYNTHETIC.xlsx", b"bad")})
    assert bad.status_code == 400 and bad.json() == {"detail": "SYNTHETIC cannot open"}
    good = client.post("/api/workbook", files={"file": ("SYNTHETIC.xlsx", b"good")})
    assert good.status_code == 200 and good.json()["source_filename"] == "SYNTHETIC.xlsx"


def test_open_error_message_when_builder_cannot_be_imported(monkeypatch):
    monkeypatch.setitem(sys.modules, "backend.report.builder", None)  # import raises ImportError
    assert ReportServices().open_error_message(RuntimeError("x")) is None


def test_importing_app_does_not_import_parser_or_pdf():
    code = (
        "import sys, backend.main; "
        "print('backend.report.builder' in sys.modules, 'backend.pdf.render' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False"


# --------------------------------------------------------------------------- #
# Entrypoint and deployment files
# --------------------------------------------------------------------------- #
def test_app_py_runs_uvicorn_with_settings(monkeypatch):
    spec = importlib.util.spec_from_file_location("fmea_app_entrypoint", Path(PROJECT_ROOT) / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured = {}
    monkeypatch.setattr(module.uvicorn, "run", lambda target, **kwargs: captured.update(target=target, **kwargs))
    monkeypatch.setattr(module, "get_settings", lambda: make_settings(host="0.0.0.0", port=8123))
    monkeypatch.setattr(module.logging, "basicConfig", lambda **kwargs: None)
    module.main()
    assert captured["target"] == "backend.main:app"
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8123
    assert captured["workers"] == 1
    # Windows avoids the Proactor loop (it stops accepting after aborted connections).
    assert module.event_loop_option("win32") == "asyncio:SelectorEventLoop"
    assert module.event_loop_option("linux") == "auto"


def test_app_yaml_databricks_settings():
    text = (Path(PROJECT_ROOT) / "app.yaml").read_text(encoding="utf-8")
    assert "command: ['python', 'app.py']" in text
    active = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for name, value in (
        ("HOST", "0.0.0.0"), ("AUTH_MODE", "databricks"), ("COOKIE_SECURE", "true"), ("OUTLOOK_EMAIL", "off"),
    ):
        assert f"name: {name}\n    value: '{value}'" in active
    assert "valueFrom" in text
    assert "scrypt$" not in text  # never a real hash in the file


def test_env_example_lists_every_setting_with_safe_defaults():
    text = (Path(PROJECT_ROOT) / ".env.example").read_text(encoding="utf-8")
    for name in (
        "AUTH_MODE", "ADMIN_USERNAME", "ADMIN_PASSWORD_HASH", "SESSION_IDLE_MINUTES", "MAX_SESSIONS",
        "MAX_UPLOAD_MB", "COOKIE_SECURE", "SESSION_COOKIE_NAME", "HOST", "PORT", "LOG_LEVEL", "OUTLOOK_EMAIL",
    ):
        assert f"{name}=" in text, name
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    assert values["AUTH_MODE"] == "local"
    assert values["HOST"] == "127.0.0.1"
    assert values["COOKIE_SECURE"] == "false"
    assert values["OUTLOOK_EMAIL"] == "auto"
    assert "ADMIN_PASSWORD_HASH" not in values  # left commented: no secret in the example
