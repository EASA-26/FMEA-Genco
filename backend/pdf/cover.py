"""Cover page, ported from the approved design (design-preview/front_page_preview.py).

Geometry, colours, motif, logo card, title lines and the blank signing cards are
kept exactly as approved; only the Station and Date of Analysis values come from
the report. The page is drawn straight onto the canvas by the cover template.
"""
from __future__ import annotations

import math
from functools import lru_cache

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics

from backend.pdf.fonts import SANS, SANS_BOLD
from backend.pdf.styles import A4_PORTRAIT
from backend.pdf.text import truncate_to_width
from backend.settings import ASSETS_DIR

LOGO_PATH = ASSETS_DIR / "tnb-genco-logo.png"

W, H = A4_PORTRAIT
MARGIN = 44

# Palette taken from the reference cover (deep blue -> light cyan diagonal)
GRAD_TOP_LEFT = HexColor("#1A5A9A")
GRAD_MID = HexColor("#2379B3")
GRAD_BOTTOM_RIGHT = HexColor("#52BAD8")
LABEL_BLUE = HexColor("#1A5A9A")
RULE_GREY = HexColor("#9DB7CF")

BRAND_LINE = "ALCM - Maintenance Strategy"
TITLE_LINES = ("Failure Mode Effect", "Analysis (FMEA)", "Report")

# Signing cards (bottom of the page)
SIGNATURE_LABELS = ("PREPARED BY:", "APPROVED BY:")
SIGNATURE_GAP = 16
SIGNATURE_BOX_H = 104
SIGNATURE_Y = 38
SIGNATURE_BOX_W = (W - 2 * MARGIN - SIGNATURE_GAP) / 2
SIGNATURE_RULE_OFFSET = 33          # rule under the label, measured down from the card top

# Detail rows (Station / Date of Analysis)
DETAIL_SIZE = 13
DETAIL_LEADING = 17
DETAIL_ROW_GAP = 4
DETAIL_MIN_SIZE = 9
DETAIL_BOTTOM_LIMIT = SIGNATURE_Y + SIGNATURE_BOX_H + 28   # keep clear of the signing cards


def signature_box_rects() -> list[tuple[float, float, float, float]]:
    """(x, y, width, height) of each signing card in PDF coordinates (origin bottom-left)."""
    return [
        (MARGIN + i * (SIGNATURE_BOX_W + SIGNATURE_GAP), SIGNATURE_Y, SIGNATURE_BOX_W, SIGNATURE_BOX_H)
        for i in range(len(SIGNATURE_LABELS))
    ]


@lru_cache(maxsize=1)
def _logo() -> ImageReader:
    return ImageReader(str(LOGO_PATH))


def draw_background(c) -> None:
    c.saveState()
    p = c.beginPath()
    p.rect(0, 0, W, H)
    c.clipPath(p, stroke=0, fill=0)
    c.linearGradient(0, H, W, 0, (GRAD_TOP_LEFT, GRAD_MID, GRAD_BOTTOM_RIGHT),
                     positions=(0, 0.5, 1), extend=True)
    c.restoreState()


def draw_diagnostic_motif(c) -> None:
    """Subtle engineering visuals: fading dot grid + concentric gauge rings."""
    cx, cy = W - 18, 372  # focal point, partly off the right edge
    c.saveState()
    p = c.beginPath()
    p.rect(0, 0, W, H)
    c.clipPath(p, stroke=0, fill=0)

    # Dot grid that fades out with distance from the focal point
    step = 16
    c.setFillColor(white)
    for gx in range(int(step / 2), int(W), step):
        for gy in range(int(step / 2), int(H), step):
            d = math.hypot(gx - cx, gy - cy)
            a = max(0.0, 0.26 * (1 - d / 330))
            a = round(a / 0.02) * 0.02
            if a <= 0:
                continue
            c.setFillAlpha(a)
            c.circle(gx, gy, 0.65, stroke=0, fill=1)

    # Concentric rings
    c.setStrokeColor(white)
    c.setLineWidth(0.6)
    for r, a in ((62, 0.16), (118, 0.12), (176, 0.09), (236, 0.06)):
        c.setStrokeAlpha(a)
        c.circle(cx, cy, r, stroke=1, fill=0)

    # Tick scale on the second ring
    c.setStrokeAlpha(0.18)
    for deg in range(0, 360, 5):
        rad = math.radians(deg)
        r0 = 118
        r1 = r0 + (8 if deg % 30 == 0 else 4)
        c.line(cx + r0 * math.cos(rad), cy + r0 * math.sin(rad),
               cx + r1 * math.cos(rad), cy + r1 * math.sin(rad))

    # Gauge arc accent
    c.setLineWidth(2.2)
    c.setLineCap(1)
    c.setStrokeAlpha(0.24)
    c.arc(cx - 176, cy - 176, cx + 176, cy + 176, startAng=118, extent=58)

    # Cross-hair
    c.setLineWidth(0.5)
    c.setStrokeAlpha(0.07)
    c.line(cx - 250, cy, cx + 20, cy)
    c.line(cx, cy - 250, cx, cy + 250)
    c.restoreState()


def draw_header(c) -> None:
    # Logo card (top right)
    card_w, card_h = 136, 60
    card_x, card_y = W - MARGIN - card_w, H - 40 - card_h
    c.saveState()
    c.setFillColor(white)
    c.setFillAlpha(0.97)
    c.roundRect(card_x, card_y, card_w, card_h, 9, stroke=0, fill=1)
    c.restoreState()
    logo = _logo()
    lw, lh = logo.getSize()
    draw_h = 42
    draw_w = draw_h * lw / lh
    c.drawImage(logo, card_x + (card_w - draw_w) / 2, card_y + (card_h - draw_h) / 2,
                width=draw_w, height=draw_h, mask="auto")

    # Brand mark + line (top left), vertically centred on the logo card
    mid_y = card_y + card_h / 2
    s = 30
    mx, my = MARGIN, mid_y - s / 2
    c.saveState()
    c.setFillColor(white)
    c.setFillAlpha(0.14)
    c.setStrokeColor(white)
    c.setStrokeAlpha(0.45)
    c.setLineWidth(0.8)
    c.roundRect(mx, my, s, s, 7, stroke=1, fill=1)
    # diagnostic pulse glyph
    c.setStrokeAlpha(1)
    c.setLineWidth(1.5)
    c.setLineCap(1)
    c.setLineJoin(1)
    pts = [(5, 15), (10.5, 15), (13, 20.5), (16.5, 8.5), (19.5, 15), (25, 15)]
    path = c.beginPath()
    path.moveTo(mx + pts[0][0], my + pts[0][1])
    for x, y in pts[1:]:
        path.lineTo(mx + x, my + y)
    c.drawPath(path, stroke=1, fill=0)
    c.restoreState()

    c.setFillColor(white)
    c.setFont(SANS_BOLD, 11)
    c.drawString(mx + s + 10, mid_y - 4, BRAND_LINE)


def _wrap_value(value: str, font_name: str, size: float, max_w: float) -> list[str]:
    """Word-wrap like the approved design; a single word wider than the value
    column (e.g. a long name without spaces) is broken between characters so it
    never runs off the page."""
    lines = []
    for line in simpleSplit(value, font_name, size, max_w):
        if pdfmetrics.stringWidth(line, font_name, size) <= max_w:
            lines.append(line)
            continue
        current = ""
        for char in line:
            if current and pdfmetrics.stringWidth(current + char, font_name, size) > max_w:
                lines.append(current.rstrip())
                current = char.lstrip()
            else:
                current += char
        if current:
            lines.append(current)
    return lines


def _layout_detail_rows(rows, x, y, max_w):
    """Choose a type size so the rows fit above the signing cards.

    Returns (size, leading, [(label, [value lines])]). The approved 13 pt is used
    whenever it fits; very long values step down to 9 pt and, only as a last
    resort, the value is shortened with an ellipsis (the station name also appears
    in every page header).
    """
    available = y - DETAIL_BOTTOM_LIMIT
    size = DETAIL_SIZE
    while True:
        leading = DETAIL_LEADING * size / DETAIL_SIZE
        label_w = max(pdfmetrics.stringWidth(label, SANS, size) for label, _ in rows)
        value_x = x + label_w + 6 + pdfmetrics.stringWidth(":", SANS, size) + 7
        value_w = max_w - (value_x - x)
        laid = [(label, _wrap_value(value, SANS_BOLD, size, value_w) or [""]) for label, value in rows]
        needed = sum(len(lines) * leading + DETAIL_ROW_GAP for _, lines in laid)
        if needed <= available or size <= DETAIL_MIN_SIZE:
            break
        size -= 1

    if needed > available:
        max_lines = max(1, int((available - DETAIL_ROW_GAP * len(laid)) // leading) - (len(laid) - 1))
        label, lines = laid[0]
        if len(lines) > max_lines:
            kept = lines[:max_lines]
            kept[-1] = truncate_to_width(kept[-1] + "…", SANS_BOLD, size, value_w)
            laid[0] = (label, kept)
    return size, leading, laid


def draw_detail_rows(c, x, y, rows, max_w) -> float:
    """Label / colon / value rows. Labels are left-aligned, the colons share one
    column and values start at the same x; long values wrap under the value.
    Returns the next y."""
    size, leading, laid = _layout_detail_rows(rows, x, y, max_w)
    label_w = max(pdfmetrics.stringWidth(label, SANS, size) for label, _ in laid)
    colon_x = x + label_w + 6
    value_x = colon_x + pdfmetrics.stringWidth(":", SANS, size) + 7
    for label, lines in laid:
        c.setFont(SANS, size)
        c.drawString(x, y, label)
        c.drawString(colon_x, y, ":")
        c.setFont(SANS_BOLD, size)
        for line in lines:
            c.drawString(value_x, y, line)
            y -= leading
        y -= DETAIL_ROW_GAP
    return y


def draw_title_block(c, station_name: str, analysis_date_text: str) -> None:
    x = MARGIN
    y = H - 178
    c.setFillColor(white)
    c.setFont(SANS_BOLD, 40)
    leading = 44
    for line in TITLE_LINES:
        c.drawString(x, y, line)
        y -= leading

    # Station, then Date of Analysis below it
    y -= 12
    draw_detail_rows(c, x, y, [("Station", station_name), ("Date of Analysis", analysis_date_text)],
                     max_w=W - 2 * MARGIN - 40)


def draw_signature_boxes(c) -> None:
    """White signing cards: blank, legible for ink or digital signatures."""
    for (x, y, box_w, box_h), label in zip(signature_box_rects(), SIGNATURE_LABELS):
        c.saveState()
        c.setFillColor(white)
        c.setFillAlpha(0.97)
        c.roundRect(x, y, box_w, box_h, 9, stroke=0, fill=1)

        c.setFillAlpha(1)
        c.setFillColor(LABEL_BLUE)
        t = c.beginText(x + 14, y + box_h - 22)
        t.setFont(SANS_BOLD, 8.5)
        t.setCharSpace(0.6)
        t.textOut(label)
        c.drawText(t)

        c.setStrokeColor(RULE_GREY)
        c.setLineWidth(0.6)
        c.line(x + 14, y + box_h - SIGNATURE_RULE_OFFSET, x + box_w - 14, y + box_h - SIGNATURE_RULE_OFFSET)
        c.restoreState()


def draw_cover(c, station_name: str, analysis_date_text: str) -> None:
    c.saveState()
    draw_background(c)
    draw_diagnostic_motif(c)
    draw_header(c)
    draw_title_block(c, (station_name or "").replace("\n", " "), analysis_date_text or "")
    draw_signature_boxes(c)
    c.restoreState()
