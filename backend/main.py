"""FastAPI application: API routes, plain-language errors, security headers and
the built React frontend (``frontend/dist``).

Run with ``python app.py``. Tests build their own app with
``create_app(settings=..., services=..., frontend_dist=...)``.
"""
from __future__ import annotations

import logging
import mimetypes
from collections.abc import Iterable
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.api import routes_auth, routes_report
from backend.api.services import ReportServices
from backend.auth.passwords import is_password_hash
from backend.auth.service import (
    AUTH_MODE_DATABRICKS,
    AUTH_MODE_LOCAL,
    AUTH_MODES,
    LoginRateLimiter,
    SessionCookieMiddleware,
    check_cookie_name,
)
from backend.mail.outlook import LOCAL_HOSTS, OUTLOOK_EMAIL_MODES, OUTLOOK_EMAIL_ON, OutlookMailer
from backend.sessions.store import SessionStore
from backend.settings import DEFAULT_ADMIN_PASSWORD_HASH, FRONTEND_DIST, Settings, get_settings

logger = logging.getLogger("fmea")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "SAMEORIGIN",   # the PDF preview iframe is same-origin
}

MSG_SERVER_ERROR = "Something went wrong on the server. Please try again or contact support."
MSG_BAD_REQUEST_FORMAT = "Some of the information sent was missing or not in the expected format."
MSG_FRONTEND_MISSING = "The web interface is not available. Build the frontend (npm run build) and restart."
MSG_REQUEST_TOO_LARGE = "This request is too large to process."
MSG_NOT_LOCAL = "This app only answers on this computer's own address. Open it at {url}."

# Methods that never change anything; other requests must also come from a local page.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Sessions one Databricks user may hold at once (several browsers or devices).
DATABRICKS_SESSIONS_PER_USER = 5

# Largest request body accepted anywhere except the workbook upload, which
# streams and limits its own body (MAX_UPLOAD_MB). Sign-in bodies are tiny.
MAX_SMALL_BODY_BYTES = 64 * 1024
UPLOAD_PATH = "/api/workbook"

# Characters and names with a special meaning in Windows paths. A frontend
# build never produces them, so a request containing them is simply not found.
_UNSAFE_PATH_CHARS = frozenset('\\:*?"<>|')
_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(10)} | {f"LPT{i}" for i in range(10)}
)

# Used when an HTTP error carries only the standard reason phrase.
_DEFAULT_ERROR_MESSAGES = {
    400: "The request could not be processed.",
    401: "Please sign in to continue.",
    403: "You do not have access to this.",
    404: "Not found.",
    405: "This action is not allowed here.",
    413: "The upload is too large.",
    429: "Too many requests. Please wait a moment and try again.",
}

# Explicit types for frontend files: on Windows, `mimetypes` reads the registry,
# which sometimes maps .js to text/plain and breaks module scripts under nosniff.
_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
}

_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #
class SecurityHeadersMiddleware:
    """Adds the security headers to every response, and ``no-store`` to API responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = _is_api_path(scope.get("path", ""))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", []))
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if name not in headers:
                        headers[name] = value
                if is_api and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class RequestBodyLimitMiddleware:
    """Refuses request bodies larger than ``max_bytes`` with 413.

    FastAPI reads a JSON body completely into memory before any dependency or
    handler runs, so without this limit anyone could send a sign-in request
    of any size. The workbook upload (``exempt_paths``) streams and limits its
    own body and is left alone.
    """

    def __init__(self, app: ASGIApp, max_bytes: int, exempt_paths: tuple[str, ...] = (UPLOAD_PATH,)) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.exempt_paths = frozenset(exempt_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            response = JSONResponse({"detail": MSG_REQUEST_TOO_LARGE}, status_code=413)
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            # Bodies sent without Content-Length (chunked) are counted as they arrive.
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # FastAPI passes HTTPExceptions raised while reading the body
                    # on to the error handlers, which send the plain 413.
                    raise StarletteHTTPException(status_code=413, detail=MSG_REQUEST_TOO_LARGE)
            return message

        await self.app(scope, limited_receive, send)


def _host_name(value: str) -> str | None:
    """The host name in a Host header (``name``, ``name:port``, ``[v6]:port``),
    lower-case and without the port; None when it is not in that form."""
    value = value.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        rest = value[end + 1:] if end != -1 else ""
        if end == -1 or (rest and not (rest.startswith(":") and rest[1:].isdigit())):
            return None
        return value[1:end]
    name, colon, port = value.partition(":")
    if colon and not port.isdigit():
        return None   # also refuses a bare IPv6 address without brackets
    return name


def _origin_host_name(origin: str) -> str | None:
    """The host name of an Origin header (``scheme://host[:port]``); None for "null"."""
    try:
        parts = urlsplit(origin.strip())
        parts.port  # raises ValueError for a malformed port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    return parts.hostname


class LocalOnlyMiddleware:
    """When the app runs only for this computer (``AUTH_MODE=local`` and a
    loopback ``HOST``), refuse requests addressed to any other name.

    A web page on another site can make the browser send requests to the app
    under that site's own name (DNS rebinding: the name is pointed at
    127.0.0.1), and the browser then treats the page and the app as one site.
    Such requests carry that name in the Host header and are refused with 403.
    Requests that change something must, when they carry an Origin header,
    also come from a page on a loopback address.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str], local_url: str) -> None:
        self.app = app
        self.allowed_hosts = frozenset(name.lower() for name in allowed_hosts)
        self.message = MSG_NOT_LOCAL.format(url=local_url)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        allowed = _host_name(headers.get("host", "")) in self.allowed_hosts
        origin = headers.get("origin")
        if allowed and origin is not None and scope.get("method", "GET") not in _SAFE_METHODS:
            allowed = _origin_host_name(origin) in self.allowed_hosts
        if not allowed:
            response = JSONResponse({"detail": self.message}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            text = value.decode("latin-1").strip()
            return int(text) if text.isascii() and text.isdigit() else None
    return None


# --------------------------------------------------------------------------- #
# Errors: always {"detail": "<plain message>"}, never a stack trace
# --------------------------------------------------------------------------- #
def _add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        detail = exc.detail
        try:
            standard_phrase = HTTPStatus(exc.status_code).phrase
        except ValueError:
            standard_phrase = ""
        if not isinstance(detail, str) or not detail.strip() or detail == standard_phrase:
            detail = _DEFAULT_ERROR_MESSAGES.get(exc.status_code, "The request could not be completed.")
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        return JSONResponse({"detail": MSG_BAD_REQUEST_FORMAT}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> Response:
        # Details stay in the server log; the browser gets a plain message.
        # %r keeps an encoded line break in the URL from starting a fake log line.
        logger.error("Unexpected error on %s %r", request.method, request.url.path, exc_info=exc)
        headers = dict(SECURITY_HEADERS)
        headers["Cache-Control"] = "no-store"
        return JSONResponse({"detail": MSG_SERVER_ERROR}, status_code=500, headers=headers)


# --------------------------------------------------------------------------- #
# Frontend files
# --------------------------------------------------------------------------- #
def _plain_path_parts(relative: str) -> list[str] | None:
    """Split a URL path into ordinary file and folder names, or None.

    This runs before the filesystem is touched. Empty parts (``//host/share``,
    a leading ``/``), ``.``/``..`` and dotfiles, backslashes, drive letters,
    ``::$DATA`` streams and device names are refused. On Windows a path like
    ``//host/share/x`` would otherwise make the server open a network
    connection to that host (and offer the signed-in Windows account to it).
    """
    if not relative or len(relative) > 512:
        return None
    parts = relative.split("/")
    for part in parts:
        if not part or part.startswith(".") or part != part.rstrip(" ."):
            return None
        if any(ch in _UNSAFE_PATH_CHARS or ord(ch) < 32 or ord(ch) == 127 for ch in part):
            return None
        if part.split(".", 1)[0].upper() in _WINDOWS_DEVICE_NAMES:
            return None
    return parts


def _file_inside(root: Path, relative: str) -> Path | None:
    """The regular file at ``root/relative``, or None if missing or outside ``root``.

    The request path is first checked name by name (`_plain_path_parts`); the
    result is then resolved (following symlinks) and must still be under
    ``root``.
    """
    parts = _plain_path_parts(relative)
    if parts is None:
        return None
    try:
        base = root.resolve()
        candidate = base.joinpath(*parts).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if candidate == base or not candidate.is_relative_to(base):
        return None
    if any(part.startswith(".") for part in candidate.relative_to(base).parts):
        return None
    try:
        return candidate if candidate.is_file() else None
    except OSError:
        return None


def _file_response(path: Path, **kwargs) -> FileResponse:
    media_type = _MEDIA_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
    return FileResponse(path, media_type=media_type or "application/octet-stream", **kwargs)


def _add_frontend_routes(app: FastAPI, dist: Path) -> None:
    @app.api_route("/assets/{asset_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend_asset(asset_path: str) -> Response:
        found = _file_inside(dist / "assets", asset_path)
        if found is None:
            raise StarletteHTTPException(status_code=404, detail="Not found.")
        return _file_response(found)

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend_page(full_path: str) -> Response:
        index = dist / "index.html"
        if not index.is_file():
            raise StarletteHTTPException(status_code=404, detail=MSG_FRONTEND_MISSING)
        # Top-level files copied from the frontend's public folder (e.g. favicon).
        found = _file_inside(dist, full_path)
        if found is not None and found.parent == dist.resolve() and found.name != index.name:
            return _file_response(found)
        # Every other page is a client-side route of the single-page app.
        return _file_response(index, headers={"Cache-Control": "no-cache"})


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
def _runs_locally(settings: Settings) -> bool:
    """The app serves only this computer: local sign-in and a loopback HOST."""
    return settings.auth_mode == AUTH_MODE_LOCAL and settings.host.strip().lower() in LOCAL_HOSTS


def _log_setting_warnings(settings: Settings) -> None:
    if settings.auth_mode == AUTH_MODE_LOCAL:
        if not is_password_hash(settings.admin_password_hash):
            logger.error(
                "ADMIN_PASSWORD_HASH is not a valid password hash, so nobody can sign in. "
                "Create one with: python tools/hash_password.py"
            )
        elif settings.admin_password_hash == DEFAULT_ADMIN_PASSWORD_HASH:
            logger.warning(
                "Using the built-in development password. Set ADMIN_PASSWORD_HASH before sharing this app."
            )
    elif settings.auth_mode == AUTH_MODE_DATABRICKS:
        logger.info(
            "AUTH_MODE=databricks: users are identified by the Databricks proxy headers. "
            "Never expose this server directly."
        )
    if settings.outlook_email == OUTLOOK_EMAIL_ON and not _runs_locally(settings):
        logger.warning(
            "OUTLOOK_EMAIL=on: 'Email the PDF' opens Outlook on the computer running this server, "
            "whoever is using the app."
        )


def create_app(
    settings: Settings | None = None,
    services: object | None = None,
    frontend_dist: Path | str | None = None,
    outlook: OutlookMailer | None = None,
    extra_local_hosts: Iterable[str] = (),
) -> FastAPI:
    """Build the application.

    ``services`` replaces the parser/PDF back end (see `backend.api.services`),
    ``frontend_dist`` the built frontend folder and ``outlook`` the Outlook
    launcher (see `backend.mail.outlook`); all three are for tests.
    ``extra_local_hosts`` adds host names accepted besides 127.0.0.1,
    localhost and ::1 when the app runs locally (tests: the test client's
    "testserver").
    """
    settings = settings or get_settings()
    if settings.auth_mode not in AUTH_MODES:
        raise ValueError(
            f"AUTH_MODE must be 'local' or 'databricks', not {settings.auth_mode!r}."
        )
    if settings.outlook_email not in OUTLOOK_EMAIL_MODES:
        raise ValueError(
            f"OUTLOOK_EMAIL must be 'auto', 'on' or 'off', not {settings.outlook_email!r}."
        )
    check_cookie_name(settings.cookie_name)
    dist = Path(frontend_dist) if frontend_dist is not None else FRONTEND_DIST

    app = FastAPI(
        title="FMEA Report Generator",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.sessions = SessionStore(
        settings.session_idle_minutes,
        settings.max_sessions,
        # In Databricks mode any request without a cookie starts a session, so
        # each user gets a few slots rather than the power to fill the store.
        max_sessions_per_user=(
            DATABRICKS_SESSIONS_PER_USER if settings.auth_mode == AUTH_MODE_DATABRICKS else None
        ),
    )
    app.state.login_limiter = LoginRateLimiter()
    app.state.services = services if services is not None else ReportServices()
    app.state.frontend_dist = dist
    # Opens "Email the PDF" drafts in Outlook (see backend.mail.outlook).
    app.state.outlook = outlook if outlook is not None else OutlookMailer()

    _log_setting_warnings(settings)
    _add_error_handlers(app)
    # Added last = outermost.
    app.add_middleware(SessionCookieMiddleware, settings=settings)
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_SMALL_BODY_BYTES)
    if _runs_locally(settings):
        app.add_middleware(
            LocalOnlyMiddleware,
            allowed_hosts=LOCAL_HOSTS | frozenset(extra_local_hosts),
            local_url=f"http://127.0.0.1:{settings.port}",
        )
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/api/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok"}

    app.include_router(routes_auth.router)
    app.include_router(routes_report.router)

    # Unknown API paths are JSON 404s, never the frontend page.
    @app.api_route("/api", methods=_ALL_METHODS, include_in_schema=False)
    @app.api_route("/api/{api_path:path}", methods=_ALL_METHODS, include_in_schema=False)
    async def api_not_found() -> Response:
        raise StarletteHTTPException(status_code=404, detail="Not found.")

    _add_frontend_routes(app, dist)
    return app


app = create_app()
