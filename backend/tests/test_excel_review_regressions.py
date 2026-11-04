"""Regression tests for defects found in the parser review.

Every workbook here is the clean SYNTHETIC workbook with one change, so each
test shows exactly which issues (and derived values) that change produces.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.excel.reader import SheetGrid, clean_text
from backend.report.builder import build_report
from backend.report.models import MergedRange

TAB_601 = "UOIR ID 601 - Clean Pump Trip"
TAB_602 = "UOIR ID 602 - Clean Valve Fault"
TITLE_601 = "SYNTHETIC Clean Pump Trip on Low Flow"


def _build(clean_workbook_with, change):
    return build_report(clean_workbook_with(change), "SYNTHETIC.xlsx")


def _issues(report):
    return [(i.severity, i.code, i.sheet, i.row, i.cell) for i in report.issues]


def _copy_row(ws, source_row, target_row, **overrides):
    """Copy one analysis row (columns A..V) and change some cells, e.g. B="New mode"."""
    for col in range(1, 23):
        ws.cell(row=target_row, column=col, value=ws.cell(row=source_row, column=col).value)
    for letter, value in overrides.items():
        ws[f"{letter}{target_row}"] = value


# --------------------------------------------------------------------------- #
# B1 is a header, not the title, when the header row is row 1
# --------------------------------------------------------------------------- #
def test_header_on_row_one_does_not_compare_b1_with_the_title(clean_workbook_with):
    report = _build(clean_workbook_with, lambda wb: wb[TAB_601].delete_rows(1))
    assert report.issues == []          # previously: ANALYSIS_TITLE_CELL_MISMATCH ('Failure Mode')
    section = report.uoirs[0]
    assert section.analysis.header_row == 1
    assert [r.source_row for r in section.analysis.rows] == [2, 3, 4, 5]
    assert section.summary.failure_mode_count == 4


def test_title_cell_is_still_checked_when_the_header_is_not_found(clean_workbook_with):
    def change(wb):
        wb[TAB_601]["N2"] = "Strategy"
        wb[TAB_601]["B1"] = "SYNTHETIC A Different Title"

    report = _build(clean_workbook_with, change)
    assert _issues(report) == [
        ("error", "ANALYSIS_HEADER_MISSING", TAB_601, None, None),
        ("warning", "ANALYSIS_TITLE_CELL_MISMATCH", TAB_601, 1, "B1"),
    ]


# --------------------------------------------------------------------------- #
# Merged cells: carry down a column, only from a merge that starts on a data row
# --------------------------------------------------------------------------- #
def test_header_merged_into_data_rows_is_not_copied_into_the_data(clean_workbook_with):
    def change(wb):
        ws = wb[TAB_601]
        ws.merge_cells("B2:B4")          # "Failure Mode" header merged over rows 3-4

    report = _build(clean_workbook_with, change)
    # Previously rows 3-4 got the failure mode "Failure Mode" and no issue at all.
    assert _issues(report) == [
        ("error", "REQUIRED_VALUE_BLANK", TAB_601, 3, "B3"),
        ("error", "REQUIRED_VALUE_BLANK", TAB_601, 4, "B4"),
    ]
    section = report.uoirs[0]
    assert section.analysis.header_row == 2
    assert [t.failure_mode for t in section.tasks[:2]] == ["", ""]
    assert section.analysis.merged == [MergedRange(first_row=0, first_col=1, last_row=1, last_col=1)]
    assert [row.cells[1] for row in section.analysis.rows[:2]] == ["", ""]


def test_uoir_header_merged_down_is_not_used_as_equipment(clean_workbook_with):
    def change(wb):
        wb["UOIR"]["H5"] = None
        wb["UOIR"].merge_cells("H4:H5")

    report = _build(clean_workbook_with, change)
    assert _issues(report) == [("warning", "UOIR_EQUIPMENT_BLANK", "UOIR", 5, "H5")]
    assert report.failure_details[0].equipment == ""          # previously "Equipment"
    assert report.uoirs[0].equipment == []
    assert report.uoirs[0].recommendations[0].heading == "KKS-CLEAN-1"


def test_team_header_merged_down_is_not_used_as_a_value(clean_workbook_with):
    seen = {}

    def change(wb):
        seen["section_b"] = clean_text(wb["Team Member"]["D7"].value)   # Person B's own Section, untouched
        wb["Team Member"]["D6"] = None
        wb["Team Member"].merge_cells("D5:D6")

    report = _build(clean_workbook_with, change)
    assert report.issues == []
    assert seen["section_b"]
    assert [(m.name, m.section) for m in report.team] == [
        ("Synthetic Person A", ""), ("Synthetic Person B", seen["section_b"]),
    ]


def test_value_merged_sideways_is_not_copied_into_the_next_column(clean_workbook_with):
    seen = {}

    def change(wb):
        seen["trade"] = clean_text(wb[TAB_601]["Q3"].value)
        wb[TAB_601].merge_cells("Q3:R3")     # Trade merged over KKS on row 3

    report = _build(clean_workbook_with, change)
    # Previously KKS silently became the Trade code and a separate recommendation group appeared.
    assert _issues(report) == [("error", "REQUIRED_VALUE_BLANK", TAB_601, 3, "R3")]
    trade = seen["trade"]
    assert trade
    section = report.uoirs[0]
    assert (section.tasks[0].trade, section.tasks[0].kks) == (trade, "")
    assert section.analysis.rows[0].cells[16:18] == [trade, ""]
    assert section.analysis.merged == [MergedRange(first_row=0, first_col=16, last_row=0, last_col=17)]


def test_block_merge_carries_down_its_own_column_only(clean_workbook_with):
    seen = {}

    def change(wb):
        seen["mode"] = clean_text(wb[TAB_602]["B3"].value)
        wb[TAB_602].merge_cells("B3:C4")     # Failure Mode + Failure Effect as one block over two rows

    report = _build(clean_workbook_with, change)
    assert _issues(report) == [
        ("error", "REQUIRED_VALUE_BLANK", TAB_602, 3, "C3"),
        ("error", "REQUIRED_VALUE_BLANK", TAB_602, 4, "C4"),
        ("info", "MERGED_CELLS_CARRIED", TAB_602, None, None),
    ]
    carried = next(i for i in report.issues if i.code == "MERGED_CELLS_CARRIED")
    assert "cover several rows in Failure Mode." in carried.message      # Failure Effect is not carried
    tasks = report.uoirs[1].tasks
    assert seen["mode"]
    assert [(t.failure_mode, t.failure_effect) for t in tasks] == [
        (seen["mode"], ""), (seen["mode"], ""),
    ]


def test_merge_running_past_the_end_of_the_table_is_clipped(clean_workbook_with):
    def change(wb):
        ws = wb[TAB_601]
        ws.merge_cells("N5:N9")          # NSM strategy merged from row 5 down past the last data row (6)

    report = _build(clean_workbook_with, change)
    section = report.uoirs[0]
    assert [r.source_row for r in section.analysis.rows] == [3, 4, 5, 6]
    assert section.analysis.merged == [MergedRange(first_row=2, first_col=13, last_row=3, last_col=13)]
    assert [t.strategy_code for t in section.tasks] == ["OC", "SR", "NSM", "NSM"]
    assert section.notes == []
    assert _issues(report) == [
        ("warning", "NSM_NEW_TASK_FILLED", TAB_601, 6, "S6"),
        ("info", "MERGED_CELLS_CARRIED", TAB_601, None, None),
    ]


# --------------------------------------------------------------------------- #
# Linking and cell values
# --------------------------------------------------------------------------- #
def test_tab_id_must_match_exactly_not_as_a_prefix(clean_workbook_with):
    def rename(wb):
        wb[TAB_601].title = "UOIR ID 60 - Clean Pump Trip"

    report = _build(clean_workbook_with, rename)
    assert [(i.severity, i.code, i.sheet) for i in report.issues] == [
        ("error", "ANALYSIS_SHEET_MISSING", "UOIR"),
        ("warning", "ANALYSIS_SHEET_UNLISTED", "UOIR ID 60 - Clean Pump Trip"),
    ]
    assert report.uoirs[0].analysis is None


def test_staff_numbers_stored_as_decimals_or_text_keep_their_digits(clean_workbook_with):
    def change(wb):
        wb["Team Member"]["C6"] = 11112222.0
        wb["Team Member"]["C7"] = "0033334444"

    report = _build(clean_workbook_with, change)
    assert report.issues == []
    assert [m.staff_no for m in report.team] == ["11112222", "0033334444"]


# --------------------------------------------------------------------------- #
# Rows typed below the empty row that ends a table
# --------------------------------------------------------------------------- #
def test_analysis_rows_after_an_empty_row_are_reported(clean_workbook_with):
    def change(wb):
        ws = wb[TAB_602]
        _copy_row(ws, 4, 6, A=3, B="SYNTHETIC mode after a gap")
        _copy_row(ws, 4, 7, A=4, B="SYNTHETIC second mode after a gap")

    report = _build(clean_workbook_with, change)
    assert _issues(report) == [("warning", "ROWS_AFTER_BLANK_ROW", TAB_602, 6, None)]
    issue = report.issues[0]
    assert issue.uoir_id == "602"
    assert issue.message == (
        f"Rows 6 and 7 of '{TAB_602}' have analysis values, but the table ends at the empty row 5, so they are "
        "not in the table or the counts. Remove the empty rows in between and upload again."
    )
    section = report.uoirs[1]
    assert [r.source_row for r in section.analysis.rows] == [3, 4]
    assert section.summary.failure_mode_count == 2
    assert report.can_export is True


def test_many_rows_after_an_empty_row_are_summarised(clean_workbook_with):
    def change(wb):
        ws = wb[TAB_602]
        for row in range(6, 16):
            _copy_row(ws, 4, row, A=row, B=f"SYNTHETIC mode {row}")

    report = _build(clean_workbook_with, change)
    assert report.issues[0].message.startswith(
        f"Rows 6, 7, 8, 9, 10, 11, 12, 13 and 2 more of '{TAB_602}' have analysis values"
    )


def test_notes_and_numbers_below_the_table_are_not_reported_as_rows(clean_workbook_with):
    def change(wb):
        ws = wb[TAB_601]
        ws["A7"] = 5                                          # pre-filled No. only
        ws["B12"] = "Root Cause (SYNTHETIC) - worn impeller"
        ws["C12"] = "SYNTHETIC explanation next to it"

    report = _build(clean_workbook_with, change)
    assert report.issues == []
    # A pre-filled row number in the No. column is template numbering, not a note.
    assert [n.cell for n in report.uoirs[0].notes] == ["B12", "C12"]


def test_text_in_the_no_column_below_the_table_is_still_a_note(clean_workbook_with):
    def change(wb):
        wb[TAB_601]["A9"] = "SYNTHETIC reviewed 2026"

    report = _build(clean_workbook_with, change)
    assert [(n.cell, n.text) for n in report.uoirs[0].notes] == [("A9", "SYNTHETIC reviewed 2026")]


def test_team_member_after_an_empty_row_is_reported(clean_workbook_with):
    def change(wb):
        ws = wb["Team Member"]
        ws["A9"], ws["B9"], ws["C9"], ws["D9"] = 3, "Synthetic Person C", 55556666, "SYNTHETIC C&I"
        ws["B12"] = "Prepared by (SYNTHETIC)"                  # a signature line is not a member

    report = _build(clean_workbook_with, change)
    assert _issues(report) == [("warning", "ROWS_AFTER_BLANK_ROW", "Team Member", 9, None)]
    assert report.issues[0].message == (
        "Row 9 of 'Team Member' has a team member, but the table ends at the empty row 8, so it is not in the "
        "report. Remove the empty rows in between and upload again."
    )
    assert [m.source_row for m in report.team] == [6, 7]


def test_uoir_after_an_empty_row_is_reported(clean_workbook_with):
    def change(wb):
        ws = wb["UOIR"]
        values = [3, 603, "SYNTHETIC UOIR after a gap", date(2026, 4, 5), date(2026, 4, 25), "CA", "PA", "Eq"]
        for col, value in zip("ABCDEFGH", values):
            ws[f"{col}8"] = value

    report = _build(clean_workbook_with, change)
    assert _issues(report) == [("warning", "ROWS_AFTER_BLANK_ROW", "UOIR", 8, None)]
    issue = report.issues[0]
    assert issue.uoir_id == "603"
    assert issue.message == (
        "Row 8 of 'UOIR' has UOIR ID 603, but the table ends at the empty row 7, so it is not in the report. "
        "Remove the empty rows in between and upload again."
    )
    assert [u.uoir_id for u in report.uoirs] == ["601", "602"]


# --------------------------------------------------------------------------- #
# Blank Title on the UOIR sheet
# --------------------------------------------------------------------------- #
def _add_uoir_row(ws, row, uoir_id, title, equipment):
    values = [row - 4, uoir_id, title, date(2026, 3, 1), date(2026, 3, 20), "CA (SYNTHETIC)", "PA (SYNTHETIC)", equipment]
    for col, value in zip("ABCDEFGH", values):
        ws[f"{col}{row}"] = value


def test_blank_title_adds_no_title_mismatch_warnings(clean_workbook_with):
    def change(wb):
        wb["UOIR"]["C5"] = None

    report = _build(clean_workbook_with, change)
    # Previously also: ANALYSIS_SHEET_TITLE_MISMATCH and ANALYSIS_TITLE_CELL_MISMATCH against an empty title.
    assert _issues(report) == [("error", "UOIR_VALUE_BLANK", "UOIR", 5, "C5")]
    assert report.uoirs[0].sheet_name == TAB_601


def test_title_given_on_a_later_row_is_used_when_the_first_is_blank(clean_workbook_with):
    def change(wb):
        ws = wb["UOIR"]
        ws["C5"] = None
        _add_uoir_row(ws, 7, 601, TITLE_601, "Clean Pump Motor")
        _add_uoir_row(ws, 8, 601, "SYNTHETIC Another Title", "Clean Pump Motor")

    report = _build(clean_workbook_with, change)
    assert _issues(report) == [
        ("error", "UOIR_VALUE_BLANK", "UOIR", 5, "C5"),
        ("warning", "UOIR_DUPLICATE_ID_CONFLICT", "UOIR", 8, "C8"),
    ]
    assert report.uoirs[0].title == TITLE_601
    assert report.issues[1].message.endswith("The Title from row 7 is used.")


# --------------------------------------------------------------------------- #
# Cell text and messages
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("value", "number_format", "expected"),
    [(-5, "0000", "-0005"), (-1234.0, "00000000", "-00001234"), (0, "000", "000")],
)
def test_zero_padding_keeps_the_sign_in_front(value, number_format, expected):
    assert clean_text(value, number_format) == expected


def test_multiline_header_reads_as_one_line_in_messages(clean_workbook_with):
    def change(wb):
        wb[TAB_601]["C2"] = "Failure\nEffect"
        wb[TAB_601]["C3"] = None

    report = _build(clean_workbook_with, change)
    issue = report.issues[0]
    assert (issue.code, issue.column) == ("REQUIRED_VALUE_BLANK", "Failure\nEffect")
    assert issue.message == f"Failure Effect is empty on row 3 of '{TAB_601}'. Fill it in and upload again."


# --------------------------------------------------------------------------- #
# Scans stay cheap on sheets with stray far-away cells
# --------------------------------------------------------------------------- #
def test_empty_cells_are_not_cached_and_row_scan_uses_stored_cells():
    grid = SheetGrid(name="SYNTHETIC")
    grid.cells = {(3, 2): ("Pump", None), (900000, 2): ("SYNTHETIC stray", None), (900000, 5): ("\xa0", None)}
    grid.finish()
    assert grid.text(10, 10) == "" and grid.text(11, 3) == ""
    assert (10, 10) not in grid._text_cache
    assert grid.rows_with_text([2, 5], 4) == [900000]
    assert grid.rows_with_text([5], 1) == []


def test_stray_value_far_below_the_table_is_a_note_only(clean_workbook_with):
    def change(wb):
        wb[TAB_601].cell(row=5000, column=3, value="SYNTHETIC stray value")
        wb["Team Member"].cell(row=5000, column=2, value="SYNTHETIC stray value")

    report = _build(clean_workbook_with, change)
    assert report.issues == []
    assert [(n.cell, n.text) for n in report.uoirs[0].notes] == [("C5000", "SYNTHETIC stray value")]
