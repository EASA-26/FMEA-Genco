"""Counts for the FMEA Summary page and rows for the Recommendation section.

Everything here works on `TaskRecord`s of one analysis tab. A row that is an
exact duplicate of an earlier row is never counted; every other row counts
once, even when the same failure mode appears with several tasks.
"""
from __future__ import annotations

from backend.config.mapping import (
    NSM_CODE,
    STANDARD_STRATEGY_CODES,
    TRADE_NOT_SPECIFIED_LABEL,
    strategy_color,
    strategy_label,
)
from backend.excel.reader import text_key
from backend.report.models import (
    NotCountedRow,
    PieSlice,
    RecommendationGroup,
    RecommendationRow,
    StrategyRow,
    Summary,
    TaskRecord,
    WorkCentreRow,
)

NEW_TASK_BLANK_REASON = "New Task blank"
NEW_TASK_INVALID_REASON = "New Task is not Yes or No"


def counted_records(tasks: list[TaskRecord]) -> list[TaskRecord]:
    """Rows that count: everything except exact duplicates."""
    return [t for t in tasks if not t.is_duplicate]


def summarise(tasks: list[TaskRecord]) -> Summary:
    counted = counted_records(tasks)
    rows = strategy_rows(counted)
    pie, pie_total = pie_slices(rows)
    return Summary(
        failure_mode_count=len(counted),
        maintenance_task_count=sum(1 for t in counted if t.strategy_code != NSM_CODE),
        task_executed_count=sum(1 for t in counted if t.new_task == "no"),
        strategy_rows=rows,
        pie=pie,
        pie_total=pie_total,
        work_centre_rows=work_centre_rows(counted),
        not_counted=not_counted_rows(counted),
        duplicate_rows=[t.source_row for t in tasks if t.is_duplicate],
    )


def strategy_rows(counted: list[TaskRecord]) -> list[StrategyRow]:
    """Standard codes always (zeros included), then other codes, then "Not specified" if needed."""
    codes: list[str] = list(STANDARD_STRATEGY_CODES)
    for record in counted:
        if record.strategy_code and record.strategy_code not in codes:
            codes.append(record.strategy_code)
    if any(not record.strategy_code for record in counted):
        codes.append("")

    rows: list[StrategyRow] = []
    for code in codes:
        matching = [t for t in counted if t.strategy_code == code]
        rows.append(StrategyRow(
            code=code,
            label=strategy_label(code),
            existing=sum(1 for t in matching if t.new_task == "no"),
            new=sum(1 for t in matching if t.new_task == "yes"),
            total=len(matching),
            color=strategy_color(code),
            standard=code in STANDARD_STRATEGY_CODES,
        ))
    return rows


def largest_remainder_percentages(counts: list[int], decimals: int = 1) -> list[float]:
    """Percentages rounded so they add up to exactly 100 (largest remainder method).

    Works in whole units of 10**-decimals percent so no floating-point drift
    creeps in; ties go to the earlier slice.
    """
    total = sum(counts)
    if total <= 0:
        return [0.0 for _ in counts]
    units = 100 * 10 ** decimals
    quotas = [count * units for count in counts]
    shares = [quota // total for quota in quotas]
    remainders = [quota % total for quota in quotas]
    leftover = units - sum(shares)
    order = sorted(range(len(counts)), key=lambda i: (-remainders[i], i))
    for i in order[:leftover]:
        shares[i] += 1
    return [share / 10 ** decimals for share in shares]


def pie_slices(rows: list[StrategyRow]) -> tuple[list[PieSlice], int]:
    charted = [row for row in rows if row.total > 0]
    total = sum(row.total for row in charted)
    if total == 0:
        return [], 0
    percents = largest_remainder_percentages([row.total for row in charted])
    slices = [
        PieSlice(code=row.code, label=row.label, count=row.total, percent=percent, color=row.color)
        for row, percent in zip(charted, percents)
    ]
    return slices, total


def work_centre_rows(counted: list[TaskRecord]) -> list[WorkCentreRow]:
    """Executed (New Task = No) and pending (Yes) per trade; blank or invalid New Task is left out."""
    groups: dict[str, dict] = {}
    for record in counted:
        if record.new_task not in ("yes", "no"):
            continue
        group = groups.get(record.trade_key)
        if group is None:
            label = record.trade if record.trade_key else TRADE_NOT_SPECIFIED_LABEL
            group = groups[record.trade_key] = {
                "label": label, "executed": 0, "pending": 0, "order": len(groups),
            }
        if record.new_task == "no":
            group["executed"] += 1
        else:
            group["pending"] += 1

    ordered = sorted(groups.values(), key=lambda g: (-(g["executed"] + g["pending"]), g["order"]))
    return [
        WorkCentreRow(
            work_centre=g["label"],
            total=g["executed"] + g["pending"],
            executed=g["executed"],
            pending=g["pending"],
        )
        for g in ordered
    ]


def not_counted_rows(counted: list[TaskRecord]) -> list[NotCountedRow]:
    """Non-NSM rows whose New Task is blank or not Yes/No (NSM rows are expected to be blank)."""
    rows: list[NotCountedRow] = []
    for record in counted:
        if record.strategy_code == NSM_CODE:
            continue
        if record.new_task == "blank":
            reason = NEW_TASK_BLANK_REASON
        elif record.new_task == "invalid":
            reason = NEW_TASK_INVALID_REASON
        else:
            continue
        rows.append(NotCountedRow(
            source_row=record.source_row,
            reason=reason,
            strategy=record.strategy_code or record.strategy_raw,
            trade=record.trade,
        ))
    return rows


def build_recommendations(tasks: list[TaskRecord], equipment: list[str]) -> list[RecommendationGroup]:
    """One group per KKS (first-appearance order), rows in workbook order."""
    equipment_text = " / ".join(equipment)
    groups: dict[str, RecommendationGroup] = {}
    for record in counted_records(tasks):
        key = text_key(record.kks).upper()
        group = groups.get(key)
        if group is None:
            heading = ", ".join(part for part in (equipment_text, record.kks) if part)
            group = groups[key] = RecommendationGroup(
                equipment=equipment_text, kks=record.kks, heading=heading, rows=[],
            )
        group.rows.append(RecommendationRow(
            source_row=record.source_row,
            failure_mode=record.failure_mode,
            task=record.task,
            frequency=record.frequency,
            new_task=record.new_task,
        ))
    return list(groups.values())
