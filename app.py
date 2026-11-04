"""Start the FMEA Report Generator web server.

Locally:            python app.py          (http://127.0.0.1:8000 by default)
Databricks Apps:    started by app.yaml    (HOST=0.0.0.0, port from DATABRICKS_APP_PORT)

Settings come from environment variables or a local .env file; see .env.example.
"""
from __future__ import annotations

import logging
import sys

import uvicorn

from backend.auth.service import AUTH_MODE_DATABRICKS
from backend.settings import Settings, get_settings


def event_loop_option(platform: str = sys.platform) -> str:
    """uvicorn ``loop`` setting for this operating system.

    On Windows the default (Proactor) event loop stops listening for good when
    a browser drops a connection while it is being accepted ("Accept failed on
    a socket", WinError 64), leaving the app unreachable. The Selector loop
    does not have that problem and is ample for a single-user local server.
    Elsewhere (Databricks runs Linux) uvicorn's default is kept.
    """
    return "asyncio:SelectorEventLoop" if platform == "win32" else "auto"


def server_options(settings: Settings, platform: str = sys.platform) -> dict:
    """Keyword arguments for ``uvicorn.run``."""
    return {
        "host": settings.host,
        "port": settings.port,
        # One worker: sessions and reports are kept in this process's memory.
        "workers": 1,
        "loop": event_loop_option(platform),
        "log_level": settings.log_level.lower(),
        "server_header": False,
        # X-Forwarded-For / X-Forwarded-Proto are only meaningful behind the
        # Databricks proxy. Locally every browser connects from 127.0.0.1, which
        # uvicorn trusts by default, so honouring them would let any caller pick
        # its own client address and dodge the per-client sign-in limit.
        "proxy_headers": settings.auth_mode == AUTH_MODE_DATABRICKS,
    }


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run("backend.main:app", **server_options(settings))


if __name__ == "__main__":
    main()
