"""Expected results for the SYNTHETIC sample-like workbook.

The sample-like workbook (tools/make_synthetic_workbook.py, ``sample`` variant)
has the layout and quirks of a full engineer workbook - trailing spaces in
headers and labels, numeric staff numbers and UOIR IDs, pre-numbered empty team
rows, tab names cut to 31 characters (one from the middle of its title),
non-breaking-space blanks, notes beside and below a table, a failure mode over
several task rows, a large ignored Notifications sheet - with entirely invented
content. Like a correctly filled-in workbook it produces no issues at all.
"""
from __future__ import annotations

import time
from datetime import date

import pytest

from backend.report.builder import build_report

TAB_712 = "UOIR ID 712 - Turbine ESD (Emer"
TAB_705 = "UOIR ID 705 - Deaerator Level T"
TAB_748 = "UOIR ID 748 - SYNTHETIC Condens"
EQUIPMENT_712 = "SYNTHETIC Lube Oil Pressure Switch Rack"


@pytest.fixture(scope="module")
def report(sample_workbook_bytes):
    return build_report(sample_workbook_bytes, "sample.xlsx")


def _uoir(report, uoir_id):
    return next(s for s in report.analyses if s.uoir_ids == [uoir_id])


def _strategy_table(summary):
    return {row.code: (row.existing, row.new, row.total) for row in summary.strategy_rows}


def _work_centres(summary):
    return [(w.work_centre, w.total, w.executed, w.pending) for w in summary.work_centre_rows]


def test_generator_matches_the_names_asserted_here(synthetic_tool):
    assert (synthetic_tool.SAMPLE_TAB_712, synthetic_tool.SAMPLE_TAB_705, synthetic_tool.SAMPLE_TAB_748) == (
        TAB_712, TAB_705, TAB_748)
    assert all(len(name) == 31 for name in (TAB_712, TAB_705, TAB_748)), "cut to Excel's tab-name limit"
    # The 705 tab name carries a piece from the middle of its title, not its start.
    assert not synthetic_tool.SAMPLE_TITLE_705.startswith("Deaerator")


def test_build_time_is_well_under_three_seconds(sample_workbook_bytes):
    started = time.perf_counter()
    build_report(sample_workbook_bytes, "sample.xlsx")
    elapsed = time.perf_counter() - started
    assert elapsed < 3.0, f"build_report took {elapsed:.2f} s"


def test_report_header_values(report):
    assert report.source_filename == "sample.xlsx"
    assert report.station == "SYNTHETIC Station S9"
    assert report.analysis_date == date(2025, 10, 6)
    assert report.analysis_date_text == "6 October 2025"
    assert report.can_export is True
    assert report.pdf_filename == "FMEA_Report_SYNTHETIC_Station_S9_2025-10-06.pdf"


def test_no_issues(report):
    # B3 (6 October 2025) is earlier than the fault dates; Date of Analysis is taken as written
    # and never compared with them. Notifications and Sheet3 are ignored without a notice.
    assert report.issues == []


def test_team_members(report):
    assert len(report.team) == 7
    assert [m.source_row for m in report.team] == list(range(6, 13))
    # Staff numbers are numeric cells in Excel (one stored as a float); they come through as
    # 8-digit text with no ".0".
    assert [m.staff_no for m in report.team] == [str(70001001 + n) for n in range(7)]
    assert all(len(m.staff_no) == 8 and m.staff_no.isdigit() for m in report.team)
    # Rows 13-14 only carry a pre-filled No (8, 9) and are not members.
    assert [m.no for m in report.team] == [str(n) for n in range(1, 8)]
    assert all(m.name and m.staff_no and m.section for m in report.team)
    assert report.team[0].section == "Mechanical"


def test_failure_details(report):
    assert [(d.uoir_id, d.source_row) for d in report.failure_details] == [("712", 5), ("705", 6), ("748", 7)]
    assert report.failure_details[0].equipment == EQUIPMENT_712          # trailing space trimmed
    assert report.failure_details[0].corrective_action.count("\n") == 2   # three lines kept
    assert report.failure_details[1].preventive_action == "Monthly comparison with the gauge glass (SYNTHETIC)."
    assert report.failure_details[2].faulty_date == date(2026, 4, 27)
    assert report.failure_details[2].uoir_date_text == "8 May 2026"
    assert report.uoir_ids == ["712", "705", "748"]                       # workbook order, not sorted
    assert [s.uoir_ids for s in report.analyses] == [["712"], ["705"], ["748"]]


def test_uoir_712(report):
    section = _uoir(report, "712")
    table = section.analysis
    assert section.sheet_name == TAB_712
    assert section.equipment == [EQUIPMENT_712]
    assert table.header_row == 2
    assert len(table.columns) == 22
    assert table.columns[19] == "Review task"
    assert [r.source_row for r in table.rows] == list(range(3, 15))
    assert table.merged == []
    # One failure mode over three task rows, the repeats with a blank No.
    assert [r.cells[0] for r in table.rows] == ["1", "2", "3", "4", "5", "", "", "6", "7", "8", "9", "10"]
    assert {r.cells[1] for r in table.rows[4:7]} == {"No spare switch in store"}
    assert table.rows[0].cells[20] == "900000000101"

    summary = section.summary
    assert (summary.failure_mode_count, summary.maintenance_task_count, summary.task_executed_count) == (12, 12, 6)
    assert _strategy_table(summary) == {
        "OC": (2, 3, 5), "SR": (0, 0, 0), "SD": (2, 0, 2), "FF": (0, 1, 1), "NSM": (0, 0, 0),
        "R-SPARE": (2, 1, 3), "N/A": (0, 0, 0), "R-HARDWARE": (0, 1, 1),
    }
    assert [row.code for row in summary.strategy_rows] == [
        "OC", "SR", "SD", "FF", "NSM", "R-SPARE", "N/A", "R-HARDWARE",
    ]
    assert summary.pie_total == 12
    assert [(s.code, s.count, s.percent) for s in summary.pie] == [
        ("OC", 5, 41.7), ("SD", 2, 16.7), ("FF", 1, 8.3), ("R-SPARE", 3, 25.0), ("R-HARDWARE", 1, 8.3),
    ]
    assert round(sum(s.percent for s in summary.pie), 1) == 100.0
    assert _work_centres(summary) == [
        ("SYNELEC", 4, 2, 2), ("SYNINCS", 3, 1, 2), ("SYNOPER", 3, 1, 2), ("SYNMECH", 2, 2, 0),
    ]
    assert summary.not_counted == []
    assert summary.duplicate_rows == []

    tasks = {t.source_row: t for t in section.tasks}
    assert (tasks[6].new_task_raw, tasks[6].new_task) == ("Yes", "yes")     # "Yes " in the cell
    assert (tasks[13].new_task_raw, tasks[13].new_task) == ("NO", "no")
    assert (tasks[6].strategy_code, tasks[6].strategy_raw) == ("R-HARDWARE", "R-hardware")

    groups = section.recommendations
    assert [g.heading for g in groups] == [
        f"{EQUIPMENT_712}, SYN10/AB020-120",
        f"{EQUIPMENT_712}, SYN11/AC300-390 XS01-02",
    ]
    assert len(groups[0].rows) == 11
    assert [r.source_row for r in groups[1].rows] == [4]
    assert [r.task for r in groups[0].rows[3:6]] == [
        "Keep two spare switches in store", "Keep one spare switch element in store",
        "Add the switch to the critical spares list",
    ]
    assert [(n.cell, n.text) for n in section.notes] == [
        ("B18", "Root Cause (SYNTHETIC) - lube oil pressure switch diaphragm fatigue"),
    ]


def test_uoir_705(report):
    section = _uoir(report, "705")
    table = section.analysis
    assert section.sheet_name == TAB_705
    assert [r.source_row for r in table.rows] == list(range(3, 10))
    assert table.columns[0] == "No."
    assert all(row.cells[0] == "" for row in table.rows)   # non-breaking spaces read as blank
    assert all(row.cells[10:13] == ["", "", ""] for row in table.rows)

    summary = section.summary
    assert (summary.failure_mode_count, summary.maintenance_task_count, summary.task_executed_count) == (7, 6, 2)
    strategies = _strategy_table(summary)
    assert strategies["OC"] == (2, 1, 3)
    assert strategies["SR"] == (0, 1, 1)
    assert strategies["FF"] == (0, 1, 1)
    assert strategies["NSM"] == (0, 0, 1)
    assert strategies["R-SOFTWARE"] == (0, 1, 1)
    assert summary.pie_total == 7
    assert [s.percent for s in summary.pie] == [42.8, 14.3, 14.3, 14.3, 14.3]
    software = next(t for t in section.tasks if t.strategy_code == "R-SOFTWARE")
    assert software.strategy_raw == "R-software"   # cell holds "\xa0R-software"
    nsm = next(t for t in section.tasks if t.strategy_code == "NSM")
    assert (nsm.new_task_raw, nsm.new_task, nsm.frequency) == ("", "blank", "")   # non-breaking spaces

    # SYNOPER has only the NSM row (New Task blank), so it is not listed.
    assert _work_centres(summary) == [("SYNINCS", 5, 2, 3), ("SYNMECH", 1, 0, 1)]
    assert summary.not_counted == []
    assert section.notes == []
    assert [(g.heading, len(g.rows)) for g in section.recommendations] == [
        ("SYNTHETIC Deaerator Level Transmitter, SYN30/CP101-102", 7),
    ]


def test_uoir_748(report):
    section = _uoir(report, "748")
    assert section.sheet_name == TAB_748
    assert [r.source_row for r in section.analysis.rows] == list(range(3, 12))

    summary = section.summary
    assert (summary.failure_mode_count, summary.maintenance_task_count, summary.task_executed_count) == (9, 9, 4)
    strategies = _strategy_table(summary)
    assert strategies["OC"] == (3, 1, 4)
    assert strategies["SR"] == (0, 1, 1)
    assert strategies["SD"] == (1, 0, 1)
    assert strategies["FF"] == (0, 1, 1)
    assert strategies["NSM"] == (0, 0, 0)
    assert strategies["R-SPARE"] == (0, 1, 1)
    assert strategies["R-PRO"] == (0, 1, 1)
    assert summary.pie_total == 9
    assert [(s.code, s.percent) for s in summary.pie] == [
        ("OC", 44.5), ("SR", 11.1), ("SD", 11.1), ("FF", 11.1), ("R-SPARE", 11.1), ("R-PRO", 11.1),
    ]
    assert _work_centres(summary) == [("SYNINCS", 5, 3, 2), ("SYNBOIL", 2, 1, 1), ("SYNOPER", 2, 0, 2)]
    assert [(n.cell, n.text) for n in section.notes] == [
        ("C1", "RCA (SYNTHETIC) - recirculation valve hunting at low load. Actuator linkage worn"),
    ]
    assert [(g.heading, len(g.rows)) for g in section.recommendations] == [
        ("SYNTHETIC Condensate Recirculation Valve, SYN40AA310/320", 9),
    ]


def test_report_serialises_to_json(report):
    payload = report.model_dump_json()
    assert '"station":"SYNTHETIC Station S9"' in payload


def test_generator_cli_writes_the_sample_variant(synthetic_tool, tmp_path, capsys):
    target = tmp_path / "SYNTHETIC_sample.xlsx"
    assert synthetic_tool.main(["--variant", "sample", str(target)]) == 0
    assert build_report(target.read_bytes(), target.name).issues == []
    assert "SYNTHETIC sample workbook" in capsys.readouterr().out
