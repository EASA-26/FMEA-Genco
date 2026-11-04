"""Summary visuals: the three count cards and the strategy pie with its legend."""
from __future__ import annotations

from typing import Sequence

from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Circle, Drawing, Rect
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import Flowable, Paragraph, Spacer, Table

from backend.pdf import styles
from backend.pdf.fonts import SANS, SANS_BOLD
from backend.pdf.text import plain_markup, truncate_to_width
from backend.report.models import PieSlice

EMPTY_PIE_MESSAGE = "No strategy values to chart."


class StatCards(Flowable):
    """A row of equal cards, each with a label and a big number."""

    CARD_HEIGHT = 64
    GAP = 12
    RADIUS = 6

    def __init__(self, items: Sequence[tuple[str, int]], width: float):
        super().__init__()
        self.items = list(items)
        self.width = width
        self.height = self.CARD_HEIGHT

    def wrap(self, availWidth, availHeight):  # noqa: N803 (ReportLab API names)
        return self.width, self.height

    def draw(self):
        c = self.canv
        count = len(self.items)
        card_w = (self.width - self.GAP * (count - 1)) / count
        for i, (label, value) in enumerate(self.items):
            x = i * (card_w + self.GAP)
            c.saveState()
            c.setFillColor(styles.CARD_FILL)
            c.setStrokeColor(styles.HAIRLINE)
            c.setLineWidth(0.7)
            c.roundRect(x, 0, card_w, self.height, self.RADIUS, stroke=1, fill=1)
            c.setFillColor(styles.PRIMARY)
            c.rect(x, 10, 3, self.height - 20, stroke=0, fill=1)   # accent bar
            c.setFillColor(styles.MUTED)
            c.setFont(SANS, 9)
            c.drawString(x + 14, self.height - 20, truncate_to_width(label, SANS, 9, card_w - 24))
            c.setFillColor(styles.HEADING_INK)
            c.setFont(SANS_BOLD, 24)
            c.drawString(x + 14, 14, truncate_to_width(str(value), SANS_BOLD, 24, card_w - 24))
            c.restoreState()


def _pie_drawing(slices: Sequence[PieSlice], diameter: float) -> Drawing:
    pad = 4
    size = diameter + 2 * pad
    drawing = Drawing(size, size, initialFontName=SANS)   # no default Times-Roman reference
    if len(slices) == 1:
        # A single 100% slice: a plain disc (avoids a separator line from the centre).
        r = diameter / 2
        drawing.add(Circle(pad + r, pad + r, r, fillColor=HexColor(slices[0].color),
                           strokeColor=styles.WHITE, strokeWidth=1))
        return drawing
    pie = Pie()
    pie.x = pie.y = pad
    pie.width = pie.height = diameter
    pie.data = [s.count for s in slices]
    pie.labels = None
    pie.startAngle = 90
    pie.direction = "clockwise"
    pie.slices.strokeColor = styles.WHITE
    pie.slices.strokeWidth = 1.2
    for i, s in enumerate(slices):
        pie.slices[i].fillColor = HexColor(s.color)
    drawing.add(pie)
    return drawing


def _swatch(color: str) -> Drawing:
    drawing = Drawing(9, 9, initialFontName=SANS)
    drawing.add(Rect(0, 0, 9, 9, rx=1.5, ry=1.5, fillColor=HexColor(color), strokeColor=None))
    return drawing


PIE_COLUMN = 172
PIE_DIAMETER = 150
LEGEND_GAP = 6
LEGEND_ROWS_KEPT_WITH_PIE = 2


def _legend_table(slices: Sequence[PieSlice], total: int, legend_width: float) -> Table:
    """Swatch | label | count | percent for every slice, then the total.

    The header row repeats and a row taller than a page may split, so even an
    unusually long legend can flow over pages."""
    label_style = styles.table_cell_style(8.5, 10.5)
    number_style = styles.table_cell_style(8.5, 10.5, align=TA_RIGHT)
    head_style = styles.table_cell_style(8, 10, bold=True, color=styles.MUTED)
    head_right = styles.table_cell_style(8, 10, align=TA_RIGHT, bold=True, color=styles.MUTED)
    total_style = styles.table_cell_style(8.5, 10.5, bold=True, color=styles.HEADING_INK)
    total_right = styles.table_cell_style(8.5, 10.5, align=TA_RIGHT, bold=True, color=styles.HEADING_INK)

    legend_widths = [16, legend_width - 16 - 44 - 52, 44, 52]
    data = [["", Paragraph("Strategy", head_style), Paragraph("Count", head_right), Paragraph("%", head_right)]]
    for s in slices:
        data.append([
            _swatch(s.color),
            Paragraph(plain_markup(s.label or s.code), label_style),
            Paragraph(str(s.count), number_style),
            Paragraph(f"{s.percent:.1f}%", number_style),
        ])
    data.append(["", Paragraph("Total", total_style), Paragraph(str(total), total_right), ""])
    legend_style = [
        ("FONT", (0, 0), (-1, -1), SANS, 8.5),   # empty cells too: no default Helvetica reference
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, styles.RULE),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, styles.RULE),
    ]
    if len(slices) > 1:  # hairlines between slice rows
        legend_style.append(("LINEBELOW", (0, 1), (-1, len(slices) - 1), 0.4, styles.HAIRLINE))
    return Table(data, colWidths=legend_widths, style=legend_style, repeatRows=1, splitInRow=1)


class StrategyPie(Flowable):
    """Pie on the left, legend (label, count, percent for every slice) on the right.

    If the pair does not fit the space it is offered (in practice only a legend
    with dozens of strategies), it splits into the pie followed by a full-width
    legend that continues on the next page with its header repeated."""

    def __init__(self, slices: Sequence[PieSlice], total: int, width: float):
        super().__init__()
        self.slices = list(slices)
        self.total = total
        self.width = width
        legend_width = width - PIE_COLUMN
        self._block = Table(
            [[_pie_drawing(self.slices, PIE_DIAMETER), _legend_table(self.slices, total, legend_width)]],
            colWidths=[PIE_COLUMN, legend_width],
            style=[
                ("FONT", (0, 0), (-1, -1), SANS, 8.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ],
        )

    def wrap(self, availWidth, availHeight):  # noqa: N803 (ReportLab API names)
        self.width, self.height = self._block.wrap(availWidth, availHeight)
        return self.width, self.height

    def draw(self):
        self._block.drawOn(self.canv, 0, 0)

    def stacked_parts(self, width: float) -> list[Flowable]:
        return [_pie_drawing(self.slices, PIE_DIAMETER), Spacer(1, LEGEND_GAP),
                _legend_table(self.slices, self.total, width)]

    def stacked_leading_height(self, width: float) -> float:
        """Height of the pie plus the legend header and first rows (kept with the headings)."""
        legend = _legend_table(self.slices, self.total, width)
        legend.wrap(width, 1e9)
        rows = legend._rowHeights[:1 + LEGEND_ROWS_KEPT_WITH_PIE]
        return PIE_DIAMETER + 8 + LEGEND_GAP + sum(rows)

    def split(self, availWidth, availHeight):  # noqa: N803 (ReportLab API names)
        if self.stacked_leading_height(availWidth) > availHeight:
            return []
        return self.stacked_parts(availWidth)


def strategy_pie(slices: Sequence[PieSlice], total: int, width: float) -> Flowable:
    """The pie with its legend, or a plain message when there is nothing to chart."""
    if not slices or total <= 0:
        return Paragraph(EMPTY_PIE_MESSAGE, styles.EMPTY_NOTE)
    return StrategyPie(slices, total, width)
