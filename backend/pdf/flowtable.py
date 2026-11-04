"""A table flowable that splits across pages the way an FMEA reader expects.

ReportLab's own `Table.split` cannot cope with everything the report needs at
once (a repeated header, merged cells that cross a page boundary, a single row
taller than a page), so `FlowTable` owns the split decision and builds a plain
ReportLab `Table` only for the part that is actually drawn on a page:

* the header rows are repeated on every part;
* a merged group of rows is moved to the next page intact when it is small
  (<= `keep_group_max`), otherwise it is split between rows and the merged value
  is repeated on the next page followed by "(cont.)";
* a row taller than the space left (or than a whole page) is split inside the
  row: each cell's paragraph is divided at a line boundary;
* nothing is ever dropped: if merged content cannot be placed at all, the part
  falls back to unmerged cells rather than failing.

Row heights are measured once per cell and cached, so laying out a long table
costs roughly one measurement per cell instead of one per cell per page.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Sequence

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Paragraph, Spacer, Table

from backend.pdf import styles
from backend.pdf.fonts import SANS, SANS_BOLD, SANS_ITALIC, text_width
from backend.pdf.text import cell_markup, font_size_to_fit_words

FIT_TOLERANCE = 1e-3
UNLIMITED_HEIGHT = 1e9
CONTINUED_MARKER = "(cont.)"
# A repeated table header may take at most this share of the page height.
MAX_HEADER_FRACTION = 0.35
MIN_HEADER_FONT_SIZE = 4.0
# A cell may be set this much smaller to keep a slightly too wide word whole.
MIN_FITTED_FONT_RATIO = 0.8


@dataclass(frozen=True)
class Span:
    """A merged block in part-relative body row indexes (0-based, inclusive)."""

    first_row: int
    first_col: int
    last_row: int
    last_col: int
    text: str = ""            # top-left text, repeated with "(cont.)" after a page break
    continued: bool = False   # this part shows the repeated value instead of the original cell

    @property
    def multi_row(self) -> bool:
        return self.last_row > self.first_row

    @property
    def single_cell(self) -> bool:
        return self.first_row == self.last_row and self.first_col == self.last_col


class CellText(Flowable):
    """Multi-line cell text: one Paragraph per workbook line (a Spacer for a blank line).

    Splitting happens between lines or inside a wrapped line, so a continuation
    never starts with a stray empty line.
    """

    def __init__(self, lines: Sequence[Flowable]):
        super().__init__()
        self.lines = list(lines)
        self._heights: list[float] = []

    def wrap(self, availWidth, availHeight):  # noqa: N803 (ReportLab API names)
        self._heights = [line.wrap(availWidth, availHeight)[1] for line in self.lines]
        self.width, self.height = availWidth, sum(self._heights)
        return self.width, self.height

    def split(self, availWidth, availHeight):  # noqa: N803 (ReportLab API names)
        used = 0.0
        for i, line in enumerate(self.lines):
            h = line.wrap(availWidth, availHeight)[1]
            if used + h <= availHeight + FIT_TOLERANCE:
                used += h
                continue
            head, rest = self.lines[:i], self.lines[i + 1:]
            pieces = [] if isinstance(line, Spacer) else line.split(availWidth, availHeight - used)
            if len(pieces) == 2:
                head, rest = head + [pieces[0]], [pieces[1]] + rest
            else:
                rest = [line] + rest
            while rest and isinstance(rest[0], Spacer):   # no blank line at the top of a continuation
                rest = rest[1:]
            if not head:
                return []
            return [CellText(head), CellText(rest)] if rest else [CellText(head)]
        return [self]

    def draw(self):
        y = self.height
        for line, h in zip(self.lines, self._heights):
            y -= h
            line.drawOn(self.canv, 0, y)


class BodyRow:
    """One drawn row: a flowable (or None when empty or covered by a merge) per column.

    `band` groups rows for zebra shading and separator lines (merged rows share a band);
    `texts` keeps the source text so identifying values can be repeated after a split.
    """

    __slots__ = ("cells", "band", "texts", "_measured")

    def __init__(self, cells: Sequence[Optional[Flowable]], band: int, texts: Sequence[str] = ()):
        self.cells = list(cells)
        self.band = band
        self.texts = list(texts)
        self._measured: dict[tuple[int, float], float] = {}

    def content_height(self, col: int, width: float) -> float:
        key = (col, round(width, 3))
        if key not in self._measured:
            self._measured[key] = self.cells[col].wrap(width, UNLIMITED_HEIGHT)[1]
        return self._measured[key]


class TableLayout:
    """Everything shared by all parts of one table: columns, cell styles, header,
    look and split rules."""

    def __init__(
        self,
        col_widths: Sequence[float],
        cell_styles: Sequence[ParagraphStyle],
        *,
        header_style: Optional[ParagraphStyle] = None,
        frame_height: float = styles.FRAME_HEIGHT,
        keep_group_fraction: float = 0.4,
        padding: tuple[float, float, float, float] = (3.0, 3.0, 2.5, 3.0),  # left, right, top, bottom
        grid: bool = True,
        zebra: bool = True,
        group_rules: bool = False,
        repeat_columns: Sequence[int] = (0,),
    ):
        if len(cell_styles) != len(col_widths):
            raise ValueError("one cell style per column is required")
        self.col_widths = list(col_widths)
        self.cell_styles = list(cell_styles)
        self.header_style = header_style
        self.font_size = cell_styles[0].fontSize if cell_styles else 8.0
        self.leading = max((s.leading for s in cell_styles), default=10.0)
        self.frame_height = frame_height
        self.keep_group_max = keep_group_fraction * frame_height
        self.pad_left, self.pad_right, self.pad_top, self.pad_bottom = padding
        self.grid = grid
        self.zebra = zebra
        self.group_rules = group_rules   # stronger line between bands (merged groups)
        # Identifying columns repeated with "(cont.)" when one row is split across pages.
        self.repeat_columns = [c for c in repeat_columns if 0 <= c < len(col_widths)]
        self.header_rows: list[list[object]] = []
        self.header_spans: list[tuple[int, int, int, int]] = []
        # An empty cell still occupies one line (ReportLab measures "" as one line).
        self.min_row_height = self.leading + self.pad_top + self.pad_bottom
        # Smallest space worth starting a split row in: a few lines of text.
        self.min_split_space = 3 * self.leading + self.pad_top + self.pad_bottom
        self._header_height: Optional[float] = None
        self._fitted_styles: dict[tuple[str, float], ParagraphStyle] = {}

    @property
    def column_count(self) -> int:
        return len(self.col_widths)

    @property
    def total_width(self) -> float:
        return sum(self.col_widths)

    def content_width(self, first_col: int, last_col: int) -> float:
        return sum(self.col_widths[first_col:last_col + 1]) - self.pad_left - self.pad_right

    # ------------------------------------------------------------------ cells
    def cell(self, text: str, col: int, last_col: Optional[int] = None,
             suffix_markup: str = "") -> Optional[Flowable]:
        """Flowable for workbook text in column `col` (None for empty text).

        Line breaks in the workbook text are kept; `suffix_markup` is appended to
        the last line."""
        if not text and not suffix_markup:
            return None
        width = self.content_width(col, col if last_col is None else last_col)
        style = self.fitted_style(self.cell_styles[col], text, width)
        lines = (text or "").split("\n")
        flowables: list[Flowable] = []
        for i, line in enumerate(lines):
            markup = cell_markup(line, style.fontName, style.fontSize, width)
            if i == len(lines) - 1 and suffix_markup:
                markup = f"{markup} {suffix_markup}" if markup else suffix_markup
            flowables.append(Paragraph(markup, style) if markup.strip() else Spacer(0, style.leading))
        return flowables[0] if len(flowables) == 1 else CellText(flowables)

    def fitted_style(self, style: ParagraphStyle, text: str, width: float) -> ParagraphStyle:
        """`style`, or a slightly smaller copy when one word of `text` is a little too
        wide for the cell (that cell only; see `font_size_to_fit_words`)."""
        size = font_size_to_fit_words(text, style.fontName, style.fontSize, width,
                                      min_size=MIN_FITTED_FONT_RATIO * style.fontSize)
        if size == style.fontSize:
            return style
        key = (style.name, size)
        if key not in self._fitted_styles:
            self._fitted_styles[key] = ParagraphStyle(f"{style.name}-fit{size:g}", parent=style, fontSize=size,
                                                      leading=size * style.leading / style.fontSize)
        return self._fitted_styles[key]

    def row(self, texts: Sequence[str], band: int, merge_last_cols: Optional[dict[int, int]] = None) -> BodyRow:
        """A body row from cell texts; `merge_last_cols` maps a merged cell's column to its last column."""
        merge_last_cols = merge_last_cols or {}
        texts = [texts[c] if c < len(texts) else "" for c in range(self.column_count)]
        cells = [self.cell(text, c, merge_last_cols.get(c)) for c, text in enumerate(texts)]
        return BodyRow(cells, band, texts)

    def continued_cell(self, text: str, col: int, last_col: Optional[int] = None) -> Flowable:
        """A merged value repeated after a page break, marked "(cont.)"."""
        style = self.cell_styles[col]
        width = self.content_width(col, col if last_col is None else last_col)
        size = style.fontSize
        while size > 5 and text_width(CONTINUED_MARKER, SANS_ITALIC, size) > width:
            size -= 0.5   # narrow columns (e.g. No.): a smaller marker instead of a broken one
        marker = f'<font size="{size:g}" color="{styles.MUTED_HEX}"><i>{CONTINUED_MARKER}</i></font>'
        return self.cell(text, col, last_col, suffix_markup=marker)

    # ------------------------------------------------------------------ header
    def set_header(self, rows: Sequence[Sequence[str]],
                   spans: Sequence[tuple[int, int, int, int]] = ()) -> None:
        """Header rows of label text; `spans` are (first_col, first_row, last_col, last_row).

        The header is repeated on every page, so it must leave room for the body.
        A label taller than its share of `MAX_HEADER_FRACTION` of the page is set
        in a smaller type size (that cell only) and, only if it still does not fit
        at the smallest size, shortened with an ellipsis; without this the table
        could not be drawn at all.
        """
        if self.header_style is None:
            raise ValueError("header_style is required for a header")
        self.header_spans = list(spans)
        cell_limit = (MAX_HEADER_FRACTION * self.frame_height / max(len(rows), 1)
                      - (self.pad_top + 1) - (self.pad_bottom + 1))
        self.header_rows = [
            [self._header_cell(label, c, r, cell_limit) if label else "" for c, label in enumerate(labels)]
            for r, labels in enumerate(rows)
        ]
        self._header_height = None

    def _header_width(self, col: int, row: int) -> float:
        for first_col, first_row, last_col, _ in self.header_spans:
            if (first_col, first_row) == (col, row):
                return self.content_width(col, last_col)
        return self.content_width(col, col)

    def _header_cell(self, label: str, col: int, row: int, max_height: float) -> Paragraph:
        width = self._header_width(col, row)
        base = self.header_style

        def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
            return Paragraph(cell_markup(text, style.fontName, style.fontSize, width), style)

        def height(p: Paragraph) -> float:
            return p.wrap(width, UNLIMITED_HEIGHT)[1]

        style = self.fitted_style(base, label, width)
        cell = paragraph(label, style)
        while height(cell) > max_height and style.fontSize > MIN_HEADER_FONT_SIZE:
            size = max(MIN_HEADER_FONT_SIZE, style.fontSize - 1.0)
            style = ParagraphStyle(f"{base.name}-{size:g}", parent=base, fontSize=size,
                                   leading=size * base.leading / base.fontSize)
            cell = paragraph(label, style)
        if height(cell) <= max_height:
            return cell
        low, high = 0, len(label)   # longest prefix that fits together with an ellipsis
        while low < high:
            mid = (low + high + 1) // 2
            if height(paragraph(label[:mid].rstrip() + "…", style)) <= max_height:
                low = mid
            else:
                high = mid - 1
        return paragraph(label[:low].rstrip() + "…", style)

    def header_height(self) -> float:
        if self._header_height is None:
            if not self.header_rows:
                self._header_height = 0.0
            else:
                table = Table([list(r) for r in self.header_rows], colWidths=self.col_widths,
                              style=self.header_commands())
                self._header_height = table.wrap(self.total_width, UNLIMITED_HEIGHT)[1]
        return self._header_height

    def header_commands(self) -> list[tuple]:
        if not self.header_rows:
            return []
        last = len(self.header_rows) - 1
        commands = [
            ("FONT", (0, 0), (-1, last), SANS_BOLD, self.font_size, self.leading),
            ("TEXTCOLOR", (0, 0), (-1, last), styles.WHITE),
            ("BACKGROUND", (0, 0), (-1, last), styles.TABLE_HEADER_FILL),
            ("VALIGN", (0, 0), (-1, last), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, last), self.pad_left),
            ("RIGHTPADDING", (0, 0), (-1, last), self.pad_right),
            ("TOPPADDING", (0, 0), (-1, last), self.pad_top + 1),
            ("BOTTOMPADDING", (0, 0), (-1, last), self.pad_bottom + 1),
            ("INNERGRID", (0, 0), (-1, last), 0.5, styles.WHITE),
        ]
        for first_col, first_row, last_col, last_row in self.header_spans:
            commands.append(("SPAN", (first_col, first_row), (last_col, last_row)))
        return commands


class FlowTable(Flowable):
    """Splittable table part (see module docstring)."""

    def __init__(self, layout: TableLayout, rows: Sequence[BodyRow], spans: Sequence[Span] = (),
                 *, keep_with_previous: bool = False):
        super().__init__()
        self.layout = layout
        self.rows = list(rows)
        self.spans = list(spans)
        # The first part of a table that follows its heading: prefer splitting over
        # leaving the heading alone at the bottom of a page.
        self.keep_with_previous = keep_with_previous
        self._top_left: dict[tuple[int, int], Span] = {}
        self._covered: set[tuple[int, int]] = set()
        for span in self.spans:
            self._top_left[(span.first_row, span.first_col)] = span
            for r in range(span.first_row, span.last_row + 1):
                for c in range(span.first_col, span.last_col + 1):
                    if (r, c) != (span.first_row, span.first_col):
                        self._covered.add((r, c))
        self._continued_cells: dict[tuple[int, int], Flowable] = {}
        self._heights: Optional[list[float]] = None
        self._table: Optional[Table] = None

    # ------------------------------------------------------------------ cells
    def _cell(self, row: int, col: int) -> Optional[Flowable]:
        if (row, col) in self._covered:
            return None
        span = self._top_left.get((row, col))
        if span is not None and span.continued:
            if not span.text:   # an empty merged cell stays empty on the next page
                return None
            key = (row, col)
            if key not in self._continued_cells:
                self._continued_cells[key] = self.layout.continued_cell(span.text, col, span.last_col)
            return self._continued_cells[key]
        return self.rows[row].cells[col] if col < len(self.rows[row].cells) else None

    def _cell_width(self, row: int, col: int) -> float:
        span = self._top_left.get((row, col))
        last_col = span.last_col if span is not None else col
        return self.layout.content_width(col, last_col)

    def _measure(self, row: int, col: int) -> float:
        """Content height of a cell (without padding)."""
        value = self._cell(row, col)
        if value is None:
            return 0.0
        width = self._cell_width(row, col)
        span = self._top_left.get((row, col))
        if span is not None and span.continued:
            return value.wrap(width, UNLIMITED_HEIGHT)[1]
        return self.rows[row].content_height(col, width)

    def row_heights(self) -> list[float]:
        """Estimated drawn height of each body row, mirroring ReportLab's sizing:
        merged content taller than its rows is shared equally among those rows."""
        if self._heights is not None:
            return self._heights
        L = self.layout
        pads = L.pad_top + L.pad_bottom
        heights = []
        for r in range(len(self.rows)):
            h = L.min_row_height
            for c in range(L.column_count):
                if (r, c) in self._covered:
                    continue
                span = self._top_left.get((r, c))
                if span is not None and span.multi_row:
                    continue
                h = max(h, self._measure(r, c) + pads)
            heights.append(h)
        needs = []
        for span in self.spans:
            if span.multi_row:
                need = self._measure(span.first_row, span.first_col) + pads
                needs.append((need, span))
        for need, span in sorted(needs, key=lambda item: -item[0]):
            have = sum(heights[span.first_row:span.last_row + 1])
            if need > have:
                extra = (need - have) / (span.last_row - span.first_row + 1)
                for r in range(span.first_row, span.last_row + 1):
                    heights[r] += extra
        self._heights = heights
        return heights

    def leading_height(self, body_rows: int) -> float:
        """Height of the header plus the first `body_rows` rows (for keep-with-heading checks)."""
        return self.layout.header_height() + sum(self.row_heights()[:body_rows])

    # ------------------------------------------------------------------ drawing
    def _build_table(self) -> Table:
        L = self.layout
        n_header = len(L.header_rows)
        data = [list(row) for row in L.header_rows]
        for r in range(len(self.rows)):
            data.append([self._cell(r, c) or "" for c in range(L.column_count)])
        n_rows = len(data)
        commands = L.header_commands()
        if self.rows:
            first, last = n_header, n_rows - 1
            commands += [
                ("FONT", (0, first), (-1, last), SANS, L.font_size, L.leading),
                ("TEXTCOLOR", (0, first), (-1, last), styles.BODY_INK),
                ("VALIGN", (0, first), (-1, last), "TOP"),
                ("LEFTPADDING", (0, first), (-1, last), L.pad_left),
                ("RIGHTPADDING", (0, first), (-1, last), L.pad_right),
                ("TOPPADDING", (0, first), (-1, last), L.pad_top),
                ("BOTTOMPADDING", (0, first), (-1, last), L.pad_bottom),
            ]
            if L.zebra:
                for r, row in enumerate(self.rows):
                    if row.band % 2 == 1:
                        commands.append(("BACKGROUND", (0, first + r), (-1, first + r), styles.ZEBRA))
            if L.grid:
                commands += [
                    ("INNERGRID", (0, first), (-1, last), 0.4, styles.HAIRLINE),
                    ("BOX", (0, 0), (-1, -1), 0.6, styles.RULE),
                ]
                for r in range(len(self.rows) - 1):
                    if L.group_rules and self.rows[r].band != self.rows[r + 1].band:
                        commands.append(("LINEBELOW", (0, first + r), (-1, first + r), 0.6, styles.RULE))
        for span in self.spans:
            if not span.single_cell:
                commands.append(("SPAN", (span.first_col, n_header + span.first_row),
                                 (span.last_col, n_header + span.last_row)))
        return Table(data, colWidths=L.col_widths, style=commands)

    def wrap(self, availWidth, availHeight):  # noqa: N803 (ReportLab API names)
        estimate = self.layout.header_height() + sum(self.row_heights())
        if estimate > availHeight + FIT_TOLERANCE:
            # Clearly too tall: skip building the table, the frame will ask for a split.
            self._table = None
            self.width, self.height = self.layout.total_width, estimate
            return self.width, self.height
        self._table = self._build_table()
        self.width, self.height = self._table.wrap(availWidth, availHeight)
        return self.width, self.height

    def draw(self):
        if self._table is None:
            self._table = self._build_table()
            self._table.wrap(self.layout.total_width, UNLIMITED_HEIGHT)
        self._table.drawOn(self.canv, 0, 0)

    # ------------------------------------------------------------------ splitting
    def split(self, availWidth, availHeight):  # noqa: N803 (ReportLab API names)
        parts = self._split(availWidth, availHeight)
        at_page_top = availHeight >= self.layout.frame_height - 1.0
        group = self._group_at(0) if not parts and at_page_top else None
        if group is not None:
            # Merged text taller than an empty page: show the first group unmerged
            # rather than fail. No text is lost (the tall text then splits inside
            # its own row) and later groups keep their merges.
            flat = [replace(s, last_row=s.first_row) if s.multi_row and s.first_row <= group[1] else s
                    for s in self.spans]
            return FlowTable(self.layout, self.rows, flat,
                             keep_with_previous=self.keep_with_previous).split(availWidth, availHeight)
        return parts

    def _split(self, aW: float, aH: float) -> list[Flowable]:
        L = self.layout
        if not self.rows:
            return []
        heights = self.row_heights()
        header_h = L.header_height()
        body = aH - header_h
        at_page_top = aH >= L.frame_height - 1.0
        must_place = at_page_top or self.keep_with_previous
        if body < L.min_row_height:
            return []

        # Whole rows that fit.
        used, n = 0.0, 0
        while n < len(self.rows) and used + heights[n] <= body + FIT_TOLERANCE:
            used += heights[n]
            n += 1
        if n >= len(self.rows):  # estimate said "fits" but the real table did not
            n = len(self.rows) - 1
            used -= heights[n]

        cut = n
        group = self._group_at(n)
        if group is not None and group[0] < n:
            start, end = group
            if sum(heights[start:end + 1]) <= L.keep_group_max:
                if start > 0:
                    cut = start               # move the small merged group to the next page intact
                elif not must_place:
                    return []                 # the whole table starts with that group: move it on
                # otherwise split inside the group (cut stays n)

        if cut == n:
            free = body - used
            fresh_body = L.frame_height - header_h
            row_too_tall_for_any_page = heights[n] > fresh_body + FIT_TOLERANCE
            if free >= L.min_split_space and (row_too_tall_for_any_page or (n == 0 and must_place)):
                parts = self._split_inside_row(n, free, aW, aH)
                if parts:
                    return parts

        while cut > 0:
            head = self._part(0, cut)
            if head.wrap(aW, aH)[1] <= aH + FIT_TOLERANCE:
                return [head, self._part(cut, len(self.rows))]
            cut -= 1
        return []

    def _group_at(self, row: int) -> Optional[tuple[int, int]]:
        """First and last row of the merged group (connected multi-row spans) containing `row`."""
        intervals = sorted((s.first_row, s.last_row) for s in self.spans if s.multi_row)
        start = end = None
        for first, last in intervals:
            if start is None or first > end:
                if start is not None and start <= row <= end:
                    return start, end
                start, end = first, last
            else:
                end = max(end, last)
        if start is not None and start <= row <= end:
            return start, end
        return None

    def _clipped_spans(self, start: int, stop: int) -> list[Span]:
        spans = []
        for span in self.spans:
            if span.last_row < start or span.first_row >= stop:
                continue
            spans.append(replace(
                span,
                first_row=max(span.first_row, start) - start,
                last_row=min(span.last_row, stop - 1) - start,
                continued=span.continued or span.first_row < start,
            ))
        return spans

    def _part(self, start: int, stop: int) -> "FlowTable":
        return FlowTable(self.layout, self.rows[start:stop], self._clipped_spans(start, stop),
                         keep_with_previous=self.keep_with_previous and start == 0)

    def _split_inside_row(self, n: int, space: float, aW: float, aH: float) -> list[Flowable]:
        """Divide row `n` so its first lines fill `space`; the rest starts the next part."""
        L = self.layout
        content_space = space - L.pad_top - L.pad_bottom
        source = self.rows[n]
        head_cells: list[Optional[Flowable]] = [None] * L.column_count
        tail_cells: list[Optional[Flowable]] = [None] * L.column_count
        placed_any = False
        for c in range(L.column_count):
            value = self._cell(n, c)
            if value is None:
                continue
            width = self._cell_width(n, c)
            if value.wrap(width, content_space)[1] <= content_space + FIT_TOLERANCE:
                head_cells[c] = value
                placed_any = True
                continue
            pieces = value.split(width, content_space)
            if len(pieces) == 2:
                head_cells[c], tail_cells[c] = pieces
                placed_any = True
            elif len(pieces) == 1:   # fits once trailing blank lines are dropped
                head_cells[c] = pieces[0]
                placed_any = True
            else:
                tail_cells[c] = value
        if not placed_any:
            return []
        for c in L.repeat_columns:
            # e.g. the Failure Mode that fitted above: repeat it so the continuation is identifiable
            if (tail_cells[c] is None and head_cells[c] is not None and c < len(source.texts)
                    and source.texts[c] and (n, c) not in self._top_left):
                tail_cells[c] = L.continued_cell(source.texts[c], c)

        head_row = BodyRow(head_cells, source.band, source.texts)
        tail_row = BodyRow(tail_cells, source.band, source.texts)

        head_spans = []
        for span in self.spans:
            if span.first_row > n:
                continue
            head_spans.append(replace(
                span,
                last_row=min(span.last_row, n),
                # a merged cell starting in the split row now has its content in head_row
                continued=span.continued and span.first_row < n,
            ))
        head = FlowTable(L, self.rows[:n] + [head_row], head_spans, keep_with_previous=self.keep_with_previous)
        if head.wrap(aW, aH)[1] > aH + FIT_TOLERANCE:
            return []

        tail_spans = []
        for span in self.spans:
            if span.last_row < n:
                continue
            text = span.text
            if span.first_row < n:
                continued = True
            elif span.first_row == n:
                # Show what is left of the merged cell. When all of it fitted above,
                # repeat the value with "(cont.)" only if the merge goes on into later
                # rows; a one-row merge is complete and stays empty (no duplicate text).
                continued = tail_cells[span.first_col] is None
                if continued and not span.multi_row:
                    text = ""
            else:
                continued = span.continued
            tail_spans.append(replace(span, first_row=max(span.first_row, n) - n,
                                      last_row=span.last_row - n, continued=continued, text=text))
        tail = FlowTable(L, [tail_row] + self.rows[n + 1:], tail_spans)
        return [head, tail]
