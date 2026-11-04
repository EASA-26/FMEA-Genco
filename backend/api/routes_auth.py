"""Sign in, sign out and "who am I" endpoints (``/api/auth``)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.auth.service import (
    AUTH_MODE_LOCAL,
    MSG_LOGIN_FAILED,
    MSG_LOGIN_NOT_USED,
    MSG_LOGIN_RATE_LIMITED,
    CurrentUser,
    app_settings,
    clear_session_cookie,
    client_host,
    credentials_match,
    login_limiter,
    require_user,
    session_store,
    set_session_cookie,
)

logger = logging.getLogger("fmea.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


def _features(request: Request) -> dict:
    """Optional features the browser may offer (see backend.mail.outlook)."""
    return {"outlook_email": request.app.state.outlook.available(app_settings(request))}


def _user_payload(request: Request, name: str, auth_mode: str) -> dict:
    return {"user": {"name": name}, "auth_mode": auth_mode, "features": _features(request)}


@router.post("/login")
async def login(body: LoginRequest, request: Request) -> dict:
    settings = app_settings(request)
    if settings.auth_mode != AUTH_MODE_LOCAL:
        raise HTTPException(status_code=400, detail=MSG_LOGIN_NOT_USED)

    limiter = login_limiter(request)
    client = client_host(request)
    wait_seconds = limiter.begin_attempt(body.username, client)
    if wait_seconds:
        logger.warning("Sign-in temporarily blocked after repeated failures (client %s).", client)
        raise HTTPException(
            status_code=429,
            detail=MSG_LOGIN_RATE_LIMITED,
            headers={"Retry-After": str(wait_seconds)},
        )

    # scrypt is deliberately slow: keep it off the event loop. The attempt is
    # already counted as a failure; a correct password clears the count.
    if not await run_in_threadpool(credentials_match, settings, body.username, body.password):
        raise HTTPException(status_code=401, detail=MSG_LOGIN_FAILED)
    limiter.reset(body.username, client)

    store = session_store(request)
    # Always start a fresh session on sign-in (a token set before sign-in is never reused).
    store.destroy(request.cookies.get(settings.cookie_name))
    session = store.create(settings.admin_username)
    set_session_cookie(request, session.token)
    return _user_payload(request, session.user_name, AUTH_MODE_LOCAL)


@router.post("/logout", status_code=204)
async def logout(request: Request, user: CurrentUser = Depends(require_user)) -> Response:
    session_store(request).destroy(user.session.token)
    clear_session_cookie(request)
    return Response(status_code=204)


@router.get("/me")
async def me(request: Request, user: CurrentUser = Depends(require_user)) -> dict:
    return _user_payload(request, user.name, user.auth_mode)
