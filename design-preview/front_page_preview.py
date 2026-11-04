"""Front page (cover) preview for the FMEA Report PDF.

Design-approval prototype only. Once approved, this drawing code moves into the
backend PDF module and reads Station Name / Date of Analysis from the workbook.

Run:  python front_page_preview.py [output.pdf]
"""
import math
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
LOGO = HERE / "assets" / "tnb-genco-logo.png"

# Liberation Sans (SIL OFL): same letter widths as Arial, bundled so the PDF
# renders identically on Windows and Linux (Databricks).
FONTS = HERE / "assets" / "fonts"
pdfmetrics.registerFont(TTFont("Sans", str(FONTS / "LiberationSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Sans-Bold", str(FONTS / "LiberationSans-Bold.ttf")))

W, H = A4
MARGIN = 44

# Palette taken from the reference cover (deep blue -> light cyan diagonal)
GRAD_TOP_LEFT = HexColor("#1A5A9A")
GRAD_MID = HexColor("#2379B3")
GRAD_BOTTOM_RIGHT = HexColor("#52BAD8")
LABEL_BLUE = HexColor("#1A5A9A")
RULE_GREY = HexColor("#9DB7CF")

BRAND_LINE = "ALCM - Maintenance Strategy"
TITLE_LINES = ["Failure Mode Effect", "Analysis (FMEA)", "Report"]


def draw_background(c):
    c.saveState()
    p = c.beginPath()
    p.rect(0, 0, W, H)
    c.clipPath(p, stroke=0, fill=0)
    c.linearGradient(0, H, W, 0, (GRAD_TOP_LEFT, GRAD_MID, GRAD_BOTTOM_RIGHT),
                     positions=(0, 0.5, 1), extend=True)
    c.restoreState()


def draw_diagnostic_motif(c):
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


def draw_header(c):
    # Logo card (top right)
    card_w, card_h = 136, 60
    card_x, card_y = W - MARGIN - card_w, H - 40 - card_h
    c.saveState()
    c.setFillColor(white)
    c.setFillAlpha(0.97)
    c.roundRect(card_x, card_y, card_w, card_h, 9, stroke=0, fill=1)
    c.restoreState()
    logo = ImageReader(str(LOGO))
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
    c.setFont("Sans-Bold", 11)
    c.drawString(mx + s + 10, mid_y - 4, BRAND_LINE)


def format_analysis_date(value):
    """Written-out date, e.g. 17 September 2026 (no leading zero on the day)."""
    return f"{value.day} {value:%B %Y}"


def draw_detail_rows(c, x, y, rows, size=13, leading=17, row_gap=4, max_w=None):
    """Label / colon / value rows. Labels are left-aligned, the colons share one
    column and values start at the same x; long values wrap under the value.
    Returns the next y."""
    label_w = max(pdfmetrics.stringWidth(label, "Sans", size) for label, _ in rows)
    colon_x = x + label_w + 6
    value_x = colon_x + pdfmetrics.stringWidth(":", "Sans", size) + 7
    for label, value in rows:
        c.setFont("Sans", size)
        c.drawString(x, y, label)
        c.drawString(colon_x, y, ":")
        c.setFont("Sans-Bold", size)
        for line in simpleSplit(value, "Sans-Bold", size, max_w - (value_x - x)):
            c.drawString(value_x, y, line)
            y -= leading
        y -= row_gap
    return y


def draw_title_block(c, station_name, analysis_date):
    x = MARGIN
    y = H - 178
    c.setFillColor(white)
    c.setFont("Sans-Bold", 40)
    leading = 44
    for line in TITLE_LINES:
        c.drawString(x, y, line)
        y -= leading

    # Station, then Date of Analysis below it
    y -= 12
    draw_detail_rows(c, x, y, [("Station", station_name), ("Date of Analysis", analysis_date)],
                     max_w=W - 2 * MARGIN - 40)


def draw_signature_boxes(c):
    """White signing cards: blank, legible for ink or digital signatures."""
    gap = 16
    box_w = (W - 2 * MARGIN - gap) / 2
    box_h = 104
    y = 38
    for i, label in enumerate(("PREPARED BY:", "APPROVED BY:")):
        x = MARGIN + i * (box_w + gap)
        c.saveState()
        c.setFillColor(white)
        c.setFillAlpha(0.97)
        c.roundRect(x, y, box_w, box_h, 9, stroke=0, fill=1)

        c.setFillAlpha(1)
        c.setFillColor(LABEL_BLUE)
        t = c.beginText(x + 14, y + box_h - 22)
        t.setFont("Sans-Bold", 8.5)
        t.setCharSpace(0.6)
        t.textOut(label)
        c.drawText(t)

        c.setStrokeColor(RULE_GREY)
        c.setLineWidth(0.6)
        c.line(x + 14, y + box_h - 33, x + box_w - 14, y + box_h - 33)
        c.restoreState()


def draw_cover(c, station_name, analysis_date):
    draw_background(c)
    draw_diagnostic_motif(c)
    draw_header(c)
    draw_title_block(c, station_name, analysis_date)
    draw_signature_boxes(c)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "front-page-preview.pdf"
    c = canvas.Canvas(str(out), pagesize=A4, initialFontName="Sans", initialFontSize=10)
    c.setTitle("Failure Mode Effect Analysis (FMEA) Report")
    c.setAuthor("")
    c.setSubject("Front page design preview")

    # Test values supplied by the user (not from a workbook yet)
    station = "Tunku Jaafar Power Station"
    analysis_date = datetime.strptime("14/09/2026", "%d/%m/%Y").date()
    draw_cover(c, station, format_analysis_date(analysis_date))
    c.showPage()
    c.save()
    print("wrote", out)


if __name__ == "__main__":
    main()
