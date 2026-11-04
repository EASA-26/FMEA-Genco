"""The two heavy operations the API calls: build a report and render its PDF.

The parser (`backend.report.builder`) and the PDF renderer (`backend.pdf.render`)
are imported only when first used. That keeps the API importable and testable
on its own, and lets tests pass a replacement object with the same three
methods to `create_app(services=...)`.
"""
from __future__ import annotations

from backend.report.models import Report


class ReportServices:
    """Default implementation backed by the real parser and PDF renderer."""

    def build_report(self, data: bytes, filename: str) -> Report:
        from backend.report.builder import build_report

        return build_report(data, filename)

    def render_pdf(self, report: Report) -> bytes:
        from backend.pdf.render import render_pdf

        return render_pdf(report)

    def open_error_message(self, exc: BaseException) -> str | None:
        """The plain-language message if ``exc`` means "this file is not a readable workbook".

        Returns None for any other exception, which the API then treats as an
        unexpected server error.
        """
        try:
            from backend.report.builder import WorkbookOpenError
        except ImportError:
            return None
        if not isinstance(exc, WorkbookOpenError):
            return None
        return workbook_error_text(exc)


# Used when a WorkbookOpenError carries no message of its own.
DEFAULT_OPEN_ERROR_MESSAGE = (
    "This file could not be opened as an Excel workbook. Save it as .xlsx in Excel and try again."
)


def workbook_error_text(exc: BaseException) -> str:
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    text = str(exc).strip()
    return text or DEFAULT_OPEN_ERROR_MESSAGE
