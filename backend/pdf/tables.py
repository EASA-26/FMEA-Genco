"""The report's tables, built on `FlowTable`."""
from __future__ import annotations

from typing import Optional, Sequence

from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle

from backend.config.mapping import FAILURE_DETAILS_LABELS, normalise_header
from backend.pdf import styles
from backend.pdf.flowtable import FlowTable, Span, TableLayout
from backend.pdf.fonts import SANS, text_width
from backend.report.models import (
    AnalysisTable,
    FailureDetail,
    MergedRange,
    RecommendationGroup,
    StrategyRow,
    TeamMember,
    WorkCentreRow,
)

EMPTY_CODE = "—"   # em dash shown for a blank strategy code

# --------------------------------------------------------------------------- #
# Analysis table column widths (A3 landscape)
# --------------------------------------------------------------------------- #
# Short Yes/No style flag columns: narrow and centred.
FLAG_COLUMNS = frozenset({"h", "s", "e", "o", "1", "2", "3", "h4", "h5", "s4"})
FLAG_WIDTH = 16.0
# Preferred widths for known columns (normalised header -> points). Other columns
# get DEFAULT_WIDTH; everything except the flags is then scaled to the frame.
ANALYSIS_WIDTH_HINTS = {
    "no": 24,
    "failuremode": 112,
    "failureeffect": 132,
    "recommendedstrategy": 64,
    "task": 168,
    "frequency": 48,
    "trade": 54,
    "kks": 90,
    "newtask": 34,
    "reviewtask": 78,
    "maintenanceplanno": 62,
    "remark": 100,
}
DEFAULT_WIDTH = 70.0
# When extra columns force the others narrower, no column is squeezed below this
# while there is room, so short values (No., New Task, Trade) stay on one line.
MIN_FLEXIBLE_WIDTH = 26.0
CENTRED_COLUMNS = FLAG_COLUMNS | {"no", "newtask", "frequency"}


def analysis_column_widths(columns: Sequence[str], frame_width: float) -> list[float]:
    """Known widths for known columns, remaining space shared, scaled to the frame width."""
    keys = [normalise_header(c) for c in columns]
    if not keys:
        return []
    base = [FLAG_WIDTH if k in FLAG_COLUMNS else float(ANALYSIS_WIDTH_HINTS.get(k, DEFAULT_WIDTH))
            for k in keys]
    flexible = [k not in FLAG_COLUMNS for k in keys]
    flag_total = sum(w for w, f in zip(base, flexible) if not f)
    flexible_total = sum(w for w, f in zip(base, flexible) if f)
    room = frame_width - flag_total
    if flexible_total and room >= flexible_total:
        scale = room / flexible_total   # widen the text columns to fill the frame
        return [w * scale if f else w for w, f in zip(base, flexible)]
    floors = [min(w, MIN_FLEXIBLE_WIDTH) for w in base]
    floor_total = sum(fl for fl, f in zip(floors, flexible) if f)
    if flexible_total and room >= floor_total:
        # Narrower than preferred: take the space from each column's share above its floor.
        scale = (room - floor_total) / (flexible_total - floor_total) if flexible_total > floor_total else 0.0
        return [fl + (w - fl) * scale if f else w for w, fl, f in zip(base, floors, flexible)]
    scale = frame_width / sum(base)   # very many columns: shrink everything evenly
    return [w * scale for w in base]


def _scale(widths: Sequence[float], total: float) -> list[float]:
    factor = total / sum(widths)
    return [w * factor for w in widths]


def _column_styles(count: int, aligns: Optional[Sequence[Optional[int]]] = None,
                   base: ParagraphStyle = styles.A4_CELL) -> list[ParagraphStyle]:
    aligns = aligns or [None] * count
    return [
        base if align is None else styles.table_cell_style(base.fontSize, base.leading, align=align)
        for align in aligns
    ]


def simple_table(headers: Sequence[str], widths: Sequence[float], rows: Sequence[Sequence[str]],
                 *, aligns: Optional[Sequence[Optional[int]]] = None) -> FlowTable:
    """A4 table: one header row, one drawn row per data row, zebra by row."""
    layout = TableLayout(widths, _column_styles(len(widths), aligns), header_style=styles.A4_HEADER)
    layout.set_header([list(headers)])
    body = [layout.row(values, band=index) for index, values in enumerate(rows)]
    return FlowTable(layout, body, keep_with_previous=True)


# --------------------------------------------------------------------------- #
# Introduction
# --------------------------------------------------------------------------- #
FAILURE_DETAIL_KEYS = ("uoir_id", "title", "faulty_date", "uoir_date", "corrective_action",
                       "preventive_action", "equipment")


def failure_details_table(details: Sequence[FailureDetail], frame_width: float) -> FlowTable:
    headers = [FAILURE_DETAILS_LABELS[k] for k in FAILURE_DETAIL_KEYS]
    widths = _scale([48, 92, 60, 60, 92, 92, 66], frame_width)
    rows = [
        [d.uoir_id, d.title, d.faulty_date_text, d.uoir_date_text, d.corrective_action,
         d.preventive_action, d.equipment]
        for d in details
    ]
    return simple_table(headers, widths, rows)


def team_table(team: Sequence[TeamMember], frame_width: float) -> FlowTable:
    widths = _scale([34, 210, 90, 176], frame_width)
    rows = [[m.no, m.name, m.staff_no, m.section] for m in team]
    return simple_table(["No", "Name", "Staff No", "Section"], widths, rows,
                        aligns=[TA_CENTER, None, None, None])


# --------------------------------------------------------------------------- #
# FMEA Analysis (A3)
# --------------------------------------------------------------------------- #
def _cell_text(table: AnalysisTable, row: int, col: int) -> str:
    cells = table.rows[row].cells
    return cells[col] if col < len(cells) else ""


def usable_merges(table: AnalysisTable) -> list[MergedRange]:
    """Merged ranges clipped to the table. Overlapping ranges, and ranges whose
    covered cells unexpectedly hold text, are left out so those cells show
    unmerged (text is never hidden)."""
    n_rows, n_cols = len(table.rows), len(table.columns)
    taken: set[tuple[int, int]] = set()
    usable = []
    for m in sorted(table.merged, key=lambda m: (m.first_row, m.first_col)):
        r0, r1 = max(m.first_row, 0), min(m.last_row, n_rows - 1)
        c0, c1 = max(m.first_col, 0), min(m.last_col, n_cols - 1)
        if r0 > r1 or c0 > c1 or (r0 == r1 and c0 == c1):
            continue
        cells = [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
        if any(cell in taken for cell in cells):
            continue
        if any(_cell_text(table, r, c) for r, c in cells[1:]):
            continue
        taken.update(cells)
        usable.append(MergedRange(first_row=r0, first_col=c0, last_row=r1, last_col=c1))
    return usable


def row_bands(n_rows: int, merges: Sequence[MergedRange]) -> list[int]:
    """Band number per row: rows joined by vertical merges share a band."""
    reach_of = list(range(n_rows))
    for m in merges:
        for r in range(m.first_row, m.last_row + 1):
            reach_of[r] = max(reach_of[r], m.last_row)
    bands, band, reach = [], -1, -1
    for r in range(n_rows):
        if r > reach:
            band += 1
        reach = max(reach, reach_of[r])
        bands.append(band)
    return bands


ANALYSIS_SIDE_PADDING = 2.5
MIN_CONTENT_WIDTH = 4.0


def side_padding_for(widths: Sequence[float], preferred: float = ANALYSIS_SIDE_PADDING) -> float:
    """Cell side padding that still leaves room for text in the narrowest column.

    Only an analysis tab with an unusually large number of columns gets less
    padding; ReportLab refuses a cell whose padding is wider than the cell."""
    if not widths:
        return preferred
    return max(0.0, min(preferred, (min(widths) - MIN_CONTENT_WIDTH) / 2))


def analysis_table(table: AnalysisTable, frame_width: float,
                   frame_height: float = styles.FRAME_HEIGHT) -> FlowTable:
    columns = list(table.columns)
    keys = [normalise_header(c) for c in columns]
    widths = analysis_column_widths(columns, frame_width)
    side = side_padding_for(widths)
    layout = TableLayout(
        widths,
        [styles.A3_CELL_CENTRED if k in CENTRED_COLUMNS else styles.A3_CELL for k in keys],
        header_style=styles.A3_HEADER,
        frame_height=frame_height,
        padding=(side, side, 2.0, 2.5),
        group_rules=True,
        repeat_columns=[i for i, k in enumerate(keys) if k in ("no", "failuremode")],
    )
    layout.set_header([columns])

    merges = usable_merges(table)
    bands = row_bands(len(table.rows), merges)
    merge_last_cols: dict[int, dict[int, int]] = {}
    for m in merges:
        merge_last_cols.setdefault(m.first_row, {})[m.first_col] = m.last_col
    body = [layout.row(table.rows[r].cells, bands[r], merge_last_cols.get(r)) for r in range(len(table.rows))]
    spans = [Span(m.first_row, m.first_col, m.last_row, m.last_col, text=_cell_text(table, m.first_row, m.first_col))
             for m in merges]
    return FlowTable(layout, body, spans, keep_with_previous=True)


# --------------------------------------------------------------------------- #
# FMEA Summary (A4)
# --------------------------------------------------------------------------- #
def strategy_table(rows: Sequence[StrategyRow], frame_width: float) -> FlowTable:
    widths = _scale([70, 290, 75, 75], frame_width)
    data = [[row.code or EMPTY_CODE, row.label, str(row.existing), str(row.new)] for row in rows]
    return simple_table(["Code", "Strategy", "Existing", "New"], widths, data,
                        aligns=[None, None, TA_RIGHT, TA_RIGHT])


def work_centre_table(rows: Sequence[WorkCentreRow], frame_width: float) -> FlowTable:
    widths = _scale([285, 75, 75, 75], frame_width)
    data = [[row.work_centre, str(row.total), str(row.executed), str(row.pending)] for row in rows]
    return simple_table(["Work Centre", "Total", "Executed", "Pending"], widths, data,
                        aligns=[None, TA_RIGHT, TA_RIGHT, TA_RIGHT])


# --------------------------------------------------------------------------- #
# Recommendation (A4, two-row grouped header)
# --------------------------------------------------------------------------- #
def recommendation_table(group: RecommendationGroup, frame_width: float) -> FlowTable:
    layout = TableLayout(_scale([175, 255, 80], frame_width), [styles.A4_CELL] * 3,
                         header_style=styles.A4_HEADER)
    layout.set_header(
        [["Failure Mode", "Recommendations", ""],
         ["", "Task", "Frequency"]],
        spans=[(0, 0, 0, 1), (1, 0, 2, 0)],   # (first_col, first_row, last_col, last_row)
    )
    body = [layout.row([row.failure_mode, row.task, row.frequency], band=index)
            for index, row in enumerate(group.rows)]
    return FlowTable(layout, body, keep_with_previous=True)


# --------------------------------------------------------------------------- #
# Key / value lines ("UOIR ID : 901")
# --------------------------------------------------------------------------- #
def key_value_table(pairs: Sequence[tuple[str, str]], frame_width: float) -> FlowTable:
    """Borderless label / colon / value rows with aligned colons; values wrap."""
    size = styles.KEY_LABEL.fontSize
    label_w = max(text_width(label, SANS, size) for label, _ in pairs) + 8
    colon_w = text_width(":", SANS, size) + 8
    layout = TableLayout(
        [label_w, colon_w, frame_width - label_w - colon_w],
        [styles.KEY_LABEL, styles.KEY_LABEL, styles.KEY_VALUE],
        padding=(0.0, 4.0, 1.0, 2.0),
        grid=False,
        zebra=False,
    )
    body = [layout.row([label, ":", value], band=index) for index, (label, value) in enumerate(pairs)]
    return FlowTable(layout, body, keep_with_previous=True)
