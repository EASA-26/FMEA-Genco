"""Shared helpers for the API tests. Contains no tests itself.

All data here is SYNTHETIC. The real parser and PDF renderer are replaced by
`FakeServices`, injected through `create_app(services=...)`, and PowerShell /
Outlook by `FakeRunner`, injected through `create_app(outlook=...)`: tests
never start PowerShell or Outlook.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from backend.auth.passwords import hash_password
from backend.mail.outlook import ENV_ATTACHMENT, OutlookMailer, RunResult
from backend.main import create_app
from backend.report.models import Issue, Report
from backend.settings import Settings

# Tests sign in with their own SYNTHETIC account, never the development password.
SYNTHETIC_PASSWORD = "SYNTHETIC-test-password"
SYNTHETIC_PASSWORD_HASH = hash_password(SYNTHETIC_PASSWORD)
SYNTHETIC_PDF = b"%PDF-1.4\n% SYNTHETIC test PDF\n"
SYNTHETIC_OPEN_ERROR = "SYNTHETIC: this file could not be opened as an Excel workbook."
# A folder that never exists, so tests never serve a real frontend build.
MISSING_DIST = Path(__file__).resolve().parent / "SYNTHETIC_no_frontend_dist"
# Not "win32", so "Email the PDF" is unavailable unless a test asks for Windows.
SYNTHETIC_PLATFORM = "SYNTHETIC-os"
# The Host header TestClient sends. A locally run app answers only to loopback
# names, so test apps also accept this one (create_app(extra_local_hosts=...)).
TEST_CLIENT_HOSTS = ("testserver",)


def fast_password_hash(password: str = SYNTHETIC_PASSWORD) -> str:
    """A valid but deliberately cheap scrypt hash, for tests that sign in hundreds of times."""
    salt = b"SYNTHETIC-salt16"
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2, r=1, p=1, dklen=32)
    return f"scrypt$2$1$1${base64.b64encode(salt).decode()}${base64.b64encode(key).decode()}"


def make_settings(**overrides) -> Settings:
    base = Settings(
        auth_mode="local",
        admin_username="admin",
        admin_password_hash=SYNTHETIC_PASSWORD_HASH,
        session_idle_minutes=60,
        max_sessions=200,
        max_upload_mb=20,
        cookie_secure=False,
        cookie_name="fmea_session",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
    return replace(base, **overrides)


def make_report(
    *,
    errors: int = 0,
    station: str = "SYNTHETIC Station",
    source_filename: str = "SYNTHETIC_workbook.xlsx",
    pdf_filename: str = "FMEA_Report_SYNTHETIC_Station_2026-01-15.pdf",
) -> Report:
    issues = [
        Issue(severity="error", code="SYNTHETIC_ERROR", message=f"SYNTHETIC error {n + 1}")
        for n in range(errors)
    ]
    issues.append(Issue(severity="warning", code="SYNTHETIC_WARNING", message="SYNTHETIC warning"))
    return Report(
        source_filename=source_filename,
        station=station,
        analysis_date=date(2026, 1, 15),
        analysis_date_text="15 January 2026",
        issues=issues,
        can_export=errors == 0,
        pdf_filename=pdf_filename,
        generated_at=datetime(2026, 1, 15, 9, 30),
    )


class FakeWorkbookOpenError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _assert_not_on_event_loop() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise AssertionError("heavy work ran on the event loop instead of the threadpool")


class FakeServices:
    """Stands in for backend.report.builder / backend.pdf.render.

    * data starting with b"NOT-A-WORKBOOK" -> FakeWorkbookOpenError
    * otherwise returns ``next_report`` (or a clean SYNTHETIC report)
    """

    def __init__(self) -> None:
        self.build_calls: list[tuple[str, bytes]] = []
        self.render_calls = 0
        self.next_report: Report | None = None
        self.build_error: BaseException | None = None
        self.render_error: BaseException | None = None

    def build_report(self, data: bytes, filename: str) -> Report:
        _assert_not_on_event_loop()
        self.build_calls.append((filename, data))
        if data.startswith(b"NOT-A-WORKBOOK"):
            raise FakeWorkbookOpenError(SYNTHETIC_OPEN_ERROR)
        if self.build_error is not None:
            raise self.build_error
        if self.next_report is not None:
            return self.next_report
        return make_report(source_filename=filename)

    def render_pdf(self, report: Report) -> bytes:
        _assert_not_on_event_loop()
        self.render_calls += 1
        if self.render_error is not None:
            raise self.render_error
        return SYNTHETIC_PDF + f"% render {self.render_calls}\n".encode()

    def open_error_message(self, exc: BaseException) -> str | None:
        return exc.message if isinstance(exc, FakeWorkbookOpenError) else None


@dataclass
class RunnerCall:
    args: list[str]
    env: dict[str, str]
    timeout: float
    attachment: Path
    attachment_bytes: bytes | None      # the file as PowerShell would have found it


class FakeRunner:
    """Stands in for the PowerShell runner of `backend.mail.outlook`.

    Records each call (and the attachment file as it was during the call),
    then returns ``returncode`` / ``stderr``, raises ``error``, or first calls
    ``on_run`` (e.g. to block until a test releases it).
    """

    def __init__(
        self,
        returncode: int = 0,
        stderr: str = "",
        error: BaseException | None = None,
        on_run: Callable[[], None] | None = None,
    ) -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.error = error
        self.on_run = on_run
        self.calls: list[RunnerCall] = []

    def __call__(self, args, env, timeout) -> RunResult:
        _assert_not_on_event_loop()
        attachment = Path(env[ENV_ATTACHMENT])
        self.calls.append(
            RunnerCall(
                args=list(args),
                env=dict(env),
                timeout=timeout,
                attachment=attachment,
                attachment_bytes=attachment.read_bytes() if attachment.is_file() else None,
            )
        )
        if self.on_run is not None:
            self.on_run()
        if self.error is not None:
            raise self.error
        return RunResult(self.returncode, self.stderr)


def make_outlook(
    runner: FakeRunner | None = None,
    platform: str = SYNTHETIC_PLATFORM,
    lock: threading.Lock | None = None,
    classic_ready: bool = True,
) -> OutlookMailer:
    """An Outlook launcher that never starts PowerShell, with its own lock
    (so one test holding the lock never affects another). ``classic_ready``
    stands in for the registry check (classic Outlook installed and in use),
    so tests never depend on which Outlook this PC has."""
    return OutlookMailer(
        runner=runner if runner is not None else FakeRunner(),
        platform=platform,
        lock=lock if lock is not None else threading.Lock(),
        classic_ready=lambda: classic_ready,
    )


def make_client(
    settings: Settings | None = None,
    services: FakeServices | None = None,
    frontend_dist: Path | None = None,
    outlook: OutlookMailer | None = None,
    extra_local_hosts: tuple[str, ...] = TEST_CLIENT_HOSTS,
    **client_kwargs,
) -> TestClient:
    app = create_app(
        settings=settings or make_settings(),
        services=services if services is not None else FakeServices(),
        frontend_dist=frontend_dist if frontend_dist is not None else MISSING_DIST,
        outlook=outlook if outlook is not None else make_outlook(),
        extra_local_hosts=extra_local_hosts,
    )
    return TestClient(app, **client_kwargs)


def login(client: TestClient, username: str = "admin", password: str = SYNTHETIC_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def upload(
    client: TestClient,
    data: bytes = b"SYNTHETIC workbook bytes",
    filename: str = "SYNTHETIC_workbook.xlsx",
    **kwargs,
):
    return client.post(
        "/api/workbook",
        files={"file": (filename, data, "application/octet-stream")},
        **kwargs,
    )


def cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def cookie_value(response, name: str = "fmea_session") -> str | None:
    for header in cookie_headers(response):
        first = header.split(";", 1)[0]
        key, _, value = first.partition("=")
        if key.strip() == name:
            return value.strip().strip('"')
    return None


def multipart_body(
    parts: list[tuple[str, str | None, bytes]], boundary: str = "SYNTHETICboundary42"
) -> tuple[bytes, str]:
    """Build a multipart/form-data body: parts are (field name, filename or None, content)."""
    chunks = []
    for name, filename, content in parts:
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: {disposition}\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n".encode()
            + content
            + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
