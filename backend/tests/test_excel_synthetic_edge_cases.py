"""The SYNTHETIC edge-case workbook: exact issues, locations and derived values."""
from __future__ import annotations

from datetime import date

import pytest

from backend.report.builder import build_report
from backend.report.models import MergedRange

TAB_501 = "UOIR ID 501 - Pump Trip due to"
TAB_502 = "UOIR ID 502 - Feed Valve Stuck"
TAB_999 = "UOIR ID 999 - Not in list"


@pytest.fixture(scope="module")
def report(edge_workbook_bytes):
    return build_report(edge_workbook_bytes, "SYNTHETIC_edge.xlsx")


@pytest.fixture(scope="module")
def clean_report(clean_workbook_bytes):
    return build_report(clean_workbook_bytes, "SYNTHETIC_clean.xlsx")


def _uoir(report, uoir_id):
    return next(s for s in report.analyses if s.uoir_ids == [uoir_id])


def test_clean_variant_has_no_issues(clean_report):
    assert clean_report.issues == []
    assert clean_report.can_export is True
    assert clean_report.uoir_ids == ["601", "602"]


def test_exact_issue_list_in_order(report):
    found = [(i.severity, i.code, i.sheet, i.row, i.column, i.cell, i.uoir_id) for i in report.issues]
    assert found == [
        ("error", "NEW_TASK_INVALID", TAB_501, 7, "New Task", "S7", "501"),
        ("error", "REQUIRED_VALUE_BLANK", TAB_501, 8, "Failure Effect", "C8", "501"),
        ("error", "REQUIRED_VALUE_BLANK", TAB_502, 7, "Trade", "H7", "502"),
        ("warning", "UOIR_DATE_NOT_DATE", "UOIR", 7, "Date of UOIR", "E7", "502"),
        ("warning", "NEW_TASK_BLANK", TAB_501, 6, "New Task", "S6", "501"),
        ("warning", "STRATEGY_UNKNOWN", TAB_501, 9, "RecommendedStrategy", "N9", "501"),
        ("warning", "STRATEGY_UNKNOWN", TAB_501, 10, "RecommendedStrategy", "N10", "501"),
        ("warning", "DUPLICATE_ROW", TAB_501, 10, None, None, "501"),
        ("warning", "NSM_NEW_TASK_FILLED", TAB_502, 5, "New Task", "J5", "502"),
        ("warning", "FORMULA_NO_VALUE", TAB_502, 6, None, "L6", "502"),
        # Spec 3.6: unchanged code and location; the tab is now included (new message below).
        ("warning", "ANALYSIS_SHEET_UNLISTED", TAB_999, None, None, None, "999"),
        # Spec 3.1 and 3.6: TAB_999 is now read, and its fragment "Not in list" is not in its B1.
        ("warning", "ANALYSIS_SHEET_TITLE_MISMATCH", TAB_999, None, None, None, "999"),
        ("info", "MERGED_CELLS_CARRIED", TAB_501, None, None, None, "501"),
        ("info", "TRADE_SPELLING_MERGED", TAB_501, 4, "Trade", "Q4", "501"),
        ("info", "STRATEGY_DERIVED_NAME", TAB_501, 11, "RecommendedStrategy", "N11", "501"),
        ("info", "SHEET_NOT_USED", "Extra Notes", None, None, None, None),
    ]
    counts = {s: sum(1 for i in report.issues if i.severity == s) for s in ("error", "warning", "info")}
    # Spec 3.6: one more warning (ANALYSIS_SHEET_TITLE_MISMATCH on TAB_999).
    assert counts == {"error": 3, "warning": 9, "info": 4}
    assert report.can_export is False


def test_issue_messages(report):
    messages = {(i.code, i.row): i.message for i in report.issues}
    assert messages[("REQUIRED_VALUE_BLANK", 8)] == (
        f"Failure Effect is empty on row 8 of '{TAB_501}'. Fill it in and upload again."
    )
    assert messages[("DUPLICATE_ROW", 10)] == "Row 10 is identical to row 9 and is counted once."
    assert messages[("NEW_TASK_INVALID", 7)].startswith("New Task must be Yes or No")
    assert "'TBC'" in messages[("NEW_TASK_INVALID", 7)]
    # Spec 3.6: the tab for an unlisted ID is now included in the report.
    assert messages[("ANALYSIS_SHEET_UNLISTED", None)] == (
        f"Tab '{TAB_999}' is for UOIR ID 999, which is not in the UOIR list. It is included in the report. "
        "Add UOIR ID 999 to the UOIR sheet if it belongs there."
    )
    # Spec 3.6: TAB_999 has no listed ID, so only B1 is compared with its fragment.
    assert messages[("ANALYSIS_SHEET_TITLE_MISMATCH", None)] == (
        f"The name of tab '{TAB_999}' does not match cell B1 ('SYNTHETIC tab for a UOIR that is not listed'). "
        "It is still used; check that it is the right tab."
    )
    assert messages[("SHEET_NOT_USED", None)] == "Sheet 'Extra Notes' is not used in the report."
    assert "Failure Mode and Failure Effect" in messages[("MERGED_CELLS_CARRIED", None)]
    assert "'R-PUMP - Redesign Pump'" in messages[("STRATEGY_DERIVED_NAME", 11)]
    assert "'SYNINCS' and 'synincs'" in messages[("TRADE_SPELLING_MERGED", 4)]


def test_team_member_sheet(report):
    assert report.station == "SYNTHETIC Station X1"
    assert report.analysis_date == date(2026, 6, 15)          # typed as the text "15/06/2026"
    assert report.analysis_date_text == "15 June 2026"
    assert report.pdf_filename == "FMEA_Report_SYNTHETIC_Station_X1_2026-06-15.pdf"
    assert [(m.no, m.staff_no, m.section, m.source_row) for m in report.team] == [
        ("1", "00001234", "Mechanical", 6),    # 1234 with number format 00000000
        ("2", "98765432", "Electrical", 7),
        ("3", "00012345", "Instrument", 8),    # typed as text
    ]


def test_failure_details(report):
    details = report.failure_details
    assert [(d.no, d.uoir_id, d.equipment, d.source_row) for d in details] == [
        ("1", "501", "Pump A", 5), ("2", "501", "Pump B", 6), ("3", "502", "Feed Valve", 7),
    ]
    first = details[0]
    assert (first.faulty_date, first.faulty_date_text) == (date(2026, 1, 10), "10 January 2026")
    assert first.corrective_action.count("\n") == 5            # six lines kept
    assert first.corrective_action.startswith("1. SYNTHETIC corrective step 1")

    third = details[2]
    assert (third.faulty_date, third.faulty_date_text) == (date(2026, 5, 3), "3 May 2026")   # text date
    assert (third.uoir_date, third.uoir_date_text) == (None, "sometime in May")
    assert third.corrective_action == "Replace actuator diaphragm.\nRecalibrate positioner."


def test_uoir_sections_and_linking(report):
    assert report.uoir_ids == ["501", "502"]
    assert [(s.uoir_ids, s.sheet_name, s.equipment) for s in report.analyses] == [
        (["501"], TAB_501, ["Pump A", "Pump B"]),
        (["502"], TAB_502, ["Feed Valve"]),
        # Spec 3.1: every analysis tab is read and becomes one section, even with no listed ID.
        (["999"], TAB_999, []),
    ]


def test_uoir_501_analysis_table(report):
    section = _uoir(report, "501")
    table = section.analysis
    assert table.sheet == TAB_501
    assert table.header_row == 2
    assert len(table.columns) == 22
    assert table.columns[7:10] == ["1", "2", "3"]
    assert table.columns[19] == "Review task"
    assert table.column_letters[0] == "A" and table.column_letters[-1] == "V"
    assert [r.source_row for r in table.rows] == list(range(3, 13))   # NBSP-only row 13 ends the table
    assert table.merged == [
        MergedRange(first_row=0, first_col=1, last_row=2, last_col=1),
        MergedRange(first_row=0, first_col=2, last_row=2, last_col=2),
    ]
    assert table.rows[0].cells[1] == "Suction strainer blocked"
    assert table.rows[1].cells[:3] == ["", "", ""]        # covered by the merge; No. is a NBSP
    assert table.rows[2].cells[:3] == ["", "", ""]
    assert table.rows[0].cells[20] == "800000000001"
    assert table.rows[9].cells[2].count("\n") == 3 and "\n\n" in table.rows[9].cells[2]
    assert [(n.cell, n.text) for n in section.notes] == [
        ("D1", "SYNTHETIC RCA note - suction strainer blocked by debris"),
        ("X4", "SYNTHETIC side note\nsecond line"),
        ("B20", "Root Cause (SYNTHETIC) - suction strainer"),
    ]


def test_uoir_501_task_records(report):
    tasks = {t.source_row: t for t in _uoir(report, "501").tasks}
    assert len(tasks) == 10
    assert [tasks[r].failure_mode for r in (3, 4, 5)] == ["Suction strainer blocked"] * 3   # carried down
    assert tasks[4].failure_effect == "Low suction pressure trips the pump"
    assert [(r, tasks[r].new_task) for r in sorted(tasks)] == [
        (3, "no"), (4, "yes"), (5, "blank"), (6, "blank"), (7, "invalid"),
        (8, "yes"), (9, "yes"), (10, "yes"), (11, "yes"), (12, "no"),
    ]
    assert (tasks[11].strategy_code, tasks[11].strategy_raw) == ("R-PUMP", "r-pump")
    assert (tasks[4].trade, tasks[4].trade_key) == ("synincs", "SYNINCS")
    assert tasks[9].trade == "SYNMECH"
    assert (tasks[10].is_duplicate, tasks[10].duplicate_of_row) == (True, 9)
    assert all(not tasks[r].is_duplicate for r in tasks if r != 10)
    assert tasks[12].task == "Modify trip logic\nAdd 2oo3 voting"


def test_uoir_501_summary(report):
    summary = _uoir(report, "501").summary
    assert (summary.failure_mode_count, summary.maintenance_task_count, summary.task_executed_count) == (9, 8, 2)
    assert [(r.code, r.existing, r.new, r.total, r.standard) for r in summary.strategy_rows] == [
        ("OC", 1, 0, 2, True), ("SR", 0, 1, 1, True), ("SD", 0, 1, 1, True), ("FF", 0, 0, 1, True),
        ("NSM", 0, 0, 1, True), ("R-SPARE", 0, 0, 0, True), ("N/A", 0, 0, 0, True),
        ("XYZ", 0, 1, 1, False), ("R-PUMP", 0, 1, 1, False), ("R-HARDWARE", 1, 0, 1, False),
    ]
    labels = {r.code: r.label for r in summary.strategy_rows}
    assert labels["XYZ"] == "XYZ"
    assert labels["R-PUMP"] == "R-PUMP - Redesign Pump"
    assert labels["N/A"] == "Not Analysed"
    assert summary.pie_total == 9
    assert [(s.code, s.count, s.percent) for s in summary.pie] == [
        ("OC", 2, 22.3), ("SR", 1, 11.1), ("SD", 1, 11.1), ("FF", 1, 11.1), ("NSM", 1, 11.1),
        ("XYZ", 1, 11.1), ("R-PUMP", 1, 11.1), ("R-HARDWARE", 1, 11.1),
    ]
    assert [(w.work_centre, w.total, w.executed, w.pending) for w in summary.work_centre_rows] == [
        ("SYNINCS", 3, 2, 1), ("SYNMECH", 2, 0, 2), ("SYNELEC", 1, 0, 1),
    ]
    assert [(n.source_row, n.reason, n.strategy, n.trade) for n in summary.not_counted] == [
        (6, "New Task blank", "OC", "SYNMECH"),
        (7, "New Task is not Yes or No", "FF", "SYNMECH"),
    ]
    assert summary.duplicate_rows == [10]


def test_uoir_501_recommendations(report):
    groups = _uoir(report, "501").recommendations
    assert [(g.heading, g.equipment, g.kks, [r.source_row for r in g.rows]) for g in groups] == [
        ("Pump A / Pump B, KKS-PUMP-A", "Pump A / Pump B", "KKS-PUMP-A", [3, 4, 5, 8, 12]),
        ("Pump A / Pump B, KKS-PUMP-B", "Pump A / Pump B", "KKS-PUMP-B", [6, 7, 9, 11]),   # "kks-pump-b" joins
    ]
    row4 = groups[0].rows[1]
    assert (row4.failure_mode, row4.task, row4.frequency, row4.new_task) == (
        "Suction strainer blocked", "Clean strainer", "6M", "yes",
    )


def test_uoir_502_blank_header_columns_and_notes(report):
    section = _uoir(report, "502")
    table = section.analysis
    assert table.header_row == 3
    # Blank header E holds data (kept); blank header K is empty (dropped).
    assert table.columns == [
        "No.", "Failure Mode", "Failure Effect", "Recommended Strategy", "", "Task", "Frequency",
        "Trade", "KKS", "New Task", "Remark",
    ]
    assert table.column_letters == ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "L"]
    assert [r.source_row for r in table.rows] == [4, 5, 6, 7]
    assert table.rows[2].cells[10] == ""          # formula without a saved value
    assert [(n.cell, n.text) for n in section.notes] == [("A2", "SYNTHETIC analysis sheet - header on row 3")]


def test_uoir_502_summary(report):
    section = _uoir(report, "502")
    summary = section.summary
    assert (summary.failure_mode_count, summary.maintenance_task_count, summary.task_executed_count) == (4, 3, 2)
    assert [(r.code, r.existing, r.new, r.total) for r in summary.strategy_rows] == [
        ("OC", 0, 1, 1), ("SR", 0, 0, 0), ("SD", 0, 0, 0), ("FF", 0, 0, 0), ("NSM", 1, 0, 1),
        ("R-SPARE", 0, 1, 1), ("N/A", 1, 0, 1),
    ]
    assert [(s.code, s.percent) for s in summary.pie] == [("OC", 25.0), ("NSM", 25.0), ("R-SPARE", 25.0), ("N/A", 25.0)]
    assert [(w.work_centre, w.total, w.executed, w.pending) for w in summary.work_centre_rows] == [
        ("SYNINCS", 1, 0, 1), ("SYNOPER", 1, 1, 0), ("SYNELEC", 1, 1, 0), ("Trade not specified", 1, 0, 1),
    ]
    assert summary.not_counted == []
    assert [(g.heading, len(g.rows)) for g in section.recommendations] == [("Feed Valve, LAB10AA101", 4)]


def test_generator_cli_writes_file(synthetic_tool, tmp_path, capsys):
    target = tmp_path / "SYNTHETIC_clean.xlsx"
    assert synthetic_tool.main(["--variant", "clean", str(target)]) == 0
    assert target.read_bytes()[:2] == b"PK"
    assert "SYNTHETIC clean workbook" in capsys.readouterr().out
