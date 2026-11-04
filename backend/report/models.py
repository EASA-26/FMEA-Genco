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

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["error", "warning", "info"]
NewTaskValue = Literal["yes", "no", "blank", "invalid"]


class Issue(BaseModel):
    """A validation finding. `error` blocks preview and export."""

    severity: Severity
    code: str                        # stable machine code, e.g. "REQUIRED_VALUE_BLANK"
    message: str                     # plain-language text for engineers
    sheet: str | None = None
    row: int | None = None           # Excel row number
    column: str | None = None        # header text as in the workbook
    cell: str | None = None          # e.g. "N8"
    uoir_id: str | None = None


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

    equipment: str                   # UOIR equipment, several joined with " / "
    kks: str
    heading: str                     # "<equipment>, <kks>"
    rows: list[RecommendationRow]


class UoirSection(BaseModel):
    uoir_id: str
    title: str
    equipment: list[str]
    sheet_name: str | None = None
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
    uoirs: list[UoirSection] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    can_export: bool                 # False when any issue has severity "error"
    pdf_filename: str                # FMEA_Report_<Station>_<YYYY-MM-DD>.pdf
    generated_at: datetime
