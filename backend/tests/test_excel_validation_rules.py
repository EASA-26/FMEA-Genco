"""Team Member, UOIR and analysis-tab rules (CONTRACT.md sections 3.3-3.7).

Each test takes the clean SYNTHETIC workbook (which has no issues), changes one
thing and checks the exact issues that result.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.report.builder import build_report

TAB_601 = "UOIR ID 601 - Clean Pump Trip"
TAB_602 = "UOIR ID 602 - Clean Valve Fault"


def _build(clean_workbook_with, change):
    return build_report(clean_workbook_with(change), "SYNTHETIC.xlsx")


def _issues(report):
    return [(i.severity, i.code, i.sheet, i.row, i.cell) for i in report.issues]


# --------------------------------------------------------------------------- #
# Sheets
# --------------------------------------------------------------------------- #
def test_team_member_sheet_missing(clean_workbook_with):
    report = _build(clean_workbook_with, lambda wb: wb.remove(wb["Team Member"]))
    assert _issues(report) == [("error", "SHEET_MISSING", None, None, None)]
    assert "'Team Member'" in report.issues[0].message
    assert (report.station, report.analysis_date, report.team) == ("", None, [])
    assert report.pdf_filename == "FMEA_Report_Station_undated.pdf"
    assert report.can_export is False


def test_uoir_sheet_missing(clean_workbook_with):
    report = _build(clean_workbook_with, lambda wb: wb.remove(wb["UOIR"]))
    # No UOIR row was read, so the tabs are not reported as unlisted; they are still read.
    assert _issues(report) == [("error", "SHEET_MISSING", None, None, None)]
    assert report.uoir_ids == []
    assert [s.sheet_name for s in report.analyses] == [TAB_601, TAB_602]


def test_sheet_names_match_trimmed_and_case_insensitive(clean_workbook_with):
    def rename(wb):
        # openpyxl refuses a case-only rename in one step, so go through a temporary name.
        for old, new in (("Team Member", "TEAM MEMBER "), ("UOIR", "uoir"), ("Notifications", "notifications")):
            wb[old].title = "SYNTHETIC temporary"
            wb["SYNTHETIC temporary"].title = new

    report = _build(clean_workbook_with, rename)
    assert report.issues == []
    assert report.station == "SYNTHETIC Clean Station"


def test_other_sheet_is_not_used(clean_workbook_with):
    report = _build(clean_workbook_with, lambda wb: wb.create_sheet("Workings"))
    assert _issues(report) == [("info", "SHEET_NOT_USED", "Workings", None, None)]
    assert report.issues[0].message == "Sheet 'Workings' is not used in the report."
    assert report.can_export is True


# --------------------------------------------------------------------------- #
# Team Member
# --------------------------------------------------------------------------- #
def test_station_blank(clean_workbook_with):
    def blank(wb):
        wb["Team Member"]["B2"] = "\xa0"

    report = _build(clean_workbook_with, blank)
    assert _issues(report) == [("error", "STATION_BLANK", "Team Member", 2, "B2")]
    assert report.pdf_filename == "FMEA_Report_Station_2026-06-15.pdf"


def test_analysis_date_blank(clean_workbook_with):
    def blank(wb):
        wb["Team Member"]["B3"] = None

    report = _build(clean_workbook_with, blank)
    assert _issues(report) == [("error", "ANALYSIS_DATE_BLANK", "Team Member", 3, "B3")]
    assert report.analysis_date_text == ""


@pytest.mark.parametrize("value", ["next week", 46000, "31/02/2026"])
def test_analysis_date_invalid(clean_workbook_with, value):
    def invalid(wb):
        wb["Team Member"]["B3"] = value
        wb["Team Member"]["B3"].number_format = "General"   # a plain number, not an Excel date

    report = _build(clean_workbook_with, invalid)
    assert _issues(report) == [("error", "ANALYSIS_DATE_INVALID", "Team Member", 3, "B3")]
    assert report.analysis_date is None


@pytest.mark.parametrize(
    "text",
    ["15/06/2026", "15-06-2026", "15.06.2026", "15-Jun-26", "15-Jun-2026", "15 June 2026", "15 Jun 2026",
     "2026-06-15", " 15/06/2026\xa0"],
)
def test_analysis_date_as_text(clean_workbook_with, text):
    def as_text(wb):
        wb["Team Member"]["B3"] = text

    report = _build(clean_workbook_with, as_text)
    assert report.issues == []
    assert report.analysis_date == date(2026, 6, 15)


def test_analysis_date_with_time_uses_the_date(clean_workbook_with):
    def with_time(wb):
        wb["Team Member"]["B3"] = datetime(2026, 6, 15, 9, 30)

    report = _build(clean_workbook_with, with_time)
    assert (report.analysis_date, report.analysis_date_text) == (date(2026, 6, 15), "15 June 2026")


def test_unexpected_labels(clean_workbook_with):
    def relabel(wb):
        wb["Team Member"]["A2"] = "Plant"
        wb["Team Member"]["A3"] = None

    report = _build(clean_workbook_with, relabel)
    assert _issues(report) == [
        ("warning", "LABEL_UNEXPECTED", "Team Member", 2, "A2"),
        ("warning", "LABEL_UNEXPECTED", "Team Member", 3, "A3"),
    ]
    assert "'Plant'" in report.issues[0].message
    assert "it is empty" in report.issues[1].message


def test_team_header_not_found(clean_workbook_with):
    def rename(wb):
        wb["Team Member"]["B5"] = "Full name"

    report = _build(clean_workbook_with, rename)
    assert _issues(report) == [("error", "TEAM_HEADER_MISSING", "Team Member", None, None)]
    assert report.team == []


def test_team_column_missing(clean_workbook_with):
    def remove_section(wb):
        wb["Team Member"]["D5"] = None

    report = _build(clean_workbook_with, remove_section)
    assert _issues(report) == [("error", "TEAM_HEADER_MISSING", "Team Member", 5, None)]
    assert "'Section'" in report.issues[0].message
    assert [(m.name, m.section) for m in report.team] == [("Synthetic Person A", ""), ("Synthetic Person B", "")]


def test_team_empty_with_prefilled_numbers(clean_workbook_with):
    def clear(wb):
        for row in (6, 7):
            for col in "BCD":
                wb["Team Member"][f"{col}{row}"] = None

    report = _build(clean_workbook_with, clear)
    assert _issues(report) == [("warning", "TEAM_EMPTY", "Team Member", 5, None)]


def test_team_ends_at_first_blank_member_row(clean_workbook_with):
    def add_after_gap(wb):
        ws = wb["Team Member"]
        ws["A8"] = 3                       # pre-filled No only
        ws["A9"] = 4
        ws["B9"] = "Synthetic Person After Gap"

    report = _build(clean_workbook_with, add_after_gap)
    assert [m.source_row for m in report.team] == [6, 7]


# --------------------------------------------------------------------------- #
# UOIR sheet
# --------------------------------------------------------------------------- #
def test_uoir_column_missing(clean_workbook_with):
    def remove(wb):
        wb["UOIR"]["H4"] = None

    report = _build(clean_workbook_with, remove)
    assert _issues(report) == [("error", "UOIR_HEADER_MISSING", "UOIR", 4, None)]
    assert "'Equipment'" in report.issues[0].message
    assert report.analyses[0].equipment == []
    assert report.analyses[0].recommendations[0].heading == "KKS-CLEAN-1"


def test_uoir_header_not_found(clean_workbook_with):
    def rename(wb):
        wb["UOIR"]["B4"] = "Reference"

    report = _build(clean_workbook_with, rename)
    # No UOIR row was read, so the tabs are not reported as unlisted.
    assert [(s, c, sh) for s, c, sh, _, _ in _issues(report)] == [("error", "UOIR_HEADER_MISSING", "UOIR")]


def test_uoir_id_blank(clean_workbook_with):
    def blank(wb):
        wb["UOIR"]["B6"] = "\xa0"

    report = _build(clean_workbook_with, blank)
    assert _issues(report) == [
        ("error", "UOIR_VALUE_BLANK", "UOIR", 6, "B6"),
        ("warning", "ANALYSIS_SHEET_UNLISTED", TAB_602, None, None),
    ]
    assert report.issues[0].message == "UOIR ID is empty on row 6 of 'UOIR'. Fill it in and upload again."
    assert len(report.failure_details) == 2          # the row is still shown
    assert report.uoir_ids == ["601"]


def test_uoir_none(clean_workbook_with):
    def clear(wb):
        for row in (5, 6):
            for col in "ABCDEFGH":
                wb["UOIR"][f"{col}{row}"] = None

    report = _build(clean_workbook_with, clear)
    # No UOIR row was read, so the tabs are not reported as unlisted.
    assert [(s, c, sh) for s, c, sh, _, _ in _issues(report)] == [("error", "UOIR_NONE", "UOIR")]


def test_uoir_rows_end_at_first_blank_row_even_with_no_prefilled(clean_workbook_with):
    def extend(wb):
        wb["UOIR"]["A7"] = 3                      # No only: ends the list
        wb["UOIR"]["B8"] = 603

    report = _build(clean_workbook_with, extend)
    assert [d.source_row for d in report.failure_details] == [5, 6]
    assert report.issues == []


def test_uoir_equipment_blank(clean_workbook_with):
    def blank(wb):
        wb["UOIR"]["H6"] = None

    report = _build(clean_workbook_with, blank)
    assert _issues(report) == [("warning", "UOIR_EQUIPMENT_BLANK", "UOIR", 6, "H6")]
    assert report.analyses[1].recommendations[0].heading == "KKS-CLEAN-3"


def test_uoir_listed_twice_with_different_title(clean_workbook_with):
    def add_row(wb):
        ws = wb["UOIR"]
        for col, value in zip("ABCDEFGH", [3, 601, "SYNTHETIC Another Title", date(2026, 3, 1), date(2026, 3, 20),
                                            "CA", "PA", "Clean Pump Motor"]):
            ws[f"{col}7"] = value

    report = _build(clean_workbook_with, add_row)
    assert _issues(report) == [("warning", "UOIR_DUPLICATE_ID_CONFLICT", "UOIR", 7, "C7")]
    section = report.analyses[0]
    assert section.title == "SYNTHETIC Clean Pump Trip on Low Flow"
    assert section.equipment == ["Clean Pump", "Clean Pump Motor"]
    assert len(report.failure_details) == 3 and len(report.uoir_ids) == 2


def test_uoir_date_with_time_and_text_date(clean_workbook_with):
    def change(wb):
        wb["UOIR"]["D5"] = datetime(2026, 3, 1, 8, 36)
        wb["UOIR"]["E6"] = "20-Apr-2026"

    report = _build(clean_workbook_with, change)
    assert report.issues == []
    first, second = report.failure_details
    assert (first.faulty_date, first.faulty_date_text) == (date(2026, 3, 1), "1 March 2026 08:36")
    assert (second.uoir_date, second.uoir_date_text) == (date(2026, 4, 20), "20 April 2026")


def test_date_of_analysis_not_compared_with_fault_dates(clean_workbook_with):
    # Date of Analysis is taken from B3 as written, even when it is earlier than the fault dates.
    def earlier(wb):
        wb["Team Member"]["B3"] = date(2026, 3, 15)

    report = _build(clean_workbook_with, earlier)
    assert report.issues == []
    assert (report.analysis_date, report.analysis_date_text) == (date(2026, 3, 15), "15 March 2026")
    assert report.can_export is True


# --------------------------------------------------------------------------- #
# Analysis tab
# --------------------------------------------------------------------------- #
def test_analysis_header_not_found(clean_workbook_with):
    def rename(wb):
        wb[TAB_601]["N2"] = "Strategy"

    report = _build(clean_workbook_with, rename)
    assert _issues(report) == [("error", "ANALYSIS_HEADER_MISSING", TAB_601, None, None)]
    section = report.analyses[0]
    assert (section.sheet_name, section.analysis, section.summary, section.tasks) == (TAB_601, None, None, [])


def test_analysis_header_beyond_search_rows(clean_workbook_with):
    report = _build(clean_workbook_with, lambda wb: wb[TAB_602].insert_rows(1, amount=14))
    assert _issues(report) == [("error", "ANALYSIS_HEADER_MISSING", TAB_602, None, None)]


def test_analysis_required_column_missing(clean_workbook_with):
    def remove(wb):
        wb[TAB_601]["R2"] = None

    report = _build(clean_workbook_with, remove)
    assert _issues(report) == [("error", "ANALYSIS_HEADER_MISSING", TAB_601, 2, None)]
    assert "'KKS'" in report.issues[0].message
    section = report.analyses[0]
    assert section.analysis.columns[17] == ""       # kept: the blank-header column holds data
    assert (section.tasks, section.summary, section.recommendations) == ([], None, [])


def test_analysis_header_duplicate(clean_workbook_with):
    def duplicate(wb):
        wb[TAB_601]["V2"] = "task"

    report = _build(clean_workbook_with, duplicate)
    assert _issues(report) == [("error", "ANALYSIS_HEADER_DUPLICATE", TAB_601, 2, "V2")]
    assert report.analyses[0].summary is None


def test_analysis_no_rows(clean_workbook_with):
    def clear(wb):
        ws = wb[TAB_601]
        ws.delete_rows(3, 4)

    report = _build(clean_workbook_with, clear)
    assert _issues(report) == [("error", "ANALYSIS_NO_ROWS", TAB_601, 2, None)]
    section = report.analyses[0]
    assert section.analysis.rows == []
    assert section.summary.failure_mode_count == 0
    assert section.summary.pie == [] and section.summary.pie_total == 0
    assert [r.total for r in section.summary.strategy_rows] == [0] * 7


def test_table_ends_at_first_blank_row_and_rest_become_notes(clean_workbook_with):
    def extend(wb):
        ws = wb[TAB_602]
        ws["A5"] = 3                                  # pre-filled No. only: ends the table
        ws["B6"] = "SYNTHETIC stray text after the gap"

    report = _build(clean_workbook_with, extend)
    section = report.analyses[1]
    assert [r.source_row for r in section.analysis.rows] == [3, 4]
    # The pre-filled row number (A5) is template numbering and is not shown as a note.
    assert [(n.cell, n.text) for n in section.notes] == [("B6", "SYNTHETIC stray text after the gap")]
    assert report.issues == []


def test_blank_strategy_is_required_and_shown_as_not_specified(clean_workbook_with):
    def blank(wb):
        wb[TAB_601]["N4"] = None

    report = _build(clean_workbook_with, blank)
    assert _issues(report) == [("error", "REQUIRED_VALUE_BLANK", TAB_601, 4, "N4")]
    rows = report.analyses[0].summary.strategy_rows
    assert (rows[-1].code, rows[-1].label, rows[-1].existing, rows[-1].new, rows[-1].total, rows[-1].standard) == (
        "", "Not specified", 0, 1, 1, False,
    )
    assert "SR" in [r.code for r in rows]              # standard rows always shown
    assert report.analyses[0].summary.pie[-1].code == ""


def test_blank_frequency_and_nsm_new_task_are_allowed(clean_workbook_bytes):
    report = build_report(clean_workbook_bytes, "SYNTHETIC.xlsx")
    tasks = report.analyses[0].tasks
    assert tasks[2].strategy_code == "NSM" and tasks[2].new_task == "blank"
    assert tasks[3].frequency == ""
    assert report.issues == []


def test_nsm_with_invalid_new_task_is_an_error_but_not_listed_as_not_counted(clean_workbook_with):
    def invalid(wb):
        wb[TAB_601]["S5"] = "TBC"

    report = _build(clean_workbook_with, invalid)
    assert _issues(report) == [("error", "NEW_TASK_INVALID", TAB_601, 5, "S5")]
    assert report.analyses[0].summary.not_counted == []


def test_duplicate_ignores_the_no_column_only(clean_workbook_with):
    def duplicate(wb):
        ws = wb[TAB_602]
        for col in range(1, 23):
            ws.cell(row=5, column=col, value=ws.cell(row=4, column=col).value)
        ws["A5"] = 99                                   # different No.
        ws["A6"] = 100
        for col in range(2, 23):
            ws.cell(row=6, column=col, value=ws.cell(row=4, column=col).value)
        ws["P6"] = "12M"                                # differs only in Frequency: counted

    report = _build(clean_workbook_with, duplicate)
    assert _issues(report) == [("warning", "DUPLICATE_ROW", TAB_602, 5, None)]
    summary = report.analyses[1].summary
    assert summary.failure_mode_count == 3
    assert summary.duplicate_rows == [5]
    assert [r.source_row for g in report.analyses[1].recommendations for r in g.rows] == [3, 4, 6]
