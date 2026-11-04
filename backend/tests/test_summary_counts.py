"""Summary counts, pie percentages, work centres and recommendation groups (sections 3.8-3.9)."""
from __future__ import annotations

import pytest

from backend.config.mapping import STANDARD_STRATEGY_CODES, UNKNOWN_STRATEGY_COLOR
from backend.report.models import TaskRecord
from backend.report.summary import (
    build_recommendations,
    largest_remainder_percentages,
    summarise,
)


def record(row, code="OC", new_task="yes", trade="SYNINCS", kks="KKS-1", failure_mode=None,
           duplicate_of=None, task="Task", frequency="1M"):
    """A SYNTHETIC TaskRecord with sensible defaults."""
    return TaskRecord(
        source_row=row,
        failure_mode=failure_mode or f"Mode {row}",
        failure_effect="Effect",
        strategy_code=code,
        strategy_raw=code,
        task=task,
        frequency=frequency,
        trade=trade,
        trade_key=" ".join(trade.split()).upper(),
        kks=kks,
        new_task=new_task,
        new_task_raw={"yes": "Yes", "no": "No", "blank": "", "invalid": "TBC"}[new_task],
        is_duplicate=duplicate_of is not None,
        duplicate_of_row=duplicate_of,
    )


# --------------------------------------------------------------------------- #
# Percentages
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ([1, 1, 1], [33.4, 33.3, 33.3]),
        ([2, 1, 1, 1, 1, 1, 1, 1], [22.3, 11.1, 11.1, 11.1, 11.1, 11.1, 11.1, 11.1]),
        ([3, 1, 1, 1], [50.0, 16.7, 16.7, 16.6]),
        ([3, 2, 1, 4, 1], [27.3, 18.2, 9.1, 36.3, 9.1]),
        ([7, 1, 1, 1], [70.0, 10.0, 10.0, 10.0]),
        ([1], [100.0]),
        ([0, 0], [0.0, 0.0]),
        ([], []),
    ],
)
def test_largest_remainder_percentages(counts, expected):
    result = largest_remainder_percentages(counts)
    assert result == expected
    if sum(counts):
        assert round(sum(result), 1) == 100.0


@pytest.mark.parametrize("counts", [[1] * 7, [5, 3, 3], [13, 7, 2, 1, 1], [1, 2, 3, 4, 5, 6]])
def test_percentages_always_sum_to_exactly_one_thousand_tenths(counts):
    tenths = [round(p * 10) for p in largest_remainder_percentages(counts)]
    assert sum(tenths) == 1000


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
def test_empty_summary():
    summary = summarise([])
    assert (summary.failure_mode_count, summary.maintenance_task_count, summary.task_executed_count) == (0, 0, 0)
    assert [r.code for r in summary.strategy_rows] == list(STANDARD_STRATEGY_CODES)
    assert all(r.total == 0 and r.standard for r in summary.strategy_rows)
    assert (summary.pie, summary.pie_total, summary.work_centre_rows) == ([], 0, [])


def test_counts_exclude_only_exact_duplicates():
    tasks = [
        record(3, "OC", "no", failure_mode="Same mode"),
        record(4, "SR", "yes", failure_mode="Same mode"),          # same mode, other strategy: counted
        record(5, "NSM", "blank"),
        record(6, "SR", "yes", failure_mode="Same mode", duplicate_of=4),
    ]
    summary = summarise(tasks)
    assert summary.failure_mode_count == 3
    assert summary.maintenance_task_count == 2
    assert summary.task_executed_count == 1
    assert summary.duplicate_rows == [6]
    assert {r.code: (r.existing, r.new, r.total) for r in summary.strategy_rows}["SR"] == (0, 1, 1)


def test_strategy_rows_order_extras_and_not_specified():
    tasks = [
        record(3, "R-PRO", "yes"),
        record(4, "OC", "no"),
        record(5, "ZZZ", "yes"),
        record(6, "", "no"),
        record(7, "R-PRO", "no"),
        record(8, "", "blank"),
    ]
    rows = summarise(tasks).strategy_rows
    assert [r.code for r in rows] == [*STANDARD_STRATEGY_CODES, "R-PRO", "ZZZ", ""]
    table = {r.code: (r.existing, r.new, r.total, r.standard, r.label) for r in rows}
    assert table["R-PRO"] == (1, 1, 2, False, "R-PRO - Redesign Procedure")
    assert table["ZZZ"] == (0, 1, 1, False, "ZZZ")
    assert table[""] == (1, 0, 2, False, "Not specified")
    assert table["N/A"][4] == "Not Analysed"
    colors = {r.code: r.color for r in rows}
    assert colors["ZZZ"] == UNKNOWN_STRATEGY_COLOR
    assert colors["OC"] == "#2a78d6"


def test_not_specified_row_absent_when_no_blank_code():
    assert "" not in [r.code for r in summarise([record(3, "OC")]).strategy_rows]


def test_not_specified_ignores_blank_codes_on_duplicates():
    tasks = [record(3, "", "yes"), record(4, "", "yes", duplicate_of=3), record(5, "OC")]
    rows = summarise(tasks).strategy_rows
    assert rows[-1].code == "" and rows[-1].total == 1


def test_pie_uses_strategy_row_order_and_skips_zero_totals():
    tasks = [record(3, "R-SPARE", "no"), record(4, "OC", "yes"), record(5, "OC", "no"), record(6, "XYZ", "blank")]
    summary = summarise(tasks)
    assert [(s.code, s.count, s.percent) for s in summary.pie] == [
        ("OC", 2, 50.0), ("R-SPARE", 1, 25.0), ("XYZ", 1, 25.0),
    ]
    assert summary.pie_total == 4


def test_work_centres_sorted_by_total_then_first_appearance():
    tasks = [
        record(3, trade="SYNOPER", new_task="yes"),
        record(4, trade="SYNELEC", new_task="no"),
        record(5, trade="synelec", new_task="yes"),
        record(6, trade="SYNINCS", new_task="no"),
        record(7, trade="SYNINCS", new_task="blank"),     # left out
        record(8, trade="", new_task="no"),
        record(9, trade="SYNCASH", new_task="invalid"),   # left out entirely
        record(10, trade="SYNOPER", new_task="no", duplicate_of=4),
    ]
    rows = summarise(tasks).work_centre_rows
    assert [(w.work_centre, w.total, w.executed, w.pending) for w in rows] == [
        ("SYNELEC", 2, 1, 1),
        ("SYNOPER", 1, 0, 1),
        ("SYNINCS", 1, 1, 0),
        ("Trade not specified", 1, 1, 0),
    ]


def test_work_centre_label_is_first_seen_spelling():
    rows = summarise([record(3, trade="synincs", new_task="no"), record(4, trade="SYNINCS")]).work_centre_rows
    assert [(w.work_centre, w.total) for w in rows] == [("synincs", 2)]


def test_nsm_rows_with_yes_or_no_still_count_in_work_centres():
    rows = summarise([record(3, "NSM", "no", trade="SYNOPER")]).work_centre_rows
    assert [(w.work_centre, w.executed) for w in rows] == [("SYNOPER", 1)]


def test_not_counted_rows():
    tasks = [
        record(3, "OC", "blank", trade="SYNINCS"),
        record(4, "NSM", "blank"),                         # expected: not listed
        record(5, "NSM", "invalid"),                       # NSM: not listed
        record(6, "SD", "invalid", trade="SYNELEC"),
        record(7, "OC", "blank", duplicate_of=3),          # duplicates are never counted
        record(8, "", "blank", trade=""),
    ]
    rows = summarise(tasks).not_counted
    assert [(n.source_row, n.reason, n.strategy, n.trade) for n in rows] == [
        (3, "New Task blank", "OC", "SYNINCS"),
        (6, "New Task is not Yes or No", "SD", "SYNELEC"),
        (8, "New Task blank", "", ""),
    ]


# --------------------------------------------------------------------------- #
# Recommendations
# --------------------------------------------------------------------------- #
def test_recommendation_groups_by_kks_in_first_appearance_order():
    tasks = [
        record(3, kks="KKS-B", new_task="yes"),
        record(4, kks="KKS-A", new_task="no"),
        record(5, kks="kks-b ", new_task="blank"),
        record(6, kks="KKS-A", duplicate_of=4),
        record(7, kks="KKS-B", new_task="no"),
    ]
    groups = build_recommendations(tasks, ["Pump A", "Pump B"])
    assert [(g.heading, g.equipment, g.kks, [r.source_row for r in g.rows]) for g in groups] == [
        ("Pump A / Pump B, KKS-B", "Pump A / Pump B", "KKS-B", [3, 5, 7]),
        ("Pump A / Pump B, KKS-A", "Pump A / Pump B", "KKS-A", [4]),
    ]
    first = groups[0].rows[0]
    assert (first.failure_mode, first.task, first.frequency, first.new_task) == ("Mode 3", "Task", "1M", "yes")


def test_recommendation_heading_without_equipment():
    groups = build_recommendations([record(3, kks="KKS-1")], [])
    assert (groups[0].equipment, groups[0].heading) == ("", "KKS-1")
