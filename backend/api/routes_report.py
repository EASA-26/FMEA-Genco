"""Workbook upload, report JSON, PDF and "Email the PDF" endpoints.

Each session holds at most one report (the last successful upload) and the PDF
rendered from it. Parsing and rendering are CPU-bound, so they run in the
threadpool and never block other requests. So does opening an Outlook email.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.api.upload import UploadRejected, read_single_file
from backend.auth.service import CurrentUser, app_settings, require_user, session_store
from backend.config.mapping import ACCEPTED_EXTENSIONS
from backend.mail.outlook import (
    OutlookBusy,
    OutlookFailed,
    OutlookMailer,
    RecipientError,
    email_intro_html,
    email_subject,
    parse_recipients,
    safe_attachment_name,
)
from backend.report.models import Report
from backend.sessions.store import Session, SessionStore

logger = logging.getLogger("fmea.report")

router = APIRouter(prefix="/api", tags=["report"])

MSG_NO_REPORT = "No workbook uploaded yet."
MSG_UPLOAD_SUPERSEDED = (
    "This upload was cancelled before it finished: the workbook was closed or another "
    "upload started. Upload the workbook again to continue."
)
MSG_EXPORT_BLOCKED = "Fix the errors listed before previewing or exporting."
MSG_PDF_FAILED = "The PDF could not be created. Please try again or contact support."
MSG_EMAIL_UNAVAILABLE = (
    "Outlook can only open the email here when the app runs on your own computer with the "
    "classic Outlook app. Download the PDF and attach it to an email instead."
)
MSG_OUTLOOK_FAILED = (
    "Outlook could not open a new email. Make sure Outlook is installed and signed in, "
    "or download the PDF and attach it yourself."
)
MSG_OUTLOOK_BUSY = "Outlook is still opening the previous email. Please wait a moment."

UPLOAD_FIELD = "file"
FALLBACK_PDF_FILENAME = "FMEA_Report.pdf"


def _services(request: Request):
    return request.app.state.services


def _outlook(request: Request) -> OutlookMailer:
    return request.app.state.outlook


def _report_response(report: Report) -> Response:
    # Serialised by pydantic directly (dates as ISO strings).
    return Response(content=report.model_dump_json(), media_type="application/json")


def _error_count(report: Report) -> int:
    return sum(1 for issue in report.issues if issue.severity == "error")


def _pdf_name(cleaned: str) -> str:
    cleaned = cleaned.strip(" .")
    if not cleaned:
        return FALLBACK_PDF_FILENAME
    if not cleaned.lower().endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def _safe_download_name(name: str) -> str:
    """Plain-ASCII name for ``filename="..."``: keeps the header well-formed whatever
    the report says the file is called."""
    return _pdf_name(re.sub(r"[^A-Za-z0-9._ -]", "_", name or ""))


def _readable_download_name(name: str) -> str:
    """The real name (accents, other scripts, quotes kept), minus control characters
    and folder separators; sent percent-encoded in ``filename*``."""
    return _pdf_name(re.sub(r"[\x00-\x1f\x7f/\\]", "_", name or ""))


def content_disposition(disposition: str, name: str) -> str:
    """``inline|attachment; filename="<ASCII name>"``, plus the RFC 5987/6266
    ``filename*=UTF-8''...`` form when the ASCII name had to change, so browsers
    save non-ASCII station names correctly."""
    fallback = _safe_download_name(name)
    header = f'{disposition}; filename="{fallback}"'
    readable = _readable_download_name(name)
    if readable != fallback:
        header += "; filename*=UTF-8''" + quote(readable, safe="!#$&+-.^_`|~")
    return header


# --------------------------------------------------------------------------- #
# Workbook
# --------------------------------------------------------------------------- #
@router.post("/workbook")
async def upload_workbook(request: Request, user: CurrentUser = Depends(require_user)) -> Response:
    settings = app_settings(request)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    store = session_store(request)
    # A discard (DELETE /api/workbook, sign-out) or a newer upload arriving while
    # this one is still being read means this result must not be kept.
    upload = store.begin_upload(user.session)
    try:
        received = await read_single_file(
            request.headers,
            request.stream(),
            field_name=UPLOAD_FIELD,
            max_bytes=max_bytes,
            extensions=ACCEPTED_EXTENSIONS,
        )
    except UploadRejected as rejected:
        raise HTTPException(status_code=rejected.status_code, detail=rejected.message) from None

    services = _services(request)
    try:
        report = await run_in_threadpool(services.build_report, received.data, received.filename)
    except Exception as exc:
        message = services.open_error_message(exc)
        if message is None:
            raise  # unexpected: the generic 500 handler logs it
        raise HTTPException(status_code=400, detail=message) from None

    # The browser gave up (Cancel, or the page was left): keep nothing, and keep
    # the previous report, which that page may still be showing.
    if await request.is_disconnected():
        raise HTTPException(status_code=409, detail=MSG_UPLOAD_SUPERSEDED)
    # Only a successful upload replaces the previous report (and its PDF).
    if not store.set_report(user.session, report, upload=upload):
        raise HTTPException(status_code=409, detail=MSG_UPLOAD_SUPERSEDED)
    return _report_response(report)


@router.delete("/workbook", status_code=204)
async def clear_workbook(request: Request, user: CurrentUser = Depends(require_user)) -> Response:
    session_store(request).clear_report(user.session)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
@router.get("/report")
async def get_report(request: Request, user: CurrentUser = Depends(require_user)) -> Response:
    report = session_store(request).get_report(user.session)
    if report is None:
        raise HTTPException(status_code=404, detail=MSG_NO_REPORT)
    return _report_response(report)


def _pdf_for_session(store: SessionStore, session: Session, services) -> tuple[Report | None, bytes | None]:
    """Return (report, pdf). pdf is None when there is no report or it has errors.

    Runs in the threadpool. The per-session lock means concurrent requests
    (preview and download together) render once and share the cached bytes.
    """
    with session.pdf_lock:
        report, version, cached = store.snapshot(session)
        if report is None or not report.can_export:
            return report, None
        if cached is not None:
            return report, cached
        pdf = services.render_pdf(report)
        store.cache_pdf(session, version, pdf)
        return report, pdf


@router.get("/report/pdf")
async def get_report_pdf(
    request: Request,
    download: bool = False,
    user: CurrentUser = Depends(require_user),
) -> Response:
    store = session_store(request)
    services = _services(request)
    try:
        report, pdf = await run_in_threadpool(_pdf_for_session, store, user.session, services)
    except Exception:
        logger.exception("PDF rendering failed.")
        raise HTTPException(status_code=500, detail=MSG_PDF_FAILED) from None

    if report is None:
        raise HTTPException(status_code=404, detail=MSG_NO_REPORT)
    if pdf is None:
        return JSONResponse(
            status_code=409,
            content={"detail": MSG_EXPORT_BLOCKED, "error_count": _error_count(report)},
        )

    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(disposition, report.pdf_filename),
            "Cache-Control": "no-store",
        },
    )


# --------------------------------------------------------------------------- #
# Email the PDF (classic Outlook on this PC)
# --------------------------------------------------------------------------- #
class EmailRequest(BaseModel):
    # Typed recipient list (may be empty); checked by parse_recipients.
    to: str = ""


@router.post("/report/email")
async def email_report_pdf(
    body: EmailRequest,
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> Response:
    """Open a new Outlook email with the PDF attached. Outlook shows it; the user sends it."""
    outlook = _outlook(request)
    if not outlook.available(app_settings(request)):
        raise HTTPException(status_code=501, detail=MSG_EMAIL_UNAVAILABLE)
    try:
        recipients = parse_recipients(body.to)
    except RecipientError as bad:
        raise HTTPException(status_code=400, detail=bad.message) from None

    # Same PDF as GET /api/report/pdf (the cached render is reused).
    store = session_store(request)
    try:
        report, pdf = await run_in_threadpool(_pdf_for_session, store, user.session, _services(request))
    except Exception:
        logger.exception("PDF rendering failed.")
        raise HTTPException(status_code=500, detail=MSG_PDF_FAILED) from None
    if report is None:
        raise HTTPException(status_code=404, detail=MSG_NO_REPORT)
    if pdf is None:
        return JSONResponse(
            status_code=409,
            content={"detail": MSG_EXPORT_BLOCKED, "error_count": _error_count(report)},
        )

    attachment = safe_attachment_name(report.pdf_filename)
    try:
        await run_in_threadpool(
            outlook.open_draft,
            recipients=recipients,
            subject=email_subject(report.station, report.analysis_date_text),
            intro_html=email_intro_html(report.station, report.analysis_date_text),
            pdf_bytes=pdf,
            attachment_name=attachment,
        )
    except OutlookBusy:
        raise HTTPException(status_code=429, detail=MSG_OUTLOOK_BUSY) from None
    except OutlookFailed:
        raise HTTPException(status_code=502, detail=MSG_OUTLOOK_FAILED) from None

    # Never log the addresses themselves.
    logger.info("Opened a new Outlook email with the PDF attached (%d recipient(s)).", len(recipients))
    return JSONResponse({"status": "opened", "recipients": recipients, "attachment": attachment})
