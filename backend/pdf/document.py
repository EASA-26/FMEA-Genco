"""Document template: cover / A4 portrait / A3 landscape pages, running header and
"Page X of Y" footer.
"""
from __future__ import annotations

from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

from backend.pdf import styles
from backend.pdf.cover import draw_cover
from backend.pdf.fonts import SANS
from backend.pdf.text import truncate_to_width

COVER = "cover"
A4 = "a4"
A3 = "a3"

REPORT_TITLE = "Failure Mode Effect Analysis (FMEA) Report"
HEADER_FONT_SIZE = 7.5
FOOTER_FONT_SIZE = 7.5


def header_text(station: str) -> str:
    station = " ".join((station or "").split())
    return f"FMEA Report · {station}" if station else "FMEA Report"


class NumberedCanvas(Canvas):
    """Canvas that holds pages back until the end so each footer can say "Page X of Y".

    Page size, header text and side margin are read from each page's own saved
    state, because a mixed A4/A3 document changes page size between pages (the
    document template's own `pagesize` stays A4).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):  # noqa: N802 (ReportLab API name)
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_furniture(total)
            super().showPage()
        super().save()

    def _draw_page_furniture(self, total: int) -> None:
        text = getattr(self, "fmea_header", None)
        if text is None:  # cover page: no header or footer
            return
        width, height = self._pagesize
        side = getattr(self, "fmea_side_margin", styles.A4_SIDE_MARGIN)
        self.saveState()
        self.setFillColor(styles.MUTED)
        self.setFont(SANS, HEADER_FONT_SIZE)
        self.drawString(side, height - styles.HEADER_BASELINE_FROM_TOP,
                        truncate_to_width(text, SANS, HEADER_FONT_SIZE, width - 2 * side))
        self.setStrokeColor(styles.HAIRLINE)
        self.setLineWidth(0.6)
        rule_y = height - styles.HEADER_RULE_FROM_TOP
        self.line(side, rule_y, width - side, rule_y)
        self.setFont(SANS, FOOTER_FONT_SIZE)
        self.drawRightString(width - side, styles.FOOTER_BASELINE, f"Page {self._pageNumber} of {total}")
        self.restoreState()


def _page_template(template_id: str, pagesize, side_margin: float, on_page) -> PageTemplate:
    frame = Frame(side_margin, styles.BOTTOM_MARGIN, pagesize[0] - 2 * side_margin, styles.FRAME_HEIGHT,
                  id=f"{template_id}-body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    return PageTemplate(id=template_id, frames=[frame], pagesize=pagesize, onPage=on_page)


def build_doc_template(buffer, station: str, analysis_date_text: str) -> BaseDocTemplate:
    """Document with the three page templates. The cover template is first, so
    page 1 is the cover; the story switches templates with NextPageTemplate."""
    running_header = header_text(station)

    def on_cover(canvas, doc):
        canvas.fmea_header = None
        draw_cover(canvas, station, analysis_date_text)

    def on_body_page(side_margin):
        def _on_page(canvas, doc):
            canvas.fmea_header = running_header
            canvas.fmea_side_margin = side_margin
        return _on_page

    doc = BaseDocTemplate(
        buffer,
        pagesize=styles.A4_PORTRAIT,
        leftMargin=styles.A4_SIDE_MARGIN,
        rightMargin=styles.A4_SIDE_MARGIN,
        topMargin=styles.TOP_MARGIN,
        bottomMargin=styles.BOTTOM_MARGIN,
        title=REPORT_TITLE,
        subject=" ".join((station or "").split()),
        author="",
        creator="FMEA Report Generator",
        initialFontName=SANS,
        initialFontSize=9,
    )
    doc.addPageTemplates([
        _page_template(COVER, styles.A4_PORTRAIT, styles.A4_SIDE_MARGIN, on_cover),
        _page_template(A4, styles.A4_PORTRAIT, styles.A4_SIDE_MARGIN, on_body_page(styles.A4_SIDE_MARGIN)),
        _page_template(A3, styles.A3_LANDSCAPE, styles.A3_SIDE_MARGIN, on_body_page(styles.A3_SIDE_MARGIN)),
    ])
    return doc
