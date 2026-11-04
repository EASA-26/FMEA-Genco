"""Who is using the app: sign-in checks, the current-user dependency and cookies.

Two modes (``AUTH_MODE``):

* ``local`` - one account (``ADMIN_USERNAME`` / ``ADMIN_PASSWORD_HASH``). The
  browser signs in through ``POST /api/auth/login`` and receives a session
  cookie. ``X-Forwarded-*`` headers are ignored because anyone can send them.
* ``databricks`` - the Databricks Apps proxy has already signed the user in and
  passes their identity in ``X-Forwarded-Email`` (or a fallback header). A
  session is created on the first request; there is no login page.

The app-wide objects (settings, session store, rate limiter) live on
``app.state`` and are created by `backend.main.create_app`.
"""
from __future__ import annotations

import hashlib
import hmac
import http.cookies
import re
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.auth.passwords import verify_password
from backend.sessions.store import Session, SessionStore
from backend.settings import Settings

AUTH_MODE_LOCAL = "local"
AUTH_MODE_DATABRICKS = "databricks"
AUTH_MODES = (AUTH_MODE_LOCAL, AUTH_MODE_DATABRICKS)

# Identity headers set by the Databricks Apps proxy, in order of preference.
FORWARDED_IDENTITY_HEADERS = (
    "X-Forwarded-Email",
    "X-Forwarded-Preferred-Username",
    "X-Forwarded-User",
)

MSG_NOT_SIGNED_IN = "Please sign in to continue."
MSG_IDENTITY_MISSING = (
    "Your Databricks sign-in could not be confirmed. Please open the app again from Databricks."
)
MSG_LOGIN_FAILED = "Incorrect username or password."
MSG_LOGIN_RATE_LIMITED = "Too many sign-in attempts. Please wait a few minutes and try again."
MSG_LOGIN_NOT_USED = "Sign-in is handled by Databricks for this app."

LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 5 * 60
# Failed sign-ins allowed from one client across *all* usernames in the same
# window. Without it a client could cycle through made-up usernames until a
# blocked username drops out of the size-limited failure table.
LOGIN_MAX_CLIENT_FAILURES = 50
# Longest username/password checked; longer input is simply a failed attempt.
MAX_CREDENTIAL_LENGTH = 1024
# Characters allowed in a cookie name (an HTTP "token", RFC 6265 / RFC 9110).
_COOKIE_NAME_PATTERN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")

# Key in the ASGI scope "state" dict through which a request asks
# `SessionCookieMiddleware` to set or clear the session cookie.
_COOKIE_STATE_KEY = "fmea_session_cookie"
_CLEAR = object()


@dataclass(frozen=True)
class CurrentUser:
    name: str
    auth_mode: str
    session: Session


# --------------------------------------------------------------------------- #
# App-wide objects
# --------------------------------------------------------------------------- #
def app_settings(request: Request) -> Settings:
    return request.app.state.settings


def session_store(request: Request) -> SessionStore:
    return request.app.state.sessions


def login_limiter(request: Request) -> "LoginRateLimiter":
    return request.app.state.login_limiter


# --------------------------------------------------------------------------- #
# Login rate limiting
# --------------------------------------------------------------------------- #
class _FailureLog:
    """Recent failure times per key (least recently failed first), size-limited.

    Not thread-safe on its own; `LoginRateLimiter` holds the lock.
    """

    def __init__(self, max_failures: int, window_seconds: float, max_keys: int) -> None:
        self.max_failures = max(int(max_failures), 1)
        self.window_seconds = window_seconds
        self.max_keys = max(int(max_keys), 1)
        self.entries: OrderedDict[str, deque[float]] = OrderedDict()

    def wait_seconds(self, key: str, now: float) -> int:
        """0 if ``key`` may try again, else seconds until it may."""
        failures = self._prune(key, now)
        if failures is None or len(failures) < self.max_failures:
            return 0
        oldest_relevant = failures[-self.max_failures]
        return max(1, int(oldest_relevant + self.window_seconds - now) + 1)

    def record(self, key: str, now: float) -> None:
        failures = self.entries.get(key)
        if failures is None:
            failures = self.entries[key] = deque(maxlen=self.max_failures)
        failures.append(now)
        self.entries.move_to_end(key)
        while len(self.entries) > self.max_keys:
            self.entries.popitem(last=False)

    def forget(self, key: str) -> None:
        self.entries.pop(key, None)

    def _prune(self, key: str, now: float) -> deque[float] | None:
        failures = self.entries.get(key)
        if failures is None:
            return None
        while failures and now - failures[0] >= self.window_seconds:
            failures.popleft()
        if not failures:
            del self.entries[key]
            return None
        return failures


class LoginRateLimiter:
    """Blocks sign-in after repeated failures.

    * per username + client: after ``max_failures`` failed attempts within
      ``window_seconds`` (the contract's 5 in 5 minutes);
    * per client, whatever the username: after ``max_client_failures``.

    While blocked, attempts are refused without checking the password, until
    the oldest counted failure is older than the window.

    Use `begin_attempt` before checking the password: it counts the attempt as
    a failure up front (atomically), so many parallel guesses cannot slip past
    the limit while the slow password check runs. Call `reset` on success.

    Memory stays bounded: keys have a fixed size (the username is hashed) and
    each table keeps at most ``max_keys`` entries.
    """

    def __init__(
        self,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_seconds: float = LOGIN_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
        max_client_failures: int = LOGIN_MAX_CLIENT_FAILURES,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._accounts = _FailureLog(max_failures, window_seconds, max_keys)
        self._clients = _FailureLog(max_client_failures, window_seconds, max_keys)

    @staticmethod
    def key_for(username: str, client_host: str) -> str:
        """Fixed-size key: case and surrounding spaces of the username are ignored."""
        normalised = username.strip().lower().encode("utf-8", "surrogatepass")
        return f"{hashlib.sha256(normalised).hexdigest()}\n{LoginRateLimiter._client_key(client_host)}"

    @staticmethod
    def _client_key(client_host: str) -> str:
        return client_host[:64]

    def begin_attempt(self, username: str, client_host: str) -> int:
        """Register a sign-in attempt.

        Returns 0 when the attempt may go ahead (it is provisionally counted as
        a failure), otherwise the number of seconds until the next attempt is
        allowed (nothing is recorded).
        """
        account = self.key_for(username, client_host)
        client = self._client_key(client_host)
        now = self._clock()
        with self._lock:
            wait = max(self._accounts.wait_seconds(account, now), self._clients.wait_seconds(client, now))
            if wait:
                return wait
            self._accounts.record(account, now)
            self._clients.record(client, now)
            return 0

    def reset(self, username: str, client_host: str) -> None:
        """Forget the failures of this username + client after a successful sign-in.

        The per-client count is kept: it only matters to clients that try
        many different usernames.
        """
        with self._lock:
            self._accounts.forget(self.key_for(username, client_host))


def client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def credentials_match(settings: Settings, username: str, password: str) -> bool:
    """Check local-mode credentials. Slow on purpose (scrypt); run in a threadpool.

    The password hash is always checked, even for a wrong username, so the
    response time does not reveal whether the username exists.
    """
    if len(username) > MAX_CREDENTIAL_LENGTH or len(password) > MAX_CREDENTIAL_LENGTH:
        return False
    password_ok = verify_password(password, settings.admin_password_hash)
    username_ok = hmac.compare_digest(
        username.strip().encode("utf-8", "surrogatepass"),
        settings.admin_username.encode("utf-8", "surrogatepass"),
    )
    return password_ok and username_ok


# --------------------------------------------------------------------------- #
# Session cookie
# --------------------------------------------------------------------------- #
def check_cookie_name(name: str) -> None:
    """Raise ValueError for a SESSION_COOKIE_NAME browsers would not accept.

    Checked at startup; otherwise every sign-in would fail with a server error.
    """
    if not isinstance(name, str) or not _COOKIE_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            f"SESSION_COOKIE_NAME {name!r} is not a valid cookie name. "
            "Use letters, digits, '_' or '-' only (for example fmea_session)."
        )


def _cookie_header(settings: Settings, value: object) -> bytes:
    cookie: http.cookies.SimpleCookie = http.cookies.SimpleCookie()
    name = settings.cookie_name
    if value is _CLEAR:
        cookie[name] = ""
        cookie[name]["max-age"] = 0
        cookie[name]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    else:
        cookie[name] = str(value)
    cookie[name]["path"] = "/"
    cookie[name]["httponly"] = True
    cookie[name]["samesite"] = "Lax"
    if settings.cookie_secure:
        cookie[name]["secure"] = True
    return cookie.output(header="").strip().encode("latin-1")


def set_session_cookie(request: Request, token: str) -> None:
    """Ask for the session cookie to be sent with this request's response."""
    request.scope.setdefault("state", {})[_COOKIE_STATE_KEY] = token


def clear_session_cookie(request: Request) -> None:
    """Ask for the session cookie to be removed with this request's response."""
    request.scope.setdefault("state", {})[_COOKIE_STATE_KEY] = _CLEAR


class SessionCookieMiddleware:
    """Adds the Set-Cookie header requested during the request to the response.

    Doing this in one place means the cookie is written with the same flags on
    every response type (JSON, PDF, 204, error responses), which FastAPI's
    per-dependency `Response` does not guarantee.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start" and _COOKIE_STATE_KEY in state:
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", _cookie_header(self.settings, state[_COOKIE_STATE_KEY])))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cookie)


# --------------------------------------------------------------------------- #
# Current user
# --------------------------------------------------------------------------- #
def forwarded_identity(request: Request) -> str | None:
    """The user name passed by the Databricks proxy, or None."""
    for header in FORWARDED_IDENTITY_HEADERS:
        value = (request.headers.get(header) or "").strip()
        if not value:
            continue
        if len(value) > 320 or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            return None
        return value
    return None


async def require_user(request: Request) -> CurrentUser:
    """FastAPI dependency: the signed-in user and their session, or 401."""
    settings = app_settings(request)
    store = session_store(request)
    token = request.cookies.get(settings.cookie_name)

    if settings.auth_mode == AUTH_MODE_DATABRICKS:
        name = forwarded_identity(request)
        if name is None:
            raise HTTPException(status_code=401, detail=MSG_IDENTITY_MISSING)
        session = store.get(token)
        if session is not None and session.user_name != name:
            # Someone else is now signed in to Databricks in this browser:
            # never show them the previous person's report.
            store.destroy(token)
            session = None
        if session is None:
            session = store.create(name)
            set_session_cookie(request, session.token)
        return CurrentUser(name=name, auth_mode=AUTH_MODE_DATABRICKS, session=session)

    # Local mode: only the session cookie counts.
    session = store.get(token)
    if session is None:
        if token:
            clear_session_cookie(request)  # expired or unknown: tidy up the browser
        raise HTTPException(status_code=401, detail=MSG_NOT_SIGNED_IN)
    return CurrentUser(name=session.user_name, auth_mode=AUTH_MODE_LOCAL, session=session)
