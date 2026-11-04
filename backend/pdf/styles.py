"""Page geometry, colours and paragraph styles shared by every PDF section."""
from __future__ import annotations

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm

from backend.pdf.fonts import SANS, SANS_BOLD

# --------------------------------------------------------------------------- #
# Page geometry (points). A4 portrait and A3 landscape share the same height,
# so every body frame has the same height.
# --------------------------------------------------------------------------- #
A4_PORTRAIT = A4
A3_LANDSCAPE = landscape(A3)

TOP_MARGIN = 20 * mm
BOTTOM_MARGIN = 16 * mm
A4_SIDE_MARGIN = 15 * mm
A3_SIDE_MARGIN = 12 * mm

FRAME_HEIGHT = A4_PORTRAIT[1] - TOP_MARGIN - BOTTOM_MARGIN
A4_FRAME_WIDTH = A4_PORTRAIT[0] - 2 * A4_SIDE_MARGIN
A3_FRAME_WIDTH = A3_LANDSCAPE[0] - 2 * A3_SIDE_MARGIN

HEADER_BASELINE_FROM_TOP = 12 * mm
HEADER_RULE_FROM_TOP = 14 * mm
FOOTER_BASELINE = 9 * mm

# --------------------------------------------------------------------------- #
# Colours: white, print-friendly pages with restrained blue.
# --------------------------------------------------------------------------- #
PRIMARY = HexColor("#1A5A9A")
HEADING_INK = HexColor("#0A2340")
BODY_INK = HexColor("#1F2933")
MUTED_HEX = "#5B6770"
MUTED = HexColor(MUTED_HEX)
TABLE_HEADER_FILL = HexColor("#1E6FBF")
ZEBRA = HexColor("#F4F8FC")
HAIRLINE = HexColor("#D5E1EC")
RULE = HexColor("#A9BFD4")        # slightly stronger line: table outline, group separators
CARD_FILL = HexColor("#F4F8FC")
WHITE = white

# --------------------------------------------------------------------------- #
# Type scale
# --------------------------------------------------------------------------- #
A3_TABLE_FONT_SIZE = 7.5
A3_TABLE_LEADING = 9.0
A4_TABLE_FONT_SIZE = 8.0
A4_TABLE_LEADING = 10.0


def _style(name: str, **kwargs) -> ParagraphStyle:
    base = dict(fontName=SANS, fontSize=9, leading=12, textColor=BODY_INK,
                spaceBefore=0, spaceAfter=0)
    base.update(kwargs)
    return ParagraphStyle(name, **base)


SECTION_TITLE = _style("SectionTitle", fontName=SANS_BOLD, fontSize=17, leading=21,
                       textColor=HEADING_INK)
HEADING_2 = _style("Heading2", fontName=SANS_BOLD, fontSize=11.5, leading=14.5,
                   textColor=HEADING_INK, spaceBefore=12, spaceAfter=6)
HEADING_3 = _style("Heading3", fontName=SANS_BOLD, fontSize=9.5, leading=12,
                   textColor=PRIMARY, spaceBefore=8, spaceAfter=4)
BODY = _style("Body")
NOTE = _style("Note", fontSize=8.5, leading=11, textColor=MUTED)
EMPTY_NOTE = _style("EmptyNote", fontSize=9, leading=12, textColor=MUTED, spaceBefore=2, spaceAfter=4)

KEY_LABEL = _style("KeyLabel", fontSize=9.5, leading=12.5, textColor=MUTED)
KEY_VALUE = _style("KeyValue", fontName=SANS_BOLD, fontSize=9.5, leading=12.5, textColor=HEADING_INK)


def table_cell_style(font_size: float, leading: float, align: int = TA_LEFT,
                     bold: bool = False, color=BODY_INK) -> ParagraphStyle:
    return _style(
        f"Cell-{font_size}-{align}-{int(bold)}",
        fontName=SANS_BOLD if bold else SANS,
        fontSize=font_size,
        leading=leading,
        alignment=align,
        textColor=color,
    )


def table_header_style(font_size: float, leading: float) -> ParagraphStyle:
    return table_cell_style(font_size, leading, align=TA_CENTER, bold=True, color=WHITE)


A3_CELL = table_cell_style(A3_TABLE_FONT_SIZE, A3_TABLE_LEADING)
A3_CELL_CENTRED = table_cell_style(A3_TABLE_FONT_SIZE, A3_TABLE_LEADING, align=TA_CENTER)
A3_HEADER = table_header_style(A3_TABLE_FONT_SIZE, A3_TABLE_LEADING)

A4_CELL = table_cell_style(A4_TABLE_FONT_SIZE, A4_TABLE_LEADING)
A4_CELL_CENTRED = table_cell_style(A4_TABLE_FONT_SIZE, A4_TABLE_LEADING, align=TA_CENTER)
A4_CELL_RIGHT = table_cell_style(A4_TABLE_FONT_SIZE, A4_TABLE_LEADING, align=TA_RIGHT)
A4_HEADER = table_header_style(A4_TABLE_FONT_SIZE, A4_TABLE_LEADING)
