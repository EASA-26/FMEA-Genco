"""Issue ids, which issues can be accepted, and the export rule (accept-issues design spec 3 and 4.1).

Every workbook here is SYNTHETIC: the edge-case workbook, or the clean workbook
with one change.
"""
from __future__ import annotations

import re
from collections import Counter

from backend.config.mapping import ACCEPTABLE_ERROR_CODES, ANALYSIS_REQUIRED_VALUES
from backend.report.builder import build_report
from backend.report.models import export_allowed


def _build(data: bytes):
    return build_report(data, "SYNTHETIC.xlsx")


def _all_blank_rows(report) -> set[tuple[str, int]]:
    """(sheet, row) of analysis rows whose every required value is blank."""
    blanks = Counter((i.sheet, i.row) for i in report.issues if i.code == "REQUIRED_VALUE_BLANK")
    return {key for key, count in blanks.items() if count == len(ANALYSIS_REQUIRED_VALUES)}


def test_issue_ids_follow_report_order(edge_workbook_bytes):
    report = _build(edge_workbook_bytes)
    assert len(report.issues) > 5
    assert [i.id for i in report.issues] == [str(n) for n in range(1, len(report.issues) + 1)]


def test_acceptable_by_code_group(edge_workbook_bytes):
    report = _build(edge_workbook_bytes)
    severities = {i.severity for i in report.issues}
    assert severities == {"error", "warning", "info"}       # the workbook exercises every group
    all_blank = _all_blank_rows(report)
    for issue in report.issues:
        if issue.severity == "warning":
            assert issue.acceptable is True, issue.code
        elif issue.severity == "info":
            assert issue.acceptable is False, issue.code
        else:
            expected = issue.code in ACCEPTABLE_ERROR_CODES and (issue.sheet, issue.row) not in all_blank
            assert issue.acceptable is expected, issue.code
        assert issue.accepted is False


def test_report_id_differs_between_builds(clean_workbook_bytes):
    first, second = _build(clean_workbook_bytes), _build(clean_workbook_bytes)
    for report in (first, second):
        assert re.fullmatch(r"[0-9a-f]{16}", report.report_id)
    assert first.report_id != second.report_id


def test_can_export_unchanged_when_nothing_accepted(clean_workbook_with, synthetic_tool):
    def blank_kks(wb):
        wb[synthetic_tool.CLEAN_TAB_601]["R3"] = None      # KKS of the first analysis row

    assert _build(clean_workbook_with(lambda wb: None)).can_export is True
    report = _build(clean_workbook_with(blank_kks))
    assert [i.code for i in report.issues] == ["REQUIRED_VALUE_BLANK"]
    assert report.can_export is False


def test_all_blank_row_is_not_acceptable(clean_workbook_with, synthetic_tool):
    tab = synthetic_tool.CLEAN_TAB_601

    def change(wb):
        ws = wb[tab]
        ws["A7"] = 5            # No.
        ws["P7"] = "1M"         # Frequency: the only other filled cell of row 7
        ws["R3"] = None         # a real analysis row with a blank KKS

    report = _build(clean_workbook_with(change))
    row_7 = [i for i in report.issues if i.code == "REQUIRED_VALUE_BLANK" and (i.sheet, i.row) == (tab, 7)]
    assert len(row_7) == len(ANALYSIS_REQUIRED_VALUES)
    assert all(i.acceptable is False for i in row_7)
    row_3 = [i for i in report.issues if i.code == "REQUIRED_VALUE_BLANK" and (i.sheet, i.row) == (tab, 3)]
    assert [(i.cell, i.acceptable) for i in row_3] == [("R3", True)]


def test_invalid_date_keeps_its_text(clean_workbook_with):
    def change(wb):
        wb["Team Member"]["B3"] = "TBC June 2026"

    report = _build(clean_workbook_with(change))
    assert report.analysis_date is None
    assert report.analysis_date_text == "TBC June 2026"
    assert report.pdf_filename.endswith("_undated.pdf")
    invalid = [i for i in report.issues if i.code == "ANALYSIS_DATE_INVALID"]
    assert len(invalid) == 1
    assert invalid[0].acceptable is True


def test_all_uoir_ids_blank_and_no_tabs_stays_blocked(clean_workbook_with, synthetic_tool):
    def change(wb):
        wb["UOIR"]["B5"] = None
        wb["UOIR"]["B6"] = None
        wb.remove(wb[synthetic_tool.CLEAN_TAB_601])
        wb.remove(wb[synthetic_tool.CLEAN_TAB_602])

    report = _build(clean_workbook_with(change))
    codes = [i.code for i in report.issues]
    assert "ANALYSIS_SHEET_NONE" in codes
    assert codes.count("UOIR_VALUE_BLANK") == 2
    none = next(i for i in report.issues if i.code == "ANALYSIS_SHEET_NONE")
    assert none.acceptable is False

    for issue in report.issues:
        if issue.acceptable:
            issue.accepted = True
    assert export_allowed(report.issues) is False
