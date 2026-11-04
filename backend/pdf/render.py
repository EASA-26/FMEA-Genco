"""Entry point: render a `Report` to PDF bytes, entirely in memory."""
from __future__ import annotations

import io
import threading

from backend.pdf.document import NumberedCanvas, build_doc_template
from backend.pdf.fonts import register_fonts
from backend.pdf.sections import build_story
from backend.report.models import Report

# ReportLab keeps some process-wide state (font subsets, parser caches), so one
# document is laid out at a time. Rendering is fast and cached per session by the API.
_render_lock = threading.Lock()


def render_pdf(report: Report) -> bytes:
    """Render the full report. Renders regardless of `report.can_export`; the API
    decides whether a report may be previewed or exported."""
    register_fonts()
    buffer = io.BytesIO()
    with _render_lock:
        doc = build_doc_template(buffer, report.station, report.analysis_date_text)
        doc.build(build_story(report), canvasmaker=NumberedCanvas)
    return buffer.getvalue()
