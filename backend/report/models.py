"""Report data model shared by the parser, the calculations, the API and the PDF.

The same `Report` object is sent to the browser (as JSON) and rendered to PDF,
so the review screens, the preview and the exported file always agree.

Source data (what the workbook says, for display) is kept apart from derived
data (normalised records and counts): `AnalysisTable` is never modified by the
calculations, which work on `TaskRecord`s.

Row numbers are Excel row numbers (1-based) so messages can point engineers to
the exact place in their workbook.
"""
from __future__ import annotations

import secrets
from collections.abc import Collection
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.config.mapping import ACCEPTABLE_ERROR_CODES

Severity = Literal["error", "warning", "info"]
NewTaskValue = Literal["yes", "no", "blank", "invalid"]


class Issue(BaseModel):
    """A validation finding. An `error` blocks preview and export until it is accepted."""

    severity: Severity
    code: str                        # stable machine code, e.g. "REQUIRED_VALUE_BLANK"
    message: str                     # plain-language text for engineers
    sheet: str | None = None
    row: int | None = None           # Excel row number
    column: str | None = None        # header text as in the workbook
    cell: str | None = None          # e.g. "N8"
    uoir_id: str | None = None
    id: str = ""                     # "1", "2", ... in report order (set by finalise_report)
    acceptable: bool = False         # may be accepted on Data Checks (set by finalise_report)
    accepted: bool = False           # accepted for this report; changed only through the API


class TeamMember(BaseModel):
    no: str
    name: str
    staff_no: str                    # text; leading zeros preserved
    section: str
    source_row: int


class FailureDetail(BaseModel):
    """One row of the UOIR sheet, displayed as-is in Introduction > Failure Details."""

    no: str
    uoir_id: str
    title: str
    faulty_date: date | None = None
    faulty_date_text: str            # "7 December 2025", or the raw text when not a date
    uoir_date: date | None = None
    uoir_date_text: str
    corrective_action: str           # multiline text preserved ("\n")
    preventive_action: str
    equipment: str
    source_row: int


class MergedRange(BaseModel):
    """A merged block inside an analysis table (indexes into rows/columns, 0-based, inclusive)."""

    first_row: int
    first_col: int
    last_row: int
    last_col: int


class AnalysisRow(BaseModel):
    source_row: int
    cells: list[str]                 # display text aligned with AnalysisTable.columns;
                                     # cells covered by a merge (not top-left) are ""


class AnalysisTable(BaseModel):
    """The FMEA Analysis table exactly as in the tab (source data, display only)."""

    sheet: str
    header_row: int
    columns: list[str]               # header text as in the workbook, source order
    column_letters: list[str]        # Excel letters, aligned with columns
    rows: list[AnalysisRow]
    merged: list[MergedRange] = Field(default_factory=list)


class Note(BaseModel):
    """Text found in an analysis tab outside the table (not the B1 title)."""

    cell: str
    text: str


class TaskRecord(BaseModel):
    """Derived, normalised view of one analysis row, used by the calculations."""

    source_row: int
    failure_mode: str
    failure_effect: str
    strategy_code: str               # normalised, e.g. "R-SPARE"; "" when blank
    strategy_raw: str                # as written, trimmed
    task: str
    frequency: str
    trade: str                       # as written, trimmed
    trade_key: str                   # grouping key: uppercase; "" when blank
    kks: str
    new_task: NewTaskValue
    new_task_raw: str
    is_duplicate: bool = False       # every column (except No.) identical to an earlier row
    duplicate_of_row: int | None = None


class StrategyRow(BaseModel):
    """One row of the Existing vs Revised table."""

    code: str                        # "" for Not specified
    label: str                       # "OC - On Condition" / "Not Analysed" / "Not specified"
    existing: int                    # New Task = No
    new: int                         # New Task = Yes
    total: int                       # all counted rows with this strategy (pie count)
    color: str
    standard: bool                   # one of the always-shown reference codes


class PieSlice(BaseModel):
    code: str
    label: str
    count: int
    percent: float                   # 0-100, one decimal; slices sum to 100.0
    color: str


class WorkCentreRow(BaseModel):
    work_centre: str                 # Trade as written (first occurrence) or "Trade not specified"
    total: int                       # executed + pending
    executed: int                    # New Task = No
    pending: int                     # New Task = Yes


class NotCountedRow(BaseModel):
    """A row left out of Existing/New and Work-Centre counts (shown as a note)."""

    source_row: int
    reason: str                      # e.g. "New Task blank"
    strategy: str
    trade: str


class Summary(BaseModel):
    failure_mode_count: int
    maintenance_task_count: int
    task_executed_count: int
    strategy_rows: list[StrategyRow]
    pie: list[PieSlice]
    pie_total: int
    work_centre_rows: list[WorkCentreRow]
    not_counted: list[NotCountedRow] = Field(default_factory=list)
    duplicate_rows: list[int] = Field(default_factory=list)   # Excel rows counted once


class RecommendationRow(BaseModel):
    source_row: int
    failure_mode: str
    task: str
    frequency: str
    new_task: NewTaskValue


class RecommendationGroup(BaseModel):
    """One heading + table in the Recommendation section (one per Equipment/KKS)."""

    equipment: str                   # Equipment of every UOIR the tab covers, joined with " / "
    kks: str
    heading: str                     # "<equipment>, <kks>"
    rows: list[RecommendationRow]


class AnalysisSection(BaseModel):
    """One analysis tab: its FMEA Analysis table, FMEA Summary and Recommendation groups."""

    sheet_name: str                  # tab name; unique in a workbook; the section's key in the UI
    uoir_ids: list[str]              # IDs in tab-name order (3.2), shown as in 3.2
    title: str                       # 3.3
    equipment: list[str]             # 3.4 (distinct, ordered)
    notes: list[Note] = Field(default_factory=list)
    analysis: AnalysisTable | None = None
    tasks: list[TaskRecord] = Field(default_factory=list)
    summary: Summary | None = None
    recommendations: list[RecommendationGroup] = Field(default_factory=list)


class Report(BaseModel):
    source_filename: str
    station: str
    analysis_date: date | None = None
    analysis_date_text: str          # "14 September 2026"
    team: list[TeamMember] = Field(default_factory=list)
    failure_details: list[FailureDetail] = Field(default_factory=list)
    uoir_ids: list[str] = Field(default_factory=list)              # distinct UOIR sheet IDs, in order
    analyses: list[AnalysisSection] = Field(default_factory=list)  # one per analysis tab, ordered by 3.5
    issues: list[Issue] = Field(default_factory=list)
    report_id: str = ""              # random hex token per built report (set by finalise_report)
    can_export: bool                 # export_allowed(issues): no error left unaccepted
    pdf_filename: str                # FMEA_Report_<Station>_<YYYY-MM-DD>.pdf
    generated_at: datetime


# --------------------------------------------------------------------------- #
# Accepting issues
# --------------------------------------------------------------------------- #
def open_error_count(issues: list[Issue]) -> int:
    """Errors that are not accepted."""
    return sum(1 for issue in issues if issue.severity == "error" and not issue.accepted)


def export_allowed(issues: list[Issue]) -> bool:
    """The export rule: no issue with severity "error" and accepted == False."""
    return open_error_count(issues) == 0


def _is_acceptable(issue: Issue, not_acceptable_rows: Collection[tuple[str, int]]) -> bool:
    if issue.severity == "warning":
        return True
    if issue.severity != "error" or issue.code not in ACCEPTABLE_ERROR_CODES:
        return False
    # A row whose every required value is blank is not an analysis row with a missing value.
    return not (issue.code == "REQUIRED_VALUE_BLANK" and (issue.sheet, issue.row) in not_acceptable_rows)


def finalise_report(report: Report, not_acceptable_rows: Collection[tuple[str, int]] = ()) -> Report:
    """A deep copy with a new `report_id`, issue ids "1".. in list order, `acceptable` and `can_export`.

    `not_acceptable_rows` holds the (sheet, row) of analysis rows whose every required value is
    blank; their REQUIRED_VALUE_BLANK issues cannot be accepted.
    """
    final = report.model_copy(deep=True)
    rows = set(not_acceptable_rows)
    for n, issue in enumerate(final.issues, start=1):
        issue.id = str(n)
        issue.acceptable = _is_acceptable(issue, rows)
    final.report_id = secrets.token_hex(8)
    final.can_export = export_allowed(final.issues)
    return final
