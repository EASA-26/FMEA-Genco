"""Unit tests for the PDF helpers: text markup, column widths, merges, lines of text."""
from __future__ import annotations

import pytest
from reportlab.platypus import Paragraph

from backend.pdf import styles
from backend.pdf.document import header_text
from backend.pdf.flowtable import CellText, TableLayout
from backend.pdf.fonts import SANS, SANS_BOLD, text_width
from backend.pdf.sections import duplicate_line, not_counted_line
from backend.pdf.tables import (
    FLAG_WIDTH,
    analysis_column_widths,
    row_bands,
    usable_merges,
)
from backend.pdf.text import cell_markup, escape, plain_markup, truncate_to_width
from backend.report.models import AnalysisRow, AnalysisTable, MergedRange, NotCountedRow
from backend.tests.test_pdf_fixtures import ANALYSIS_COLUMNS, LONG_KKS


# --------------------------------------------------------------------------- text
def test_escape_and_line_breaks():
    assert escape("A & B <C>") == "A &amp; B &lt;C&gt;"
    assert plain_markup("one\ntwo & three") == "one<br/>two &amp; three"


def test_short_text_is_only_escaped():
    assert cell_markup("Valve <V1> & pump", SANS, 7.5, 200) == "Valve &lt;V1&gt; &amp; pump"


def test_long_token_gets_break_points_at_separators():
    width = 60
    markup = cell_markup(LONG_KKS, SANS, 7.5, width)
    segments = markup.split("<br/>")
    assert len(segments) > 1
    assert "".join(segments) == LONG_KKS            # nothing added or lost
    assert all(text_width(s, SANS, 7.5) <= width for s in segments)
    # natural break points first (after "/" and "-"), then between letters and digits
    assert segments == ["SYN11/AB920-", "980XV03-04-", "LONGCODE", "123456"]


def test_camel_case_header_breaks_between_words():
    width = text_width("Recommended", SANS_BOLD, 7.5) + 2
    assert cell_markup("RecommendedStrategy", SANS_BOLD, 7.5, width) == "Recommended<br/>Strategy"


def test_multiline_text_keeps_its_lines():
    assert cell_markup("line one\nline two", SANS, 8, 300) == "line one<br/>line two"


def test_truncate_to_width():
    assert truncate_to_width("short", SANS, 8, 100) == "short"
    long_text = "SYNTHETIC " * 30
    shortened = truncate_to_width(long_text, SANS, 8, 100)
    assert shortened.endswith("…") and text_width(shortened, SANS, 8) <= 100


def test_header_text():
    assert header_text("SYNTHETIC  Station\nOne") == "FMEA Report · SYNTHETIC Station One"
    assert header_text("") == "FMEA Report"


# --------------------------------------------------------------------------- notes
def test_not_counted_and_duplicate_lines():
    row = NotCountedRow(source_row=8, reason="New Task blank", strategy="OC", trade="SYNINCS")
    assert not_counted_line(row) == "Not counted: row 8 (OC, SYNINCS) — New Task blank."
    bare = NotCountedRow(source_row=12, reason="New Task is not Yes or No.", strategy="", trade="")
    assert not_counted_line(bare) == "Not counted: row 12 — New Task is not Yes or No."
    assert duplicate_line(9) == "Row 9 is identical to an earlier row and was counted once."


# --------------------------------------------------------------------------- column widths
def test_analysis_widths_fill_the_frame_with_narrow_flags():
    widths = analysis_column_widths(ANALYSIS_COLUMNS, styles.A3_FRAME_WIDTH)
    assert sum(widths) == pytest.approx(styles.A3_FRAME_WIDTH)
    by_header = dict(zip(ANALYSIS_COLUMNS, widths))
    for flag in ("H", "S", "E", "O", "1", "2", "3", "H4", "H5", "S4"):
        assert by_header[flag] == FLAG_WIDTH
    assert by_header["Task"] > by_header["Failure Mode"] > by_header["Trade"] > by_header["No."]


def test_unknown_and_many_columns_still_fit():
    columns = ANALYSIS_COLUMNS + ["SYNTHETIC Extra", ""]
    widths = analysis_column_widths(columns, styles.A3_FRAME_WIDTH)
    assert sum(widths) == pytest.approx(styles.A3_FRAME_WIDTH)
    assert widths[-1] == pytest.approx(widths[-2])
    many = [f"SYNTHETIC column {i}" for i in range(120)]
    assert sum(analysis_column_widths(many, styles.A3_FRAME_WIDTH)) == pytest.approx(styles.A3_FRAME_WIDTH)
    assert analysis_column_widths([], styles.A3_FRAME_WIDTH) == []


# --------------------------------------------------------------------------- merges
def _table(rows, merged, columns=3):
    return AnalysisTable(
        sheet="SYNTHETIC", header_row=1, columns=[f"C{i}" for i in range(columns)],
        column_letters=[chr(65 + i) for i in range(columns)],
        rows=[AnalysisRow(source_row=2 + i, cells=cells) for i, cells in enumerate(rows)],
        merged=merged,
    )


def test_usable_merges_clip_skip_overlaps_and_covered_text():
    rows = [["a", "b", "c"], ["", "x", ""], ["", "y", "z"], ["", "e", "f"]]
    merged = [
        MergedRange(first_row=0, first_col=0, last_row=9, last_col=0),   # clipped to the table
        MergedRange(first_row=1, first_col=0, last_row=2, last_col=0),   # overlaps the first: ignored
        MergedRange(first_row=0, first_col=2, last_row=2, last_col=2),   # covered cell holds "z": ignored
        MergedRange(first_row=3, first_col=1, last_row=3, last_col=1),   # a single cell: ignored
    ]
    usable = usable_merges(_table(rows, merged))
    assert usable == [MergedRange(first_row=0, first_col=0, last_row=3, last_col=0)]


def test_row_bands_join_vertically_merged_rows():
    merges = [MergedRange(first_row=1, first_col=0, last_row=3, last_col=0),
              MergedRange(first_row=3, first_col=1, last_row=4, last_col=1)]
    assert row_bands(7, merges) == [0, 1, 1, 1, 1, 2, 3]


# --------------------------------------------------------------------------- cell text
def _layout(width=120.0):
    return TableLayout([width], [styles.A4_CELL])


def test_cell_single_line_is_a_paragraph_and_blank_is_none():
    layout = _layout()
    assert isinstance(layout.cell("one line", 0), Paragraph)
    assert layout.cell("", 0) is None


def test_multiline_cell_keeps_blank_lines_but_never_starts_a_continuation_with_one():
    layout = _layout()
    cell = layout.cell("first\n\nsecond\nthird", 0)
    assert isinstance(cell, CellText)
    width = layout.content_width(0, 0)
    leading = styles.A4_CELL.leading
    assert cell.wrap(width, 1e6)[1] == pytest.approx(4 * leading)   # the blank line keeps its space
    head, tail = cell.split(width, 1.5 * leading)                     # room for one line only
    assert [line.getPlainText() for line in head.lines] == ["first"]
    assert [line.getPlainText() for line in tail.lines] == ["second", "third"]


def test_continued_marker_fits_a_narrow_column():
    layout = TableLayout([24.0], [styles.A3_CELL], padding=(2.5, 2.5, 2.0, 2.5))
    cell = layout.continued_cell("21", 0)
    width = layout.content_width(0, 0)
    cell.wrap(width, 1e6)
    assert len(cell.blPara.lines) == 2       # "21" then "(cont.)" - the marker itself is not broken
