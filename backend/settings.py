"""Runtime settings, read from environment variables only.

Locally, values may also come from a `.env` file in the project root (simple
KEY=VALUE lines; real environment variables win). On Databricks Apps the same
names are set in app.yaml (secrets via `valueFrom`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BACKEND_DIR / "assets"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

# scrypt hash of the initial development password ("fmea26"), used only when
# ADMIN_PASSWORD_HASH is not set. Generate a new one with tools/hash_password.py.
DEFAULT_ADMIN_PASSWORD_HASH = (
    "scrypt$16384$8$1$uQ0dsT8pnCOFG0gbrulDHA==$51KrBcKRZAZXfwo16WeMbm44NkexOPcANC3+4Q1f0io="
)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    auth_mode: str                 # "local" (username/password) or "databricks" (forwarded identity)
    admin_username: str
    admin_password_hash: str
    session_idle_minutes: int
    max_sessions: int
    max_upload_mb: int
    cookie_secure: bool
    cookie_name: str
    host: str
    port: int
    log_level: str
    # "Email the PDF" through classic Outlook on this PC: "auto" (only when the
    # app runs on the user's own Windows computer), "on" or "off".
    outlook_email: str = "auto"


@lru_cache
def get_settings() -> Settings:
    _load_dotenv(PROJECT_ROOT / ".env")
    env = os.environ
    return Settings(
        auth_mode=env.get("AUTH_MODE", "local").strip().lower(),
        admin_username=env.get("ADMIN_USERNAME", "admin"),
        admin_password_hash=env.get("ADMIN_PASSWORD_HASH", DEFAULT_ADMIN_PASSWORD_HASH),
        session_idle_minutes=int(env.get("SESSION_IDLE_MINUTES", "60")),
        max_sessions=int(env.get("MAX_SESSIONS", "200")),
        max_upload_mb=int(env.get("MAX_UPLOAD_MB", "20")),
        cookie_secure=_bool("COOKIE_SECURE", False),
        cookie_name=env.get("SESSION_COOKIE_NAME", "fmea_session"),
        host=env.get("HOST", "127.0.0.1"),
        port=int(env.get("DATABRICKS_APP_PORT") or env.get("PORT") or "8000"),
        log_level=env.get("LOG_LEVEL", "info"),
        outlook_email=env.get("OUTLOOK_EMAIL", "auto").strip().lower() or "auto",
    )
