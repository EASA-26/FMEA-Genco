"""Turn an uploaded FMEA workbook into a `Report`.

`build_report` only raises when the file cannot be opened at all
(`WorkbookOpenError`). Every problem with the content becomes an `Issue` with
a plain-language message and the exact sheet/row/cell, so engineers can fix
the workbook; any issue with severity "error" blocks export.

Reading order: Team Member -> UOIR list -> link analysis tabs -> each analysis
tab (display table, notes, task records) -> counts and recommendations.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Callable

from openpyxl.utils.cell import coordinate_from_string, column_index_from_string, get_column_letter

from backend.config.mapping import (
    ANALYSIS_COLUMNS,
    ANALYSIS_DATE_CELL,
    ANALYSIS_DATE_LABEL_CELL,
    ANALYSIS_HEADER_MARKERS,
    ANALYSIS_REQUIRED_HEADERS,
    ANALYSIS_REQUIRED_VALUES,
    ANALYSIS_ROW_NUMBER_FIELD,
    ANALYSIS_TITLE_CELL,
    HEADER_SEARCH_ROWS,
    IGNORED_SHEETS,
    NO_VALUES,
    NSM_CODE,
    REDESIGN_PREFIX,
    STATION_CELL,
    STATION_LABEL_CELL,
    STRATEGY_NAMES,
    TEAM_COLUMNS,
    TEAM_END_WHEN_BLANK,
    TEAM_SHEET,
    UOIR_COLUMNS,
    UOIR_REQUIRED_VALUES,
    UOIR_SHEET,
    YES_VALUES,
    normalise_code,
    normalise_header,
    strategy_label,
)
from backend.excel.linking import (
    AnalysisTab,
    UoirRef,
    check_title_cell,
    find_analysis_tabs,
    link_analysis_tabs,
    parse_analysis_tab_name,
    uoir_id_key,
)
from backend.excel.reader import (
    SheetGrid,
    SheetInfo,
    WorkbookOpenError,
    WorkbookSource,
    cell_ref,
    text_key,
)
from backend.report.formatting import (
    collapse_whitespace,
    format_date,
    make_pdf_filename,
    parse_date_text,
    plain_list,
    quote_list,
    shorten,
)
from backend.report.models import (
    AnalysisRow,
    AnalysisTable,
    FailureDetail,
    Issue,
    MergedRange,
    NewTaskValue,
    Note,
    Report,
    TaskRecord,
    TeamMember,
    UoirSection,
)
from backend.report.summary import build_recommendations, summarise

__all__ = ["WorkbookOpenError", "build_report"]

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# Row numbers listed in one message before the rest are summarised as "N more".
_MAX_ROWS_LISTED = 8

# An analysis row below the table's closing empty row is reported when at least
# this many of its required-value cells are filled (a stray note fills one or two).
_ANALYSIS_ROW_MIN_FILLED = 3

# Label cells on Team Member: label cell -> (expected words, name shown, value cell)
_TEAM_LABELS = (
    (STATION_LABEL_CELL, "station", "Station", STATION_CELL),
    (ANALYSIS_DATE_LABEL_CELL, "date of analysis", "Date of Analysis", ANALYSIS_DATE_CELL),
)


def build_report(data: bytes, filename: str) -> Report:
    """Read the workbook bytes and return the full report (content problems are in `issues`)."""
    with WorkbookSource(data) as source:
        return _ReportBuilder(source, filename).build()


def _row_col(coordinate: str) -> tuple[int, int]:
    letters, row = coordinate_from_string(coordinate)
    return row, column_index_from_string(letters)


def _s(count: int) -> str:
    return "" if count == 1 else "s"


@dataclass
class _Section:
    ref: UoirRef
    model: UoirSection
    title_row: int          # UOIR sheet row the section's Title was taken from


class _ReportBuilder:
    def __init__(self, source: WorkbookSource, filename: str) -> None:
        self.source = source
        self.filename = filename
        self.issues: list[Issue] = []
        self.station = ""
        self.analysis_date: date | None = None
        self.team: list[TeamMember] = []
        self.failure_details: list[FailureDetail] = []
        self.sections: dict[str, _Section] = {}

    # ------------------------------------------------------------------ #
    def build(self) -> Report:
        team_sheet, uoir_sheet, analysis_tabs = self._classify_sheets()
        if team_sheet is not None:
            self._read_team(team_sheet)
        if uoir_sheet is not None:
            self._read_uoirs(uoir_sheet)

        outcome = link_analysis_tabs([s.ref for s in self.sections.values()], analysis_tabs)
        self.issues.extend(outcome.issues)
        for key, section in self.sections.items():
            tab = outcome.tabs.get(key)
            if tab is not None:
                self._read_analysis(section, tab)

        issues = self._sorted_issues()
        return Report(
            source_filename=self.filename,
            station=self.station,
            analysis_date=self.analysis_date,
            analysis_date_text=format_date(self.analysis_date),
            team=self.team,
            failure_details=self.failure_details,
            uoirs=[s.model for s in self.sections.values()],
            issues=issues,
            can_export=not any(i.severity == "error" for i in issues),
            pdf_filename=make_pdf_filename(self.station, self.analysis_date),
            generated_at=datetime.now(),
        )

    def _add(self, severity: str, code: str, message: str, **location: object) -> None:
        self.issues.append(Issue(severity=severity, code=code, message=message, **location))

    def _add_rows_after_blank_row(
        self, sheet: str, rows: list[int], blank_row: int, what: tuple[str, str], left_out: str,
        uoir_id: str | None = None,
    ) -> None:
        """Warn that rows holding data sit below the empty row where a table stops, so they are left out.

        `what` is the (one row, several rows) wording, e.g. ("a team member", "team members").
        """
        if len(rows) == 1:
            subject, verb, pronoun = f"Row {rows[0]}", f"has {what[0]}", "it is"
        else:
            shown = [str(r) for r in rows[:_MAX_ROWS_LISTED]]
            if len(rows) > _MAX_ROWS_LISTED:
                shown.append(f"{len(rows) - _MAX_ROWS_LISTED} more")
            subject, verb, pronoun = f"Rows {plain_list(shown)}", f"have {what[1]}", "they are"
        self._add(
            "warning", "ROWS_AFTER_BLANK_ROW",
            f"{subject} of '{sheet}' {verb}, but the table ends at the empty row {blank_row}, so {pronoun} "
            f"{left_out}. Remove the empty rows in between and upload again.",
            sheet=sheet, row=rows[0], uoir_id=uoir_id,
        )

    def _sorted_issues(self) -> list[Issue]:
        order = {sheet.name: sheet.index for sheet in self.source.sheets}
        return sorted(
            self.issues,
            key=lambda i: (SEVERITY_ORDER[i.severity], order.get(i.sheet, -1), i.row or 0),
        )

    def _grid(self, sheet: SheetInfo, uoir_id: str | None = None) -> SheetGrid:
        grid = self.source.read_grid(sheet)
        for ref in grid.formula_cells_without_value:
            row, _ = _row_col(ref)
            self._add(
                "warning", "FORMULA_NO_VALUE",
                f"Cell {ref} on '{sheet.name}' has a formula with no saved result, so it reads as empty. "
                "Open the file in Excel, save it and upload again.",
                sheet=sheet.name, row=row, cell=ref, uoir_id=uoir_id,
            )
        return grid

    # ------------------------------------------------------------------ #
    # Sheets
    # ------------------------------------------------------------------ #
    def _classify_sheets(self) -> tuple[SheetInfo | None, SheetInfo | None, list[AnalysisTab]]:
        worksheets = [s for s in self.source.sheets if s.is_worksheet]

        def locate(wanted: str) -> SheetInfo | None:
            key = wanted.strip().lower()
            return next((s for s in worksheets if s.name.strip().lower() == key), None)

        team_sheet = locate(TEAM_SHEET)
        uoir_sheet = locate(UOIR_SHEET)
        for wanted, found in ((TEAM_SHEET, team_sheet), (UOIR_SHEET, uoir_sheet)):
            if found is None:
                self._add(
                    "error", "SHEET_MISSING",
                    f"The workbook has no '{wanted}' sheet. Add it (named exactly '{wanted}') and upload again.",
                )

        ignored = {name.strip().lower() for name in IGNORED_SHEETS}
        candidates: list[SheetInfo] = []
        for sheet in self.source.sheets:
            if sheet is team_sheet or sheet is uoir_sheet:
                continue
            if sheet.name.strip().lower() in ignored:
                continue
            if sheet.is_worksheet and parse_analysis_tab_name(sheet.name):
                candidates.append(sheet)
                continue
            self._add(
                "info", "SHEET_NOT_USED", f"Sheet '{sheet.name}' is not used in the report.",
                sheet=sheet.name,
            )
        return team_sheet, uoir_sheet, find_analysis_tabs(candidates)

    @staticmethod
    def _find_header_row(grid: SheetGrid, required: list[str]) -> tuple[int, dict[str, int]] | None:
        """First row (within the search limit) whose normalised headers include all `required`."""
        for row in range(1, min(HEADER_SEARCH_ROWS, grid.max_row) + 1):
            columns: dict[str, int] = {}
            for col in range(1, grid.max_col + 1):
                text = grid.text(row, col)
                if text:
                    columns.setdefault(normalise_header(text), col)
            if all(key in columns for key in required):
                return row, columns
        return None

    # ------------------------------------------------------------------ #
    # Team Member
    # ------------------------------------------------------------------ #
    def _read_team(self, sheet: SheetInfo) -> None:
        grid = self._grid(sheet)
        name = sheet.name

        for label_cell, expected, shown, value_cell in _TEAM_LABELS:
            row, col = _row_col(label_cell)
            label = grid.text(row, col)
            if expected not in text_key(label).lower():
                found = f"it says '{shorten(label)}'" if label else "it is empty"
                self._add(
                    "warning", "LABEL_UNEXPECTED",
                    f"Cell {label_cell} on '{name}' should say '{shown}', but {found}. The sheet layout may "
                    f"have changed; check that cell {value_cell} holds the {shown}.",
                    sheet=name, row=row, cell=label_cell,
                )

        row, col = _row_col(STATION_CELL)
        self.station = grid.text(row, col)
        if not self.station:
            self._add(
                "error", "STATION_BLANK",
                f"Station is empty (cell {STATION_CELL} on '{name}'). Fill it in and upload again.",
                sheet=name, row=row, cell=STATION_CELL,
            )

        row, col = _row_col(ANALYSIS_DATE_CELL)
        raw, text = grid.raw(row, col), grid.text(row, col)
        if isinstance(raw, datetime):
            self.analysis_date = raw.date()
        elif isinstance(raw, date):
            self.analysis_date = raw
        elif not text:
            self._add(
                "error", "ANALYSIS_DATE_BLANK",
                f"Date of Analysis is empty (cell {ANALYSIS_DATE_CELL} on '{name}'). Fill it in and upload again.",
                sheet=name, row=row, cell=ANALYSIS_DATE_CELL,
            )
        else:
            self.analysis_date = parse_date_text(text)
            if self.analysis_date is None:
                self._add(
                    "error", "ANALYSIS_DATE_INVALID",
                    f"Date of Analysis '{shorten(text)}' (cell {ANALYSIS_DATE_CELL} on '{name}') is not a date. "
                    "Enter a date such as 15/06/2026 and upload again.",
                    sheet=name, row=row, cell=ANALYSIS_DATE_CELL,
                )

        headers = {field: normalise_header(header) for field, header in TEAM_COLUMNS.items()}
        found = self._find_header_row(grid, [headers["name"], headers["staff_no"]])
        if found is None:
            self._add(
                "error", "TEAM_HEADER_MISSING",
                f"The team member table was not found on '{name}'. Expected a header row with "
                f"{quote_list(list(TEAM_COLUMNS.values()))} within the first {HEADER_SEARCH_ROWS} rows.",
                sheet=name,
            )
            return
        header_row, columns = found
        column_of = {field: columns.get(key) for field, key in headers.items()}
        missing = [TEAM_COLUMNS[field] for field, col in column_of.items() if col is None]
        if missing:
            self._add(
                "error", "TEAM_HEADER_MISSING",
                f"The team member table on '{name}' is missing the column{_s(len(missing))} "
                f"{quote_list(missing)} (header row {header_row}).",
                sheet=name, row=header_row,
            )

        def value(row: int, field: str) -> str:
            col = column_of.get(field)
            return grid.carried_text(row, col, header_row + 1) if col else ""

        end_columns = [column_of[f] for f in TEAM_END_WHEN_BLANK if column_of.get(f)]
        row = header_row + 1
        while row <= grid.max_row and any(grid.text(row, c) for c in end_columns):
            self.team.append(TeamMember(
                no=value(row, "no"),
                name=value(row, "name"),
                staff_no=value(row, "staff_no"),
                section=value(row, "section"),
                source_row=row,
            ))
            row += 1
        if not self.team:
            self._add(
                "warning", "TEAM_EMPTY",
                f"No team members were found on '{name}' below the header row (row {header_row}).",
                sheet=name, row=header_row,
            )

        # The list stops at the first empty row; a member typed below a gap would vanish silently.
        name_col = column_of["name"]
        other_cols = [column_of[f] for f in ("staff_no", "section") if column_of.get(f)]
        later_rows = [
            r for r in grid.rows_with_text([name_col], row + 1) if any(grid.text(r, c) for c in other_cols)
        ]
        if later_rows:
            self._add_rows_after_blank_row(
                name, later_rows, row, ("a team member", "team members"), "not in the report",
            )

    # ------------------------------------------------------------------ #
    # UOIR list
    # ------------------------------------------------------------------ #
    def _read_uoirs(self, sheet: SheetInfo) -> None:
        grid = self._grid(sheet)
        name = sheet.name
        headers = {field: normalise_header(header) for field, header in UOIR_COLUMNS.items()}
        found = self._find_header_row(grid, [headers["uoir_id"], headers["title"]])
        if found is None:
            self._add(
                "error", "UOIR_HEADER_MISSING",
                f"The UOIR table was not found on '{name}'. Expected a header row with "
                f"{quote_list(list(UOIR_COLUMNS.values()))} within the first {HEADER_SEARCH_ROWS} rows.",
                sheet=name,
            )
            return
        header_row, columns = found
        column_of = {field: columns.get(key) for field, key in headers.items()}
        missing = [UOIR_COLUMNS[field] for field, col in column_of.items() if col is None]
        if missing:
            self._add(
                "error", "UOIR_HEADER_MISSING",
                f"The UOIR table on '{name}' is missing the column{_s(len(missing))} {quote_list(missing)} "
                f"(header row {header_row}).",
                sheet=name, row=header_row,
            )

        def header_text(field: str) -> str:
            col = column_of.get(field)
            return (grid.text(header_row, col) if col else "") or UOIR_COLUMNS[field]

        first_data_row = header_row + 1

        def value(row: int, field: str) -> str:
            col = column_of.get(field)
            return grid.carried_text(row, col, first_data_row) if col else ""

        end_columns = [col for field, col in column_of.items() if field != "no" and col]
        row = header_row + 1
        while row <= grid.max_row and any(grid.text(row, c) for c in end_columns):
            uoir_id, title, equipment = value(row, "uoir_id"), value(row, "title"), value(row, "equipment")
            location_id = uoir_id or None
            for field in UOIR_REQUIRED_VALUES:
                col = column_of.get(field)
                if col and not value(row, field):
                    self._add(
                        "error", "UOIR_VALUE_BLANK",
                        f"{header_text(field)} is empty on row {row} of '{name}'. Fill it in and upload again.",
                        sheet=name, row=row, column=header_text(field), cell=cell_ref(row, col),
                        uoir_id=location_id,
                    )
            faulty_date, faulty_text = self._uoir_date(
                grid, name, row, first_data_row, column_of, "faulty_date", header_text, location_id
            )
            uoir_date, uoir_text = self._uoir_date(
                grid, name, row, first_data_row, column_of, "uoir_date", header_text, location_id
            )
            if column_of.get("equipment") and not equipment:
                self._add(
                    "warning", "UOIR_EQUIPMENT_BLANK",
                    f"{header_text('equipment')} is empty on row {row} of '{name}'.",
                    sheet=name, row=row, column=header_text("equipment"),
                    cell=cell_ref(row, column_of["equipment"]), uoir_id=location_id,
                )
            self.failure_details.append(FailureDetail(
                no=value(row, "no"),
                uoir_id=uoir_id,
                title=title,
                faulty_date=faulty_date,
                faulty_date_text=faulty_text,
                uoir_date=uoir_date,
                uoir_date_text=uoir_text,
                corrective_action=value(row, "corrective_action"),
                preventive_action=value(row, "preventive_action"),
                equipment=equipment,
                source_row=row,
            ))
            if uoir_id:
                self._add_to_section(name, row, column_of, header_text, uoir_id, title, equipment)
            row += 1

        if not self.failure_details:
            self._add(
                "error", "UOIR_NONE",
                f"No UOIRs were found on '{name}' below the header row (row {header_row}).",
                sheet=name, row=header_row,
            )

        # The list stops at the first empty row; a UOIR typed below a gap would vanish silently
        # (and its analysis tab would only be reported as "not in the UOIR list").
        id_col, title_col = column_of.get("uoir_id"), column_of.get("title")
        if id_col and title_col:
            for later in grid.rows_with_text([id_col], row + 1):
                later_id = grid.text(later, id_col)
                if grid.text(later, title_col):
                    self._add_rows_after_blank_row(
                        name, [later], row, (f"UOIR ID {later_id}", ""), "not in the report", uoir_id=later_id,
                    )

    def _uoir_date(
        self, grid: SheetGrid, sheet_name: str, row: int, first_data_row: int, column_of: dict[str, int | None],
        field: str, header_text: Callable[[str], str], uoir_id: str | None,
    ) -> tuple[date | None, str]:
        """An Excel date, or a text date we can read; anything else is kept as text with a warning."""
        col = column_of.get(field)
        if not col:
            return None, ""
        raw, text = grid.carried_raw(row, col, first_data_row), grid.carried_text(row, col, first_data_row)
        if isinstance(raw, datetime):
            return raw.date(), text
        if isinstance(raw, date):
            return raw, text
        if not text:
            return None, ""
        parsed = parse_date_text(text)
        if parsed is not None:
            return parsed, format_date(parsed)
        self._add(
            "warning", "UOIR_DATE_NOT_DATE",
            f"{header_text(field)} on row {row} of '{sheet_name}' is not a date ('{shorten(text)}'). "
            "It is shown as written.",
            sheet=sheet_name, row=row, column=header_text(field), cell=cell_ref(row, col), uoir_id=uoir_id,
        )
        return None, text

    def _add_to_section(
        self, sheet_name: str, row: int, column_of: dict[str, int | None], header_text: Callable[[str], str],
        uoir_id: str, title: str, equipment: str,
    ) -> None:
        """One section per distinct UOIR ID; later rows only add Equipment."""
        key = uoir_id_key(uoir_id)
        section = self.sections.get(key)
        if section is None:
            id_col = column_of["uoir_id"]
            ref = UoirRef(
                uoir_id=uoir_id, title=title, sheet=sheet_name, row=row,
                cell=cell_ref(row, id_col), column=header_text("uoir_id"),
            )
            section = self.sections[key] = _Section(
                ref, UoirSection(uoir_id=uoir_id, title=title, equipment=[]), title_row=row,
            )
        elif title and not section.model.title:
            # The first row's Title is empty (already an error); use the first Title given so the
            # tab linking and title checks compare against real text rather than "".
            section.model.title = title
            section.ref = replace(section.ref, title=title)
            section.title_row = row
        elif title and text_key(title) != text_key(section.model.title):
            self._add(
                "warning", "UOIR_DUPLICATE_ID_CONFLICT",
                f"UOIR ID {uoir_id} is listed again on row {row} of '{sheet_name}' with a different Title "
                f"('{shorten(title)}'). The Title from row {section.title_row} is used.",
                sheet=sheet_name, row=row, column=header_text("title"),
                cell=cell_ref(row, column_of["title"]), uoir_id=uoir_id,
            )
        if equipment and text_key(equipment) not in {text_key(e) for e in section.model.equipment}:
            section.model.equipment.append(equipment)

    # ------------------------------------------------------------------ #
    # Analysis tab
    # ------------------------------------------------------------------ #
    def _read_analysis(self, section: _Section, tab: AnalysisTab) -> None:
        sheet = tab.sheet
        name = sheet.name
        uoir_id = section.ref.uoir_id
        model = section.model
        model.sheet_name = name
        grid = self._grid(sheet, uoir_id)
        title_row, title_col = _row_col(ANALYSIS_TITLE_CELL)

        def check_title() -> None:
            title_issue = check_title_cell(grid.text(title_row, title_col), section.ref, name)
            if title_issue is not None:
                self.issues.append(title_issue)

        markers = [normalise_header(ANALYSIS_COLUMNS[field]) for field in ANALYSIS_HEADER_MARKERS]
        found = self._find_header_row(grid, markers)
        if found is None:
            check_title()
            wanted = quote_list([ANALYSIS_COLUMNS[field] for field in ANALYSIS_HEADER_MARKERS])
            self._add(
                "error", "ANALYSIS_HEADER_MISSING",
                f"The analysis table was not found on '{name}'. Expected a header row with {wanted} "
                f"within the first {HEADER_SEARCH_ROWS} rows.",
                sheet=name, uoir_id=uoir_id,
            )
            return
        header_row, _ = found

        # Table extent: first..last filled header cell, rows until the first blank row.
        header_cols = [c for c in range(1, grid.max_col + 1) if grid.text(header_row, c)]
        first_col, last_col = header_cols[0], header_cols[-1]
        row_number_key = normalise_header(ANALYSIS_COLUMNS[ANALYSIS_ROW_NUMBER_FIELD])
        row_number_col = next(
            (c for c in header_cols if normalise_header(grid.text(header_row, c)) == row_number_key), None
        )
        span = [c for c in range(first_col, last_col + 1) if c != row_number_col]
        last_row = header_row
        while last_row + 1 <= grid.max_row and any(grid.text(last_row + 1, c) for c in span):
            last_row += 1
        data_rows = range(header_row + 1, last_row + 1)

        # B1 holds the title, unless the header row is row 1 and B1 is a column header
        # (comparing "Failure Mode" with the UOIR title would be a false alarm).
        if not (header_row <= title_row <= last_row and first_col <= title_col <= last_col):
            check_title()

        # A column with a blank header is kept only when it holds data.
        columns = [
            c for c in range(first_col, last_col + 1)
            if grid.text(header_row, c) or any(grid.text(r, c) for r in data_rows)
        ]
        field_cols, headers_ok = self._map_analysis_columns(grid, name, uoir_id, header_row, columns)
        if not data_rows:
            self._add(
                "error", "ANALYSIS_NO_ROWS",
                f"No analysis rows were found on '{name}' below the header row (row {header_row}).",
                sheet=name, row=header_row, uoir_id=uoir_id,
            )

        # The table stops at the first empty row. Rows that still look like analysis rows further
        # down (several required values filled) would otherwise drop out of the counts silently.
        value_cols = [field_cols[f] for f in ANALYSIS_REQUIRED_VALUES if f in field_cols]
        later_rows = [
            r for r in grid.rows_with_text(value_cols, last_row + 2)
            if sum(1 for c in value_cols if grid.text(r, c)) >= _ANALYSIS_ROW_MIN_FILLED
        ]
        if later_rows:
            self._add_rows_after_blank_row(
                name, later_rows, last_row + 1, ("analysis values", "analysis values"),
                "not in the table or the counts", uoir_id=uoir_id,
            )

        model.analysis = self._analysis_table(grid, name, uoir_id, header_row, columns, data_rows)
        model.notes = self._notes(
            grid, header_row, last_row, first_col, last_col, field_cols.get(ANALYSIS_ROW_NUMBER_FIELD)
        )
        if not headers_ok:
            return
        model.tasks = self._task_records(grid, name, uoir_id, header_row, columns, data_rows, field_cols)
        model.summary = summarise(model.tasks)
        model.recommendations = build_recommendations(model.tasks, model.equipment)

    def _map_analysis_columns(
        self, grid: SheetGrid, name: str, uoir_id: str, header_row: int, columns: list[int],
    ) -> tuple[dict[str, int], bool]:
        """Find the mapped columns by header; report missing or repeated headers."""
        field_cols: dict[str, int] = {}
        missing: list[str] = []
        ok = True
        for field, header in ANALYSIS_COLUMNS.items():
            key = normalise_header(header)
            matches = [
                c for c in columns
                if grid.text(header_row, c) and normalise_header(grid.text(header_row, c)) == key
            ]
            if len(matches) > 1:
                ok = False
                cells = plain_list([cell_ref(header_row, c) for c in matches])
                self._add(
                    "error", "ANALYSIS_HEADER_DUPLICATE",
                    f"The column '{grid.text(header_row, matches[0])}' appears more than once in the header row "
                    f"of '{name}' (cells {cells}). Keep one and upload again.",
                    sheet=name, row=header_row, column=grid.text(header_row, matches[1]),
                    cell=cell_ref(header_row, matches[1]), uoir_id=uoir_id,
                )
            if matches:
                field_cols[field] = matches[0]
            elif field in ANALYSIS_REQUIRED_HEADERS:
                missing.append(header)
        if missing:
            ok = False
            self._add(
                "error", "ANALYSIS_HEADER_MISSING",
                f"The analysis table on '{name}' is missing the column{_s(len(missing))} {quote_list(missing)} "
                f"(header row {header_row}).",
                sheet=name, row=header_row, uoir_id=uoir_id,
            )
        return field_cols, ok

    def _analysis_table(
        self, grid: SheetGrid, name: str, uoir_id: str, header_row: int, columns: list[int], data_rows: range,
    ) -> AnalysisTable:
        """The table as displayed: cell text, merged blocks clipped to the table, covered cells empty."""
        first_data = header_row + 1
        last_data = header_row + len(data_rows)
        cells = [[grid.text(r, c) for c in columns] for r in data_rows]

        merged: list[MergedRange] = []
        carried: set[int] = set()
        for rng in grid.merged:
            top, bottom = max(rng.min_row, first_data), min(rng.max_row, last_data)
            positions = [i for i, c in enumerate(columns) if rng.min_col <= c <= rng.max_col]
            if top > bottom or not positions:
                continue
            for r in range(top, bottom + 1):
                for i in positions:
                    if (r, columns[i]) != (rng.min_row, rng.min_col):
                        cells[r - first_data][i] = ""
            if bottom > top or len(positions) > 1:
                merged.append(MergedRange(
                    first_row=top - first_data, first_col=positions[0],
                    last_row=bottom - first_data, last_col=positions[-1],
                ))
            # Only a merge that starts on a data row carries its value down its own column
            # (SheetGrid.carried_text); other covered cells count as blank.
            if bottom > top and rng.min_row >= first_data and rng.min_col in columns:
                carried.add(columns.index(rng.min_col))
        merged.sort(key=lambda m: (m.first_row, m.first_col))

        headers = [grid.text(header_row, c) for c in columns]
        if carried:
            names = [headers[i] or f"column {get_column_letter(columns[i])}" for i in sorted(carried)]
            self._add(
                "info", "MERGED_CELLS_CARRIED",
                f"Merged cells on '{name}' cover several rows in {plain_list(names)}. The merged value is used "
                "for every row it covers.",
                sheet=name, uoir_id=uoir_id,
            )
        return AnalysisTable(
            sheet=name,
            header_row=header_row,
            columns=headers,
            column_letters=[get_column_letter(c) for c in columns],
            rows=[AnalysisRow(source_row=r, cells=row_cells) for r, row_cells in zip(data_rows, cells)],
            merged=merged,
        )

    @staticmethod
    def _notes(
        grid: SheetGrid, header_row: int, last_row: int, first_col: int, last_col: int, no_col: int | None = None,
    ) -> list[Note]:
        """Text outside the table rectangle (row-major), except the title cell.

        Row numbers pre-filled in the No. column below the table (as on the Team
        Member sheet) are template numbering, not notes, so they are skipped.
        """
        title = _row_col(ANALYSIS_TITLE_CELL)
        notes: list[Note] = []
        for row, col in sorted(grid.cells):
            if (row, col) == title:
                continue
            if header_row <= row <= last_row and first_col <= col <= last_col:
                continue
            text = grid.text(row, col)
            if not text:
                continue
            if col == no_col and row > last_row and text.isdigit():
                continue
            notes.append(Note(cell=cell_ref(row, col), text=text))
        return notes

    def _task_records(
        self, grid: SheetGrid, name: str, uoir_id: str, header_row: int, columns: list[int], data_rows: range,
        field_cols: dict[str, int],
    ) -> list[TaskRecord]:
        """Normalised records from effective values, with the row-level checks."""
        first_data_row = header_row + 1

        def value(row: int, field: str) -> str:
            return grid.carried_text(row, field_cols[field], first_data_row)

        def header(field: str) -> str:
            return grid.text(header_row, field_cols[field])

        def header_label(field: str) -> str:
            # A header typed over two lines ("Failure\nEffect") reads as one line in a message.
            return collapse_whitespace(header(field))

        def location(row: int, field: str) -> dict[str, object]:
            return {
                "sheet": name, "row": row, "column": header(field),
                "cell": cell_ref(row, field_cols[field]), "uoir_id": uoir_id,
            }

        compare_cols = [c for c in columns if c != field_cols.get(ANALYSIS_ROW_NUMBER_FIELD)]
        first_row_with: dict[tuple[str, ...], int] = {}
        trade_spellings: dict[str, list[tuple[str, int]]] = {}   # trade key -> [(spelling, first row)]
        records: list[TaskRecord] = []

        for row in data_rows:
            for field in ANALYSIS_REQUIRED_VALUES:
                if not value(row, field):
                    self._add(
                        "error", "REQUIRED_VALUE_BLANK",
                        f"{header_label(field)} is empty on row {row} of '{name}'. Fill it in and upload again.",
                        **location(row, field),
                    )

            strategy_raw = value(row, "strategy")
            code = normalise_code(strategy_raw)
            if code and code not in STRATEGY_NAMES:
                if code.startswith(REDESIGN_PREFIX) and len(code) > len(REDESIGN_PREFIX):
                    self._add(
                        "info", "STRATEGY_DERIVED_NAME",
                        f"Strategy code '{shorten(strategy_raw)}' on row {row} of '{name}' is not in the standard "
                        f"list. It is shown as '{strategy_label(code)}'.",
                        **location(row, "strategy"),
                    )
                else:
                    self._add(
                        "warning", "STRATEGY_UNKNOWN",
                        f"Strategy code '{shorten(strategy_raw)}' on row {row} of '{name}' is not a known code. "
                        f"It is shown as '{code}'; check the spelling.",
                        **location(row, "strategy"),
                    )

            new_task_raw = value(row, "new_task")
            new_task = self._new_task_value(new_task_raw)
            if new_task == "invalid":
                self._add(
                    "error", "NEW_TASK_INVALID",
                    f"New Task must be Yes or No, but row {row} of '{name}' has '{shorten(new_task_raw)}'. "
                    "Correct it and upload again.",
                    **location(row, "new_task"),
                )
            elif new_task == "blank" and code != NSM_CODE:
                self._add(
                    "warning", "NEW_TASK_BLANK",
                    f"New Task is empty on row {row} of '{name}'. This row is left out of the Existing/New and "
                    "Work-Centre counts.",
                    **location(row, "new_task"),
                )
            elif code == NSM_CODE and new_task in ("yes", "no"):
                self._add(
                    "warning", "NSM_NEW_TASK_FILLED",
                    f"Row {row} of '{name}' is NSM (No Schedule Maintenance) but New Task is '{new_task_raw}'. "
                    f"NSM rows normally leave New Task empty; the row is counted as {new_task.title()}.",
                    **location(row, "new_task"),
                )

            trade = value(row, "trade")
            trade_key = text_key(trade).upper()
            if trade_key:
                spellings = trade_spellings.setdefault(trade_key, [])
                if all(text_key(trade) != s for s, _ in spellings):
                    spellings.append((text_key(trade), row))

            compare_key = tuple(text_key(grid.carried_text(row, c, first_data_row)) for c in compare_cols)
            original_row = first_row_with.setdefault(compare_key, row)
            is_duplicate = original_row != row
            if is_duplicate:
                self._add(
                    "warning", "DUPLICATE_ROW",
                    f"Row {row} is identical to row {original_row} and is counted once.",
                    sheet=name, row=row, uoir_id=uoir_id,
                )

            records.append(TaskRecord(
                source_row=row,
                failure_mode=value(row, "failure_mode"),
                failure_effect=value(row, "failure_effect"),
                strategy_code=code,
                strategy_raw=strategy_raw,
                task=value(row, "task"),
                frequency=value(row, "frequency"),
                trade=trade,
                trade_key=trade_key,
                kks=value(row, "kks"),
                new_task=new_task,
                new_task_raw=new_task_raw,
                is_duplicate=is_duplicate,
                duplicate_of_row=original_row if is_duplicate else None,
            ))

        for trade_key, spellings in trade_spellings.items():
            if len(spellings) > 1:
                second_row = spellings[1][1]
                self._add(
                    "info", "TRADE_SPELLING_MERGED",
                    f"Trade is written as {quote_list([s for s, _ in spellings])} on '{name}'. These are counted "
                    "as one work centre.",
                    **location(second_row, "trade"),
                )
        return records

    @staticmethod
    def _new_task_value(raw: str) -> NewTaskValue:
        lowered = raw.strip().lower()
        if lowered in YES_VALUES:
            return "yes"
        if lowered in NO_VALUES:
            return "no"
        if not lowered:
            return "blank"
        return "invalid"
