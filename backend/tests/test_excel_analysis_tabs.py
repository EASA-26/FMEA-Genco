"""One analysis section per tab, and tab names that list several UOIR IDs (design spec 3 and 4).

Every workbook here is the clean SYNTHETIC workbook with one change, so each
test shows exactly which sections and issues that change produces.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.report.builder import build_report

TITLE_603 = "SYNTHETIC Clean Valve Fault During Shutdown"
TWO_ID_TAB = "UOIR ID 602 603 - Clean Valve"
UNLISTED_TAB = "UOIR ID 999 - Clean Pump"
SHARED_TAB = "UOIR ID 0602 - Clean Valve"
DASH_TAB = "UOIR ID 602 - 603 - Clean Valve"
UNREADABLE_TAB = "UOIR 602 - Clean Valve"
TAB_600 = "UOIR ID 600 - Clean Pump"
TITLE_600 = "SYNTHETIC Clean Pump Restart Fault"

# copy_worksheet first names the copy "<name> Copy", which is longer than Excel allows.
copies_tabs = pytest.mark.filterwarnings("ignore:Title is more than 31 characters")


def _build(clean_workbook_with, change):
    return build_report(clean_workbook_with(change), "SYNTHETIC.xlsx")


def _codes(report):
    return [(i.severity, i.code, i.sheet) for i in report.issues]


def _move(wb, ws, index):
    wb.move_sheet(ws, offset=index - wb.index(ws))


@pytest.fixture
def two_id(synthetic_tool):
    """Add UOIR 603 to the UOIR sheet and rename the 602 tab so it covers 602 and 603."""

    def change(wb):
        synthetic_tool.add_uoir_row(wb, 603, TITLE_603, "Clean Valve Positioner")
        wb[synthetic_tool.CLEAN_TAB_602].title = TWO_ID_TAB

    return change


def test_tool_names_tabs_with_several_ids(synthetic_tool):
    assert synthetic_tool.analysis_tab_name([602, 603], "Clean Valve") == TWO_ID_TAB
    assert synthetic_tool.analysis_tab_name(("601",), "Clean Pump Trip") == synthetic_tool.CLEAN_TAB_601


# --------------------------------------------------------------------------- #
# A tab that covers several UOIRs
# --------------------------------------------------------------------------- #
def test_two_id_tab_is_one_section(clean_workbook_with, synthetic_tool, two_id):
    t = synthetic_tool
    report = _build(clean_workbook_with, two_id)
    assert report.uoir_ids == ["601", "602", "603"]
    assert len(report.failure_details) == 3
    assert [(s.sheet_name, s.uoir_ids) for s in report.analyses] == [
        (t.CLEAN_TAB_601, ["601"]), (TWO_ID_TAB, ["602", "603"]),
    ]
    section = report.analyses[1]
    assert section.title == t.CLEAN_TITLE_602                      # from B1
    assert section.equipment == ["Clean Valve", "Clean Valve Positioner"]
    assert section.recommendations[0].heading == "Clean Valve / Clean Valve Positioner, KKS-CLEAN-3"
    assert section.summary.failure_mode_count == 2
    assert report.issues == []
    assert report.can_export is True


def test_multi_id_title_is_b1_and_falls_back(clean_workbook_with, synthetic_tool, two_id):
    def with_b1(value):
        def change(wb):
            two_id(wb)
            wb[TWO_ID_TAB]["B1"] = value

        return change

    topic = _build(clean_workbook_with, with_b1("SYNTHETIC Clean Valve Topic"))
    assert topic.analyses[1].title == "SYNTHETIC Clean Valve Topic"
    blank = _build(clean_workbook_with, with_b1(None))
    assert blank.analyses[1].title == synthetic_tool.CLEAN_TITLE_602   # first listed Title in the tab name
    for report in (topic, blank):
        assert "ANALYSIS_TITLE_CELL_MISMATCH" not in [i.code for i in report.issues]
        assert report.issues == []


def test_multi_id_title_skips_b1_inside_the_table(clean_workbook_with, synthetic_tool, two_id):
    def header_on_row_one(wb):
        two_id(wb)
        wb[TWO_ID_TAB].delete_rows(1)            # B1 is now the "Failure Mode" header

    report = _build(clean_workbook_with, header_on_row_one)
    assert report.analyses[1].title == synthetic_tool.CLEAN_TITLE_602
    assert report.issues == []

    def header_not_found(wb):
        two_id(wb)
        wb[TWO_ID_TAB]["N2"] = "Strategy"
        wb[TWO_ID_TAB]["B1"] = "SYNTHETIC Clean Valve Topic"

    report = _build(clean_workbook_with, header_not_found)
    assert report.analyses[1].title == "SYNTHETIC Clean Valve Topic"   # B1 still counts without a table
    assert _codes(report) == [("error", "ANALYSIS_HEADER_MISSING", TWO_ID_TAB)]


def test_single_uoir_tab_keeps_uoir_sheet_title(clean_workbook_with, synthetic_tool):
    t = synthetic_tool

    def with_b1(value):
        def change(wb):
            wb[t.CLEAN_TAB_602]["B1"] = value

        return change

    same = _build(clean_workbook_with, with_b1(t.CLEAN_TITLE_602.lower()))
    assert same.analyses[1].title == t.CLEAN_TITLE_602
    assert same.issues == []

    other = _build(clean_workbook_with, with_b1("SYNTHETIC Other"))
    assert other.analyses[1].title == t.CLEAN_TITLE_602
    assert _codes(other) == [("warning", "ANALYSIS_TITLE_CELL_MISMATCH", t.CLEAN_TAB_602)]


# --------------------------------------------------------------------------- #
# UOIRs that no tab names, and names that were not read
# --------------------------------------------------------------------------- #
def test_more_uoirs_than_tabs_exports_with_one_info(clean_workbook_with, synthetic_tool, two_id):
    added = {}

    def change(wb):
        two_id(wb)
        added["row"] = synthetic_tool.add_uoir_row(wb, 604, "SYNTHETIC Clean Fan Stop", "Clean Fan")

    report = _build(clean_workbook_with, change)
    assert [(i.severity, i.code, i.sheet, i.uoir_id) for i in report.issues] == [
        ("info", "ANALYSIS_SHEET_MISSING", "UOIR", "604"),
    ]
    assert (report.issues[0].row, report.issues[0].cell) == (added["row"], f"B{added['row']}")
    assert report.can_export is True
    assert len(report.analyses) == 2
    assert report.uoir_ids == ["601", "602", "603", "604"]


def test_uoir_id_not_read_after_a_dash(clean_workbook_with, synthetic_tool):
    def change(wb):
        synthetic_tool.add_uoir_row(wb, 603, TITLE_603, "Clean Valve Positioner")
        wb[synthetic_tool.CLEAN_TAB_602].title = DASH_TAB

    report = _build(clean_workbook_with, change)
    assert _codes(report) == [
        ("warning", "UOIR_ID_NOT_READ", "UOIR"),
        ("warning", "ANALYSIS_SHEET_TITLE_MISMATCH", DASH_TAB),
    ]
    assert report.issues[0].uoir_id == "603"
    assert [s.uoir_ids for s in report.analyses] == [["601"], ["602"]]


def test_unreadable_uoir_sheet_name_warns(clean_workbook_with, synthetic_tool):
    def change(wb):
        wb[synthetic_tool.CLEAN_TAB_602].title = UNREADABLE_TAB

    report = _build(clean_workbook_with, change)
    assert _codes(report) == [
        ("warning", "UOIR_ID_NOT_READ", "UOIR"),
        ("warning", "ANALYSIS_SHEET_NAME_UNREADABLE", UNREADABLE_TAB),
    ]
    unreadable = report.issues[1]
    assert unreadable.uoir_id is None
    assert unreadable.message == (
        f"Sheet '{UNREADABLE_TAB}' looks like an analysis tab, but its name does not start with 'UOIR ID' and "
        "a number, so it is not in the report. Rename it like 'UOIR ID 123 - Title of the UOIR' and upload again."
    )
    assert report.can_export is True
    assert [s.sheet_name for s in report.analyses] == [synthetic_tool.CLEAN_TAB_601]


@pytest.mark.parametrize("misnamed", ["UIOR ID 602 - Clean Valve", "FMEA UOIR ID 602"])
def test_misspelled_tab_name_with_a_listed_id_warns(clean_workbook_with, synthetic_tool, misnamed):
    """A tab the app cannot recognise still points at itself when its name holds an uncovered UOIR ID."""
    def change(wb):
        wb[synthetic_tool.CLEAN_TAB_602].title = misnamed

    report = _build(clean_workbook_with, change)
    assert _codes(report) == [
        ("warning", "UOIR_ID_NOT_READ", "UOIR"),
        ("info", "SHEET_NOT_USED", misnamed),
    ]
    not_read = report.issues[0]
    assert (not_read.row, not_read.cell, not_read.uoir_id) == (6, "B6", "602")
    assert not_read.message == (
        f"UOIR ID 602 appears in the name of tab '{misnamed}', but it was not read as one of the tab's IDs. "
        "Write every ID right after 'UOIR ID', separated by spaces, commas or &, for example "
        "'UOIR ID 123 124 - Title', and upload again."
    )
    assert report.can_export is True
    assert [s.sheet_name for s in report.analyses] == [synthetic_tool.CLEAN_TAB_601]


def test_unused_sheet_without_an_uncovered_id_stays_info(clean_workbook_with, synthetic_tool):
    """Only a number that matches an uncovered UOIR turns the note into a warning."""
    def change(wb):
        wb[synthetic_tool.CLEAN_TAB_602].title = "Valve notes 2026"

    report = _build(clean_workbook_with, change)
    assert _codes(report) == [
        ("info", "ANALYSIS_SHEET_MISSING", "UOIR"),
        ("info", "SHEET_NOT_USED", "Valve notes 2026"),
    ]


# --------------------------------------------------------------------------- #
# Tabs for an ID that is not listed, and IDs named by several tabs
# --------------------------------------------------------------------------- #
def _add_unlisted_tab(synthetic_tool, blank_c3=False):
    def change(wb):
        copy = wb.copy_worksheet(wb[synthetic_tool.CLEAN_TAB_601])
        copy.title = UNLISTED_TAB
        if blank_c3:
            copy["C3"] = None
        _move(wb, copy, 2)

    return change


@copies_tabs
def test_unlisted_tab_is_included_last(clean_workbook_with, synthetic_tool):
    t = synthetic_tool
    report = _build(clean_workbook_with, _add_unlisted_tab(t))
    assert [s.sheet_name for s in report.analyses] == [t.CLEAN_TAB_601, t.CLEAN_TAB_602, UNLISTED_TAB]
    section = report.analyses[2]
    assert section.uoir_ids == ["999"]
    assert section.title == t.CLEAN_TITLE_601                       # B1 of the copied tab
    assert section.equipment == []
    assert section.recommendations[0].heading == "KKS-CLEAN-1"
    assert _codes(report) == [("warning", "ANALYSIS_SHEET_UNLISTED", UNLISTED_TAB)]
    unlisted = report.issues[0]
    assert unlisted.uoir_id == "999"
    assert unlisted.message == (
        f"Tab '{UNLISTED_TAB}' is for UOIR ID 999, which is not in the UOIR list. It is included in the "
        "report. Add UOIR ID 999 to the UOIR sheet if it belongs there."
    )
    assert report.can_export is True


@copies_tabs
def test_error_in_unlisted_tab_blocks_export(clean_workbook_with, synthetic_tool):
    report = _build(clean_workbook_with, _add_unlisted_tab(synthetic_tool, blank_c3=True))
    blank = [i for i in report.issues if i.code == "REQUIRED_VALUE_BLANK"]
    assert [(i.severity, i.sheet, i.cell, i.uoir_id) for i in blank] == [("error", UNLISTED_TAB, "C3", "999")]
    assert report.can_export is False


@copies_tabs
def test_same_id_in_two_tabs_warns_and_keeps_both(clean_workbook_with, synthetic_tool):
    t = synthetic_tool

    def change(wb):
        wb.copy_worksheet(wb[t.CLEAN_TAB_602]).title = SHARED_TAB

    report = _build(clean_workbook_with, change)
    assert [(s.sheet_name, s.uoir_ids) for s in report.analyses] == [
        (t.CLEAN_TAB_601, ["601"]), (t.CLEAN_TAB_602, ["602"]), (SHARED_TAB, ["602"]),
    ]
    assert [(i.severity, i.code, i.sheet, i.row, i.uoir_id) for i in report.issues] == [
        ("warning", "UOIR_IN_SEVERAL_TABS", "UOIR", 6, "602"),
    ]
    assert report.issues[0].message == (
        f"UOIR ID 602 is named in 2 tabs: '{t.CLEAN_TAB_602}' and '{SHARED_TAB}'. Both are in the report. "
        "Check that this is intended."
    )
    assert report.can_export is True


# --------------------------------------------------------------------------- #
# No analysis tab, no UOIR sheet
# --------------------------------------------------------------------------- #
def test_no_analysis_tab_is_an_error_without_missing_infos(clean_workbook_with, synthetic_tool):
    def change(wb):
        wb.remove(wb[synthetic_tool.CLEAN_TAB_601])
        wb.remove(wb[synthetic_tool.CLEAN_TAB_602])

    report = _build(clean_workbook_with, change)
    assert [(i.severity, i.code) for i in report.issues] == [("error", "ANALYSIS_SHEET_NONE")]
    assert report.analyses == []
    assert report.uoir_ids == ["601", "602"]
    assert report.can_export is False


def test_uoir_sheet_missing_adds_no_tab_noise(clean_workbook_with, synthetic_tool):
    t = synthetic_tool
    report = _build(clean_workbook_with, lambda wb: wb.remove(wb["UOIR"]))
    assert [i.code for i in report.issues] == ["SHEET_MISSING"]
    assert report.uoir_ids == []
    assert [s.uoir_ids for s in report.analyses] == [["601"], ["602"]]
    assert [s.title for s in report.analyses] == [t.CLEAN_TITLE_601, t.CLEAN_TITLE_602]   # from B1


# --------------------------------------------------------------------------- #
# Order of sections and issue locations
# --------------------------------------------------------------------------- #
@copies_tabs
def test_sections_follow_uoir_sheet_order_not_tab_order(clean_workbook_with, synthetic_tool, two_id):
    t = synthetic_tool

    def moved(wb):
        two_id(wb)
        _move(wb, wb[TWO_ID_TAB], 2)             # now before the 601 tab

    report = _build(clean_workbook_with, moved)
    assert [s.sheet_name for s in report.analyses] == [t.CLEAN_TAB_601, TWO_ID_TAB]

    def with_600(wb):
        moved(wb)
        t.add_uoir_row(wb, 600, TITLE_600, "Clean Pump")       # listed after 603
        copy = wb.copy_worksheet(wb[t.CLEAN_TAB_601])
        copy.title = TAB_600
        copy["B1"] = TITLE_600
        _move(wb, copy, 2)                       # the first analysis tab in the workbook

    report = _build(clean_workbook_with, with_600)
    assert report.uoir_ids == ["601", "602", "603", "600"]
    assert [s.sheet_name for s in report.analyses] == [t.CLEAN_TAB_601, TWO_ID_TAB, TAB_600]
    assert report.issues == []


def test_tab_issues_carry_joined_ids(clean_workbook_with, two_id):
    def change(wb):
        two_id(wb)
        wb[TWO_ID_TAB]["C3"] = None

    report = _build(clean_workbook_with, change)
    assert [(i.code, i.sheet, i.cell, i.uoir_id) for i in report.issues] == [
        ("REQUIRED_VALUE_BLANK", TWO_ID_TAB, "C3", "602, 603"),
    ]


def test_hidden_two_id_tab_warns_once(clean_workbook_with, two_id):
    def change(wb):
        two_id(wb)
        wb[TWO_ID_TAB].sheet_state = "hidden"

    report = _build(clean_workbook_with, change)
    assert [(i.severity, i.code, i.sheet, i.uoir_id) for i in report.issues] == [
        ("warning", "ANALYSIS_SHEET_HIDDEN", TWO_ID_TAB, "602, 603"),
    ]
    assert report.issues[0].message == (
        f"Tab '{TWO_ID_TAB}' (UOIR ID 602, 603) is hidden in Excel. It is included in the report."
    )
    assert report.analyses[1].analysis is not None


def test_rows_after_blank_uoir_row_message(clean_workbook_with):
    def change(wb):
        ws = wb["UOIR"]
        values = [3, 603, "SYNTHETIC UOIR after a gap", date(2026, 4, 5), date(2026, 4, 25), "CA", "PA", "Eq"]
        for col, value in zip("ABCDEFGH", values):
            ws[f"{col}8"] = value

    report = _build(clean_workbook_with, change)
    assert [(i.severity, i.code, i.sheet, i.row) for i in report.issues] == [
        ("warning", "ROWS_AFTER_BLANK_ROW", "UOIR", 8),
    ]
    assert report.issues[0].message == (
        "Row 8 of 'UOIR' has UOIR ID 603, but the table ends at the empty row 7, so it is not in Failure "
        "Details. Remove the empty rows in between and upload again."
    )
    assert report.uoir_ids == ["601", "602"]
