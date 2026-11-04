# FMEA Report Generator — Build Contract

This is the single source of truth for everyone building the app. Engineers
upload an FMEA workbook, review the extracted data, preview the report and export
a PDF (optionally opening it in a new Outlook email). The app is **one-time use**:
nothing is stored, and the workbook, report and PDF last only for the current page
visit (4.1). **Accuracy of extraction and counts is the top priority**; never invent,
silently drop, or double count data.

This version describes the app **as built and accepted** after the component
builds and their adversarial reviews (see the Change log at the end). Items that
were requested but not decided are listed in section 7. The user-facing guide is
`README.md`.

Shared, owner-controlled files (do **not** edit; if you need a change, report it
as a contract change request): `backend/config/mapping.py`,
`backend/report/models.py`, `backend/settings.py`, this file.

Constraints for all code:
- Python code must run on **Python 3.11** (Databricks) — no 3.12+ syntax or APIs
  (no `type X = ...`, no PEP 695 generics, no `itertools.batched`, no PEP 701
  f-strings that reuse quotes or backslashes inside braces, etc.). Local interpreter
  is 3.14 and **no 3.11 interpreter is available**: 3.11 compatibility is checked
  syntactically (`ast.parse(..., feature_version=(3, 11))` plus an f-string token
  scan), not by running the tests on 3.11.
- No Windows-only paths. Assets via `backend.settings.ASSETS_DIR`. The one Windows-only
  feature, "Email the PDF" (`backend/mail/outlook.py`, section 4.2), is switched off on every
  other platform.
- **One-time use, no database** (section 4.1). The uploaded workbook is read in memory and never
  saved; the report, preview and PDF exist only for the current page visit while signed in.
- Never write uploads or PDFs to disk; work in memory (`io.BytesIO`). Single exception: "Email the
  PDF" writes the PDF into a fresh temporary folder for Outlook to attach and deletes that folder
  straight after (section 4.2).
- Runtime dependencies are only those in `requirements.txt`. Test-only packages
  (pytest, httpx, PyMuPDF — AGPL) stay in `requirements-dev.txt`. No extra package for Outlook
  (no pywin32): it is driven through Windows PowerShell.
- Plain-language, engineer-facing messages. No stack traces or technical jargon in the UI.
- Documentation and tests use SYNTHETIC data only. No engineer workbook, and no value taken from
  one, is kept in the project (section 1).

---

## 1. Layout and ownership

```
README.md                  setup, rules and deployment guide for engineers/operators       [DOCS]
app.py                     entrypoint: uvicorn.run(**server_options(settings))             [API]
app.yaml                   Databricks Apps config (inert locally)                        [API]
requirements.txt / -dev    pinned deps                                                    [owner]
.env.example                                                                              [API]
backend/
  settings.py              env settings (+ optional .env in the project root)             [owner]
  config/mapping.py        sheet/cell/header/code mapping + strategy names/colours       [owner]
  report/models.py         pydantic Report model                                          [owner]
  excel/reader.py          open workbook from bytes, cell cleaning, merged ranges,        [PARSER]
                           formula scan, WorkbookOpenError
  excel/linking.py         analysis-tab <-> UOIR matching                                  [PARSER]
  report/formatting.py     format_date, parse_date_text, make_pdf_filename, text helpers  [PARSER]
  report/summary.py        counts per UOIR, recommendations                               [PARSER]
  report/builder.py        build_report(data, filename) -> Report                          [PARSER]
  pdf/                     render_pdf(report) -> bytes                                     [PDF]
    fonts.py styles.py text.py cover.py document.py flowtable.py tables.py charts.py
    sections.py render.py
  auth/passwords.py        scrypt hashing                                                  [API]
  auth/service.py          sign-in rate limiter, current-user dependency, cookie middleware [API]
  sessions/store.py        in-memory session store                                         [API]
  api/services.py          ReportServices (lazy builder / renderer)                        [API]
  api/upload.py            streaming in-memory multipart reader                            [API]
  api/routes_auth.py, api/routes_report.py   FastAPI routers (email endpoint in routes_report) [API]
  mail/outlook.py          "Email the PDF": availability, recipients, email text,          [API]
                           PowerShell/Outlook launcher (OutlookMailer)
  main.py                  create_app(), middleware, error handlers, frontend serving     [API]
  tests/                   conftest.py, test_excel_*.py, test_summary_*.py,
                           test_local_workbook_smoke.py (opt-in) [PARSER];
                           test_pdf_*.py [PDF] (test_pdf_fixtures.py = helpers, no tests);
                           test_api_*.py, test_mail_outlook.py [API]
tools/make_synthetic_workbook.py   SYNTHETIC edge / clean / sample-like workbook generator [PARSER]
tools/hash_password.py             prints an ADMIN_PASSWORD_HASH                           [API]
tools/check_outlook_script.py      Windows only: PowerShell's parser checks the Outlook script [API]
                                   (parsed, never run; not part of the test suite)
frontend/                  React (Vite, JavaScript) app, builds to frontend/dist           [FRONTEND]
  src/lib/email.js         browser copy of the recipient check (same rules as the server)
```

Shared test helpers live in `backend/tests/conftest.py` (PARSER: `sample_workbook_bytes`,
`synthetic_tool`, `edge_workbook_bytes`, `clean_workbook_bytes`, `clean_workbook_with`) or
in component-prefixed modules without tests (`test_pdf_fixtures.py`).

Test workbooks: every workbook the tests use is built in memory by
`tools/make_synthetic_workbook.py` (`--variant edge|clean|sample`) and holds only invented values
labelled SYNTHETIC. `sample_workbook_bytes` is the **sample-like** workbook: the sheets, layout and
quirks of a full engineer workbook with invented content (expected results in 3.11); it is always
available, so no test skips for want of a file. No engineer workbook is read by the default test
run or kept in the project.

Checking a real workbook stays possible on your own machine: the opt-in smoke test
`backend/tests/test_local_workbook_smoke.py` is skipped unless `FMEA_SAMPLE_WORKBOOK` points at an
existing file. The file is read in place (never copied or saved) and only value-free invariants are
asserted: it parses, has a station and at least one UOIR, `pdf_filename` is
`FMEA_Report_*.pdf`, `can_export` matches the error list, and `render_pdf` returns bytes starting
with `%PDF`. Never write a value from a real workbook into a test, fixture or document.
`.gitignore` excludes `*.xlsx`, `*.xlsm`, `*.xlsb`, `*.xls`, `*.csv` and `FMEA_Report_*.pdf`.

## 2. Module interfaces

```python
# backend/excel/reader.py (re-exported by backend/report/builder.py: same class)
class WorkbookOpenError(Exception):          # unreadable / not an Excel workbook
    message: str                               # plain-language, shown to the user

# backend/report/builder.py
def build_report(data: bytes, filename: str) -> Report: ...
    # Never raises for content problems: they become Report.issues.

# backend/report/formatting.py
def format_date(d: date | datetime | None) -> str      # "7 December 2025" ("" for None); datetime with a
                                                        # non-midnight time -> "7 December 2025 08:36"
def parse_date_text(text: str) -> date | None          # formats in 3.4
def make_pdf_filename(station: str, d: date | None) -> str
    # FMEA_Report_<station: whitespace->"_", only [A-Za-z0-9_-] kept, "_" runs collapsed,
    #   leading/trailing "_" trimmed; blank -> "Station">_<YYYY-MM-DD | "undated">.pdf
    # e.g. ("SYNTHETIC Station #1", 2026-06-15) -> "FMEA_Report_SYNTHETIC_Station_1_2026-06-15.pdf"

# backend/pdf/render.py
def render_pdf(report: Report) -> bytes       # renders regardless of can_export (API gates export);
                                               # one render at a time per process (lock)

# backend/auth/passwords.py
def hash_password(password: str) -> str       # "scrypt$<n>$<r>$<p>$<salt b64>$<dk b64>", n=16384 r=8 p=1, 16-byte salt, dklen=32
def verify_password(password: str, encoded: str) -> bool   # constant-time; False on malformed input
def is_password_hash(encoded: str) -> bool    # verify accepts n power of two <= 2**17, r <= 16, p <= 4

# backend/api/services.py — the object create_app(services=...) expects
class ReportServices:
    def build_report(self, data: bytes, filename: str) -> Report
    def render_pdf(self, report: Report) -> bytes
    def open_error_message(self, exc: BaseException) -> str | None   # message if exc is a WorkbookOpenError
    # builder and renderer are imported lazily (importing backend.main loads neither)

# backend/mail/outlook.py — "Email the PDF" (section 4.2)
def outlook_email_available(settings: Settings, platform: str = sys.platform) -> bool
    # True only when platform == "win32" and OUTLOOK_EMAIL != "off" and (OUTLOOK_EMAIL == "on" or
    #   (AUTH_MODE == "local" and HOST in {"127.0.0.1", "localhost", "::1"}))
def classic_outlook_ready(platform: str = sys.platform, *, class_registered=..., new_outlook_selected=...) -> bool
    # True on Windows when classic Outlook's COM class is registered and UseNewOutlook != 1 (4.2)
# OutlookMailer.available(settings) = outlook_email_available(...) and (OUTLOOK_EMAIL == "on" or classic_ready())
def parse_recipients(text: str | None) -> list[str]   # raises RecipientError (.message = plain text)
def email_subject(station: str | None, analysis_date_text: str | None) -> str
def email_intro_html(station: str | None, analysis_date_text: str | None) -> str
def safe_attachment_name(name: str | None) -> str     # Windows-safe "<name>.pdf"; idempotent
class OutlookMailer:                                  # one instance on app.state.outlook
    def __init__(self, runner: Runner | None = None, platform: str = sys.platform,
                 timeout: float = 120.0, lock: threading.Lock | None = None)
        # runner(args, env, timeout) -> RunResult(returncode, stderr); default starts PowerShell.
        # lock defaults to one process-wide lock (tried without waiting).
    def available(self, settings: Settings) -> bool
    def open_draft(self, *, recipients, subject, intro_html, pdf_bytes, attachment_name) -> None
        # blocking (call it in the threadpool); raises OutlookBusy or OutlookFailed

# backend/main.py
def create_app(settings: Settings | None = None, services: object | None = None,
               frontend_dist: Path | str | None = None,
               outlook: OutlookMailer | None = None,
               extra_local_hosts: Iterable[str] = ()) -> FastAPI ; app = create_app()
    # keyword arguments are for tests; with none it uses get_settings(), ReportServices(), frontend/dist,
    # OutlookMailer() (the real PowerShell runner). extra_local_hosts adds Host names the local-only
    # check accepts besides 127.0.0.1/localhost/::1 (tests pass TestClient's "testserver").
    # Raises ValueError at startup for an unknown AUTH_MODE, an OUTLOOK_EMAIL other than
    # auto/on/off, or an invalid SESSION_COOKIE_NAME.

# app.py
def server_options(settings: Settings, platform: str = sys.platform) -> dict   # kwargs for uvicorn.run
```

## 3. Workbook rules (PARSER)

### 3.1 Opening
- Accept `.xlsx` / `.xlsm` (checked by the API before calling the builder). Open with
  `openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True, keep_links=False)` —
  a `Notifications` sheet can hold tens of thousands of rows, so full mode is ~10x slower. Never evaluate macros,
  formulas or external links.
- read-only mode has no merged-cell info: read `<mergeCell ref=...>` from each used sheet's
  XML in the zip (map sheet name -> part via `xl/workbook.xml` + `xl/_rels/workbook.xml.rels`).
  Sheet visibility (`state="hidden"|"veryHidden"`) and chart sheets (non-worksheet parts) also
  come from the workbook part. Single-cell merge refs are ignored.
- Only the used sheets are read: `Team Member`, `UOIR` and the linked analysis tabs. Each sheet's
  real extent is read (`reset_dimensions()`), so a wrong stored `<dimension>` does not hide cells.
- Formulas: while scanning a used sheet's XML, a cell with `<f>` and no cached `<v>` -> warning
  `FORMULA_NO_VALUE` (one per cell). A `t="str"` cell with an empty `<v>` is a saved empty result
  and is not flagged. (Replaces the earlier idea of a second `data_only=False` pass.)
- Anything that stops the file opening or a used sheet being read -> `WorkbookOpenError("This file
  could not be opened as an Excel workbook. Save it as .xlsx in Excel and try again.")`.

### 3.2 Cell text (`clean_text`)
- None -> "". `\xa0` -> space. `\r\n`/`\r` -> `\n`. Collapse runs of spaces/tabs inside a line
  to one space; strip each line; drop leading/trailing empty lines. Whitespace-only -> "".
- bool -> "TRUE"/"FALSE". int -> `str(int)`; integral float -> `str(int(v))`; other float ->
  fixed-point without exponent, trailing zeros removed. If number_format is all zeros
  (e.g. "00000000") and the value is a whole number, zero-pad to that width with the sign in
  front (-5 with "0000" -> "-0005"). Non-whole numbers are never padded or rounded.
- date/datetime -> `format_date`. time -> "HH:MM".
- Comparison key (`value_key` / `text_key`): clean_text with all whitespace (incl. newlines)
  collapsed to one space. Case is kept (duplicates must be exact).

### 3.2a Merged cells in data rows (all tables)
- **Display:** the analysis table shows merges as merges; covered cells are "".
- **Derived values** (Team Member rows, UOIR rows, analysis task records, duplicate check): a
  covered cell takes the merge's top-left value **only when the merge starts on a data row (at
  or below the first data row) and the cell is in the same column as the top-left cell** (carry
  down). Every other covered cell (a header merged down into data, a value merged sideways such
  as Trade over KKS, block spill-over from another column) counts as **blank**, so the normal
  blank-value checks report it. Implemented as `SheetGrid.carried_text` / `carried_raw`.
- The end of each table is found from each cell's **own** text, not carried values. Fixed cells
  (`A2`, `A3`, `B2`, `B3`, analysis `B1`) are read from the cell itself.

### 3.3 Sheets
- Locate sheets by trimmed, case-insensitive name, among worksheets only. `Team Member` or `UOIR`
  missing -> error `SHEET_MISSING` (no sheet location). `Notifications`, `Sheet3` (`IGNORED_SHEETS`)
  are never opened/iterated (no issue).
- Worksheets whose name matches `ANALYSIS_SHEET_PATTERN` are analysis candidates. Any other sheet
  (including chart sheets) -> info `SHEET_NOT_USED` ("Sheet 'X' is not used in the report.").

### 3.4 Team Member
- Station = `B2`, Date of Analysis = `B3`. Blank -> error `STATION_BLANK` / `ANALYSIS_DATE_BLANK`.
  B3 must be an Excel date; a text date is parsed with formats `%d/%m/%Y %d-%m-%Y %d.%m.%Y
  %d-%b-%y %d-%b-%Y %d %B %Y %d %b %Y %Y-%m-%d`; unparseable -> error `ANALYSIS_DATE_INVALID`.
- `A2` should contain "station", `A3` "date of analysis" (case-insensitive, whitespace collapsed)
  else warning `LABEL_UNEXPECTED` (layout may have changed). The expected words currently live in
  `builder._TEAM_LABELS` (see 7).
- Team header row: first row within `HEADER_SEARCH_ROWS` containing headers Name and Staff No
  (normalised). Not found -> error `TEAM_HEADER_MISSING` (no members read). Found but No or
  Section missing -> error `TEAM_HEADER_MISSING` naming the columns (rows are still read).
- Rows below the header until the first row where Name, Staff No and Section are all blank
  (own cell text; No may be pre-filled). Values use the carry rule (3.2a). No members -> warning
  `TEAM_EMPTY`.
- Rows below that closing empty row with Name plus Staff No or Section -> one warning
  `ROWS_AFTER_BLANK_ROW` listing the rows (first 8, then "N more"), located at the first such row:
  "Row 9 of 'Team Member' has a team member, but the table ends at the empty row 8, so it is not
  in the report. Remove the empty rows in between and upload again."

### 3.5 UOIR sheet
- Header row: first row within `HEADER_SEARCH_ROWS` containing "UOIR ID" and "Title". Not found ->
  error `UOIR_HEADER_MISSING` (nothing read). Any other `UOIR_COLUMNS` header missing -> error
  `UOIR_HEADER_MISSING` naming the missing headers (rows are still read).
- Data rows until the first row where every mapped column except No is blank (own cell text).
  Values use the carry rule (3.2a).
- Blank UOIR ID or Title on a data row -> error `UOIR_VALUE_BLANK`. No rows -> error `UOIR_NONE`.
- UOIR ID: clean_text (numeric 501 -> "501"). Dates: Excel date/datetime -> `date` (the `*_text`
  keeps a non-midnight time: "7 December 2025 08:36"); text that parses -> that date and
  `format_date(date)`; otherwise keep the text and warning `UOIR_DATE_NOT_DATE`.
  Blank Equipment -> warning `UOIR_EQUIPMENT_BLANK`.
- `failure_details`: every data row, in sheet order, exactly as written.
- UOIR sections: one per distinct UOIR ID **with leading zeros removed** ("0501" and "501" are one
  UOIR; `UoirSection.uoir_id` keeps the first row's text), in first-appearance order. `equipment` =
  distinct non-blank Equipment values (compared by `text_key`, order kept). Title = the **first
  non-blank Title** of that ID (a blank first Title is replaced silently; the blank row is already
  a `UOIR_VALUE_BLANK` error). A later non-blank Title that differs (by `text_key`) -> warning
  `UOIR_DUPLICATE_ID_CONFLICT` naming the row the used Title came from.
- Date of Analysis is taken from `B3` as written and is **never compared with the fault dates**
  (user decision 2026-11-04; the former `DATE_OF_ANALYSIS_BEFORE_FAULT` warning is removed).
- Rows below the closing empty row with both UOIR ID and Title filled -> warning
  `ROWS_AFTER_BLANK_ROW`, **one per row**, with `uoir_id` set: "Row 8 of 'UOIR' has UOIR ID 699,
  but the table ends at the empty row 7, so it is not in the report. Remove the empty rows in
  between and upload again." (Severity for UOIR rows: see 7.)

### 3.6 Linking analysis tabs (linking.py)
- Tab name pattern (case-insensitive): `UOIR`, optional spaces, `ID`, optional spaces, optional
  `:`/`#`/`-`, the ID digits, then the remainder; title fragment = remainder with leading
  separators (`-`, `:`, spaces, tabs, non-breaking spaces) removed.
- Match IDs exactly after stripping leading zeros ("UOIR ID 60" never links to 601). For each UOIR:
  - 0 candidates -> error `ANALYSIS_SHEET_MISSING` ("No worksheet found for UOIR ID 501. Expected a tab
    named like 'UOIR ID 501 - SYNTHETIC Pump Tr…'." — suggested name cut to 31 characters), located
    on the UOIR row.
  - 1 candidate -> linked. If the UOIR Title is non-blank and the fragment does not match -> warning
    `ANALYSIS_SHEET_TITLE_MISMATCH` (still linked by ID).
  - >1 candidates: keep those whose fragment matches the title. Exactly one -> linked, and each
    other candidate -> info `SHEET_NOT_USED` ("Sheet 'X' is not used in the report. Tab 'Y' matches
    the title of UOIR ID N and was used instead."; severity: see 7). Otherwise -> error
    `ANALYSIS_SHEET_AMBIGUOUS` (list tab names).
  - Fragment match: normalise both (lowercase, `\xa0` -> space, remove characters Excel forbids in
    tab names `[]:*?/\`, collapse whitespace) and require fragment ⊆ title (substring; empty
    fragment matches).
  - `B1` of the tab non-blank and its `text_key` differs from the Title's (case-insensitive) ->
    warning `ANALYSIS_TITLE_CELL_MISMATCH`. **Skipped** when the UOIR Title is blank, and when `B1`
    lies inside the analysis table rectangle (header on row 1). Still checked when no header row
    is found.
  - Hidden tab linked -> warning `ANALYSIS_SHEET_HIDDEN` (included in the report).
- Candidate tabs whose ID is not in the UOIR sheet -> warning `ANALYSIS_SHEET_UNLISTED` ("…is not in
  the UOIR list and was left out of the report."). Unlinked tabs are not read.

### 3.7 Analysis tab
- Header row: first row within `HEADER_SEARCH_ROWS` whose normalised cells include every
  `ANALYSIS_HEADER_MARKERS`. Not found -> error `ANALYSIS_HEADER_MISSING`; `analysis` stays None,
  no notes, no tasks, summary None.
- Table extent: columns first..last non-blank header cell of that row; the No. column is the
  header whose normalised text is `no`. Data rows: from header_row+1 until the first row where
  every cell between the first and last header column, except the No. column, is blank (own text).
- Header display text = clean_text (numeric headers 1,2,3 -> "1","2","3"). A blank header inside the
  range: keep the column (header "") only if any data cell in it is non-blank, otherwise drop it.
- Map `ANALYSIS_COLUMNS` by normalised header among the kept columns. Any `ANALYSIS_REQUIRED_HEADERS`
  missing -> error `ANALYSIS_HEADER_MISSING`; a mapped header (No. included) appearing twice -> error
  `ANALYSIS_HEADER_DUPLICATE` (located at the second cell). In both cases `analysis` and `notes` are
  still built, but `tasks` and `recommendations` are empty and **`summary` is None**.
- No data rows -> error `ANALYSIS_NO_ROWS`; with good headers the summary is **all zeros** (the
  standard strategy rows, empty pie, pie_total 0).
- Rows below the closing empty row (from last data row + 2) where **at least 3** of the
  `ANALYSIS_REQUIRED_VALUES` columns are filled -> one warning `ROWS_AFTER_BLANK_ROW` listing the
  rows (first 8, then "N more"): "Rows 15 and 16 of '<tab>' have analysis values, but the table ends
  at the empty row 14, so they are not in the table or the counts. Remove the empty rows in between
  and upload again." (Heuristic: a large notes block below the table can also trigger it.)
- `AnalysisTable`: display text per cell. Merged ranges intersecting the data rows and kept columns
  are clipped to them; every covered cell (not the range's own top-left) is "". A clipped range is
  recorded in `merged` (table-relative indexes) only if it still spans more than one row or column.
  Excel does not allow overlapping merges; consumers must still tolerate overlaps (PDF and frontend
  draw overlapping ranges unmerged).
- Effective values for derived data follow 3.2a. If a merge that starts on a data row covers more
  than one data row in a table column -> info `MERGED_CELLS_CARRIED` once per tab (row None, so it
  sorts first within its sheet), naming only the columns that really carry.
- `notes`: every non-blank cell of the sheet outside the table rectangle
  (header_row..last data row × first..last header column), excluding `B1`, row-major order. Whole
  numbers in the No. column below the table (pre-filled template numbering) are not notes.
- `TaskRecord` per data row from effective values:
  - Required values (`ANALYSIS_REQUIRED_VALUES`) blank -> error `REQUIRED_VALUE_BLANK` per cell
    ("Failure Effect is empty on row 7 of 'UOIR ID 501 - Pump Trip due to'. Fill it in and upload again.").
    The message uses the header on one line (a header typed over two lines is joined); `column`
    keeps the workbook text.
  - `strategy_code = normalise_code(value)`; `strategy_raw` = clean_text. Non-blank code not in
    `STRATEGY_NAMES`: starts with "R-" -> info `STRATEGY_DERIVED_NAME` (name "Redesign X");
    otherwise warning `STRATEGY_UNKNOWN` (shown as the code itself).
  - `new_task`: lowercase trimmed value in `YES_VALUES` -> "yes"; in `NO_VALUES` -> "no"; blank ->
    "blank"; else "invalid" + error `NEW_TASK_INVALID` ("New Task must be Yes or No …").
    Blank on a non-NSM row -> warning `NEW_TASK_BLANK`. NSM with Yes/No -> warning
    `NSM_NEW_TASK_FILLED` (still counted by its value).
  - `trade_key` = value_key(trade).upper(). Different spellings (by `text_key`) merged into one key ->
    info `TRADE_SPELLING_MERGED`, once per key per tab, located at the row of the second spelling.
  - Exact duplicates: a row whose `text_key` tuple over every kept table column except No. (carry
    rule applied) equals an earlier row's -> `is_duplicate=True`, `duplicate_of_row` set, warning
    `DUPLICATE_ROW` ("Row 9 is identical to row 6 and is counted once.").
  - Row-level issues (`REQUIRED_VALUE_BLANK`, `STRATEGY_*`, `NEW_TASK_*`, `NSM_NEW_TASK_FILLED`) are
    raised for every row, duplicates included.

### 3.8 Summary (summary.py) — per UOIR, over records with `is_duplicate == False` ("counted")
- `summary` is None when the analysis tab is missing, has no header row, or has missing/duplicate
  mapped headers (3.7). Consumers must handle None.
- `failure_mode_count` = len(counted). *(A failure mode with several different tasks/strategies counts once per row; only exact duplicates are ignored.)*
- `maintenance_task_count` = counted with `strategy_code != "NSM"`.
- `task_executed_count` = counted with `new_task == "no"`.
- `strategy_rows`: `STANDARD_STRATEGY_CODES` in order (always, zeros included), then other
  non-blank codes in first-appearance order, then a `""` "Not specified" row only if any counted
  record has a blank code. existing = count "no", new = count "yes", total = all counted with that
  code. label = `strategy_label(code)`, color = `strategy_color(code)`, standard = code in STANDARD.
  Every code not in `STRATEGY_COLORS` (unknown, other `R-`, blank) gets `UNKNOWN_STRATEGY_COLOR`
  (see 7).
- `pie`: strategy_rows with total > 0 in the same order; `pie_total` = sum; percent to one decimal
  using largest-remainder (integer arithmetic; ties go to the earlier slice) so the slices sum to
  exactly 100.0 (empty list when pie_total == 0).
- `work_centre_rows`: counted records with new_task in {yes, no}, grouped by trade_key ("" ->
  `TRADE_NOT_SPECIFIED_LABEL`); label = first-seen trade text; executed = no, pending = yes,
  total = executed + pending; sorted by total desc, ties by first appearance.
- `not_counted`: counted non-NSM records with new_task "blank" (reason "New Task blank") or
  "invalid" (reason "New Task is not Yes or No"); `strategy` = code, or the raw text when the code is
  blank. NSM rows with blank New Task are expected and are not listed.
- `duplicate_rows`: source rows of duplicates.

### 3.9 Recommendations
- Per UOIR, rows = counted records in workbook order (any new_task value): failure_mode, task,
  frequency, new_task.
- Grouped by KKS (key = value_key(kks).upper()), groups in first-appearance order, rows keep
  workbook order within a group. equipment = " / ".join(UoirSection.equipment);
  heading = ", ".join of the non-empty parts of (equipment, kks): `f"{equipment}, {kks}"`, just kks
  when equipment is empty, just equipment when kks is blank (already an error), "" when both are
  empty (the PDF then shows "KKS not specified").

### 3.10 Report
- `can_export` = no issue with severity "error". `pdf_filename` = `make_pdf_filename`.
  `analysis_date_text` = format_date. `generated_at` = `datetime.now()`.
- Issues ordered by (severity error < warning < info, sheet tab index with sheet None first,
  row with None first); the sort is stable, so equal keys keep the order they were found in.

### 3.11 Expected results for the SYNTHETIC sample-like workbook (tests)
The `sample` variant of `tools/make_synthetic_workbook.py` copies the sheets, layout and quirks of
a full engineer workbook with invented content: trailing spaces in labels and headers, numeric staff
numbers and UOIR IDs, pre-numbered empty team rows, tab names cut to 31 characters, multi-line
CA/PA text, non-breaking-space blanks, notes beside and below a table, one failure mode over several
task rows, and large ignored sheets. Asserted by `backend/tests/test_excel_sample_workbook.py` and,
through the API and the PDF, by `backend/tests/test_e2e_report_consistency.py`.
- station "SYNTHETIC Station S9"; analysis_date 2025-10-06 ("6 October 2025", earlier than every
  fault date and taken as written); no issues at all (can_export True); pdf_filename
  "FMEA_Report_SYNTHETIC_Station_S9_2025-10-06.pdf".
- team: 7 members (rows 6–12); staff numbers are numeric cells (one stored as a float) and come out
  as 8-digit text with no ".0"; rows 13–14 (No 8, 9 only) excluded.
- failure_details: UOIR 712, 705, 748 (rows 5–7, workbook order, not sorted); the trailing space of
  an Equipment value is trimmed; multi-line CA keeps its line breaks.
- UOIR 712 (tab "UOIR ID 712 - Turbine ESD (Emer", header row 2, 22 columns, 12 rows 3–14, no
  merges; one failure mode over three task rows, the repeats with a blank No.): FM 12, MT 12,
  Executed 6. Strategy (existing/new/total): OC 2/3/5, SR 0/0/0, SD 2/0/2, FF 0/1/1, NSM 0/0/0,
  R-SPARE 2/1/3, N/A 0/0/0, R-HARDWARE 0/1/1 (raw "R-hardware"). Pie total 12 (41.7 / 16.7 / 8.3 /
  25.0 / 8.3). New Task "Yes " -> yes, "NO" -> no. Work centres (total, executed/pending):
  SYNELEC 4 (2/2), SYNINCS 3 (1/2), SYNOPER 3 (1/2), SYNMECH 2 (2/0). Recommendation groups:
  "SYNTHETIC Lube Oil Pressure Switch Rack, SYN10/AB020-120" (11 rows) and
  "SYNTHETIC Lube Oil Pressure Switch Rack, SYN11/AC300-390 XS01-02" (1 row, source_row 4).
  Notes: B18 (below the table, after empty rows).
- UOIR 705 (tab "UOIR ID 705 - Deaerator Level T", a piece from the middle of the title; 7 rows
  3–9, every blank typed as non-breaking spaces, so the No. column is blank): FM 7, MT 6,
  Executed 2. OC 2/1/3, SR 0/1/1, FF 0/1/1, NSM 0/0/1 (New Task blank), R-SOFTWARE 0/1/1 (raw
  "\xa0R-software"). Pie total 7 (42.8 / 14.3 / 14.3 / 14.3 / 14.3). Work centres: SYNINCS 5 (2/3),
  SYNMECH 1 (0/1) (SYNOPER has only the NSM row -> not listed). not_counted empty; no
  NEW_TASK_BLANK; no notes. One group "SYNTHETIC Deaerator Level Transmitter, SYN30/CP101-102" (7 rows).
- UOIR 748 (tab "UOIR ID 748 - SYNTHETIC Condens", 9 rows 3–11): FM 9, MT 9, Executed 4.
  OC 3/1/4, SR 0/1/1, SD 1/0/1, FF 0/1/1, NSM 0/0/0, R-SPARE 0/1/1, R-PRO 0/1/1. Pie total 9
  (44.5 / 11.1 x 5). Work centres: SYNINCS 5 (3/2), SYNBOIL 2 (1/1), SYNOPER 2 (0/2). Notes: C1 (next
  to the title, above the table). One group "SYNTHETIC Condensate Recirculation Valve,
  SYN40AA310/320" (9 rows).
- All counts above are invented for this workbook; none is taken from a real workbook.
- `Notifications` (300 filler rows) and `Sheet3` are ignored without a message.
- `build_report` on this workbook stays under 3 s (test limit).

### 3.12 Issue code catalogue

| Severity | Codes |
|---|---|
| error (blocks preview/export) | `SHEET_MISSING`, `STATION_BLANK`, `ANALYSIS_DATE_BLANK`, `ANALYSIS_DATE_INVALID`, `TEAM_HEADER_MISSING`, `UOIR_HEADER_MISSING`, `UOIR_VALUE_BLANK`, `UOIR_NONE`, `ANALYSIS_SHEET_MISSING`, `ANALYSIS_SHEET_AMBIGUOUS`, `ANALYSIS_HEADER_MISSING`, `ANALYSIS_HEADER_DUPLICATE`, `ANALYSIS_NO_ROWS`, `REQUIRED_VALUE_BLANK`, `NEW_TASK_INVALID` |
| warning | `LABEL_UNEXPECTED`, `TEAM_EMPTY`, `ROWS_AFTER_BLANK_ROW`, `UOIR_DATE_NOT_DATE`, `UOIR_EQUIPMENT_BLANK`, `UOIR_DUPLICATE_ID_CONFLICT`, `FORMULA_NO_VALUE`, `ANALYSIS_SHEET_TITLE_MISMATCH`, `ANALYSIS_TITLE_CELL_MISMATCH`, `ANALYSIS_SHEET_HIDDEN`, `ANALYSIS_SHEET_UNLISTED`, `STRATEGY_UNKNOWN`, `NEW_TASK_BLANK`, `NSM_NEW_TASK_FILLED`, `DUPLICATE_ROW` |
| info | `SHEET_NOT_USED`, `MERGED_CELLS_CARRIED`, `STRATEGY_DERIVED_NAME`, `TRADE_SPELLING_MERGED` |

A new code must be added here and to the README "Checks and messages" tables.

## 4. API (API owner) — all JSON errors are `{"detail": "<plain message>"}`

| Method & path | Auth | Behaviour |
|---|---|---|
| `GET /api/health` | no | `{"status":"ok"}` |
| `POST /api/auth/login` `{username,password}` | no | 200 `{"user":{"name":"admin"},"auth_mode":"local","features":{"outlook_email":<bool>}}` + a **new** session cookie (any previous session of that browser is destroyed); 401 "Incorrect username or password."; 429 "Too many sign-in attempts. Please wait a few minutes and try again." with `Retry-After: <seconds>` after 5 failures in 5 min per username+client **or** 50 failures in 5 min per client across all usernames; 400 "Sign-in is handled by Databricks for this app." in databricks mode |
| `POST /api/auth/logout` | yes | 204; session (and its report) destroyed, cookie cleared |
| `GET /api/auth/me` | yes | 200 `{"user":{"name":…},"auth_mode":…,"features":{"outlook_email":<bool>}}`; 401 when not signed in. In databricks mode it returns 200 (creating the session) whenever a valid identity header is present. `features.outlook_email` = `OutlookMailer.available(settings)` (4.2: allowed by the settings and classic Outlook in use); exactly `true` gives the Outlook-draft button, anything else the mail-app fallback |
| `POST /api/workbook` multipart `file` | yes | See upload rules below. 200 Report JSON (content issues are inside the report). Only a **successful** upload replaces the session's report and PDF cache; any failure keeps the previous ones. Parsing runs in the threadpool. 409 "This upload was cancelled before it finished: the workbook was closed or another upload started. Upload the workbook again to continue." when, while this upload was being read, the workbook was discarded (`DELETE /api/workbook`, sign-out) or a newer upload started (that one wins), or the browser disconnected (Cancel, page left; the previous report is then kept); nothing is stored (4.1). |
| `GET /api/report` | yes | 200 Report JSON; 404 "No workbook uploaded yet." **Not called by the frontend**: a page never restores a report from the server (4.1). Kept for tests. |
| `DELETE /api/workbook` | yes | 204, clears report and PDF cache (also 204 when there is none) and cancels an upload still being read. The frontend calls it when the workspace opens, on `pagehide` (keepalive) while the page holds a report or an upload is running, when the workspace itself fails to draw, and for "Remove" (4.1) |
| `GET /api/report/pdf?download=0\|1` | yes | 404 if no report; 409 `{"detail":"Fix the errors listed before previewing or exporting.","error_count":n}` if `can_export` false; else `application/pdf`, `Content-Disposition: inline\|attachment; filename="<ASCII-safe pdf_filename>"` plus `; filename*=UTF-8''<percent-encoded>` when the ASCII form had to change, `Cache-Control: no-store`. PDF bytes cached per session until the next upload/delete; a per-session lock makes concurrent preview + download render once. Render failure -> 500 "The PDF could not be created. Please try again or contact support." (logged, not cached). A `download` value that is not a boolean -> 422. |
| `POST /api/report/email` `{"to": "<string>"}` | yes | Opens a new classic-Outlook email with the PDF attached on the computer running the server (Display, never Send). 200 `{"status":"opened","recipients":[…normalised…],"attachment":"<file name>"}`. Errors and the order they are checked: see 4.2 |

Upload rules (`backend/api/upload.py`, streaming, in memory only — Starlette's form parser is not
used because it spools files over 1 MB to disk):
- Not `multipart/form-data`, no `file` part, or a form sent with no file chosen -> 400 "No file was
  received. Please choose an Excel workbook and try again." Only the first `file` part is used.
- File name (folders and control characters stripped) not ending in `.xlsx`/`.xlsm` -> 400 "Please
  upload an Excel workbook (.xlsx or .xlsm)." (checked as soon as the part headers arrive).
- File bytes > `MAX_UPLOAD_MB` -> 413 "The file is larger than 20 MB. Please upload a smaller
  workbook." (size from settings). A declared `Content-Length` above the limit + 1 MB overhead is
  rejected before reading; bytes are counted as they arrive either way (chunked bodies too).
- Body ends early / client disconnects -> 400 "The upload did not finish. Please try again."
- `WorkbookOpenError` -> 400 with its message. Any other builder exception -> generic 500.

Other responses (all `{"detail": …}` with a plain string):
- Any request body over **64 KB** except `/api/workbook` -> 413 "This request is too large to
  process." (early from `Content-Length`, or counted while streaming).
- Invalid JSON / wrong field types -> 422 "Some of the information sent was missing or not in the
  expected format."
- Unknown `/api` paths (any method) -> 404 "Not found."
- 401 wording: local "Please sign in to continue."; databricks "Your Databricks sign-in could not be
  confirmed. Please open the app again from Databricks."
- HTTP errors that carry only the standard reason phrase get a default plain message (400, 401,
  403, 404, 405, 413, 429).
- Unhandled exceptions -> 500 "Something went wrong on the server. Please try again or contact
  support." (logged with the path `%r`-escaped), no stack trace.
- Proxy/gateway errors (502/503/504) are not produced by the app; the frontend has its own messages.

Auth modes (`AUTH_MODE`):
- `local` — username/password against `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH`. Username compared
  after trimming (case-sensitive, constant time); the password hash is always checked, even for a
  wrong username. Username or password longer than 1024 characters is a failed attempt. Each attempt
  is counted as a failure up front (atomically) and a success clears only the username+client
  count. Limiter keys are `sha256(trimmed lowercase username)` + client host (≤ 64 chars); both
  tables are LRU-bounded (10,000 keys). While blocked, the password is not checked.
  `X-Forwarded-*` headers are never trusted in local mode (and uvicorn `proxy_headers` is off).
  An unknown/expired cookie on a protected request gets 401 and the cookie is cleared.
- `databricks` — no login page; user from `X-Forwarded-Email` (fallback
  `X-Forwarded-Preferred-Username`, `X-Forwarded-User`); the first non-empty header is used and must
  be ≤ 320 characters with no control characters, otherwise 401. A session is created on the first
  request; if the cookie's session belongs to a different user it is destroyed and a new one is
  created (never show another user's report). Each user keeps at most **5** sessions: creating a
  sixth ends that user's least recently used session (other users unaffected). `/api/auth/login`
  returns 400. The server must only be reachable through the Databricks proxy (logged at startup).

Session cookie: name `SESSION_COOKIE_NAME` (default `fmea_session`; invalid name -> ValueError at
startup), value `secrets.token_urlsafe(32)`, HttpOnly, SameSite=Lax, Path=/, Secure from
`COOKIE_SECURE` (app.yaml sets true). Cookies are written by one middleware so every response type
gets the same flags; clearing sends Max-Age=0 and an expired date. Server-side store with idle
timeout `SESSION_IDLE_MINUTES`, cap `MAX_SESSIONS` (evict least-recently used). Sessions, reports and
PDFs are in memory only; one uvicorn worker, one instance. No separate CSRF token (SameSite=Lax +
JSON bodies + same-origin fetches).

`main.py`:
- Serves `frontend/dist` when present. `/assets/*` (GET/HEAD) -> the file inside `dist/assets`, or
  JSON 404 "Not found." when missing (never index.html). Any other non-`/api` GET/HEAD -> an
  existing **top-level** file in `dist` (e.g. a favicon; not `index.html`) is served as a file;
  everything else -> `index.html` with `Cache-Control: no-cache` (also for `/index.html`). If
  `index.html` is missing -> 404 "The web interface is not available. Build the frontend (npm run
  build) and restart."
- Static paths are checked name by name **before any filesystem access**: empty parts (`//host`),
  `.`/`..`/dotfiles, backslashes, `:` (drive letters, `::$DATA`), `*?"<>|`, control characters,
  trailing dots/spaces, Windows device names and paths over 512 characters are refused; the resolved
  path must still be inside the folder. Explicit media types for frontend files (not the Windows
  registry).
- Local-only check (`LocalOnlyMiddleware`, installed only when `AUTH_MODE=local` and `HOST` is
  `127.0.0.1`, `localhost` or `::1`): a request whose Host header name (port ignored; `[::1]:port`
  accepted) is not one of those three gets 403 `{"detail":"This app only answers on this computer's
  own address. Open it at http://127.0.0.1:<PORT>."}`, and so does a POST/PUT/PATCH/DELETE whose
  Origin header is present and not `http(s)://` one of those names (`null` included). This blocks
  DNS-rebinding pages (another site's name pointed at 127.0.0.1) from signing in, uploading or
  opening Outlook. Not installed with `HOST=0.0.0.0` (shared on the network) or in databricks mode.
- Security headers on every response (errors included): `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`, `X-Frame-Options: SAMEORIGIN` (the PDF preview iframe is
  same-origin); `Cache-Control: no-store` on `/api` responses that set none.
- FastAPI docs are disabled (`docs_url`, `redoc_url`, `openapi_url` = None).
- Startup logs: warning while the built-in development password hash is used; error when
  `ADMIN_PASSWORD_HASH` is not a valid hash; info reminder in databricks mode; warning when
  `OUTLOOK_EMAIL=on` is used while the app is not local-only (Outlook would open on the server's
  computer, whoever uses the app).
- `app.state.outlook` holds the `OutlookMailer` (`create_app(outlook=...)` in tests).

`app.py`: `uvicorn.run("backend.main:app", **server_options(settings))` with `host`, `port`,
`workers=1`, `loop="asyncio:SelectorEventLoop"` on Windows only (the Proactor loop stops accepting
connections for good after an aborted connection, WinError 64) and `"auto"` elsewhere, `log_level`
from `LOG_LEVEL`, `server_header=False`, and `proxy_headers = (AUTH_MODE == "databricks")`.

Settings (`backend/settings.py`): `AUTH_MODE` (local), `ADMIN_USERNAME` (admin), `ADMIN_PASSWORD_HASH`
(built-in development hash), `SESSION_IDLE_MINUTES` (60), `MAX_SESSIONS` (200), `MAX_UPLOAD_MB` (20),
`COOKIE_SECURE` (false), `SESSION_COOKIE_NAME` (fmea_session), `HOST` (127.0.0.1; app.yaml 0.0.0.0),
port = `DATABRICKS_APP_PORT` or `PORT` or 8000, `LOG_LEVEL` (info), `OUTLOOK_EMAIL` (auto; trimmed and
lower-cased; `auto`, `on` or `off`, anything else stops the app at startup; app.yaml `off`) ->
`Settings.outlook_email`. A `.env` in the project root is loaded first; real environment variables
win. Settings are cached: restart after changing them.

### 4.1 One-time use (no database)

The app keeps nothing between visits. There is no database and no file store.
- **Server.** The upload is streamed into memory and never written to disk (4, upload rules). Each
  session holds at most one report and the PDF rendered from it, in memory only. They are dropped by
  `DELETE /api/workbook`, sign-out (the session is destroyed), the idle timeout
  (`SESSION_IDLE_MINUTES`), eviction when the store is full (`MAX_SESSIONS`), a restart, and replaced
  by the next successful upload. An upload stores its report only if nothing newer happened while it
  was being read: `SessionStore.begin_upload` numbers each upload, `clear_report` (DELETE, and the
  session ending) bumps the number, and `set_report(..., upload=n)` stores nothing when it changed; a
  browser that disconnected (Cancel, page left) is checked with `request.is_disconnected()` before
  storing. Either way the upload answers 409 and keeps nothing.
- **Browser (one page visit).** `Workspace` never restores a report with `GET /api/report`. On mount it
  awaits `discardWorkbook()` (`DELETE /api/workbook`, 404 treated as fine) and keeps its loading
  state ("Preparing your workspace…") until that finishes, so an upload cannot race the discard; it
  then starts on **Upload** with no report. If the discard fails (other than 401) it shows "The
  workspace could not be prepared" with **Try again**.
- `window` `pagehide` (refresh, closing the tab, going to another site) -> any running upload is
  aborted and, **only when this page holds a report or had an upload running** (so closing an older
  tab that holds nothing does not close the workbook of another tab), `discardWorkbookOnExit()` sends
  `fetch('/api/workbook', {method: 'DELETE', keepalive: true, credentials: 'same-origin', headers: {Accept: 'application/json'}})`
  with every error swallowed (best effort; if it never arrives, the next visit's mount discard, the
  idle timeout or sign-out clears the report). In mock mode it does nothing (the mock report lives in
  page memory).
- `pageshow` with `event.persisted` (page restored from the back/forward cache) ->
  `window.location.reload()`, so a stale report is never shown.
- If the workspace itself fails to draw, the page-level `ErrorBoundary` (`onError`) calls
  `discardWorkbookOnExit()` at once, since the screen holding the report and its `pagehide` handler
  are gone.
- Cancel during an upload aborts the request; the server sees the disconnect and keeps nothing (the
  report the page still shows, if any, stays).
- Moving between the app's own steps (Upload, Data Checks, review sections, Preview, Export) is
  client-side and keeps the report. Sign-out calls `POST /api/auth/logout`, which destroys the session
  and its report.
- The session cookie belongs to the browser, not the tab: opening the app in another tab runs the
  mount discard and so closes the workbook of the first tab.
- A **404** from preview (prepare-PDF), download or email means the server no longer holds the
  report: the app goes back to Upload with no report and an info notice ("Workbook closed"):
  "This workbook is no longer open. It is closed when you sign out, refresh or leave the page, or
  open the app in another tab. Upload it again to continue." (`WORKBOOK_CLOSED_MESSAGE` in
  `src/api/client.js`). Starting a new upload clears the notice.

### 4.2 Email the PDF (Outlook draft, or mail-app fallback)

The app never sends email. Two ways, chosen by `features.outlook_email`:

- **Outlook draft** (`outlook_email` true, button "Open in Outlook"): the server asks the classic
  Outlook desktop app, on the computer running the server, to show a **new email** (Display, never
  Send) with To, Subject, a short introduction and the PDF attached; the user checks it and presses
  Send in Outlook. Implemented in `backend/mail/outlook.py` with PowerShell COM automation
  (`New-Object -ComObject Outlook.Application`); no Python or npm package was added.
- **Mail-app fallback** (`outlook_email` false, button "Download PDF & open email"): entirely in the
  browser (`src/lib/email.js` `mailtoLink`). From the click it opens
  `mailto:<recipients joined with ",">?subject=…&body=…` (same subject as `email_subject`, plain-text
  version of `email_intro_html`; "@" kept, everything else percent-encoded) and then downloads the PDF
  as the Download button does; the user attaches it. Works with any default mail app, including the
  new Outlook for Windows, which cannot be automated.

Availability of the draft (`OutlookMailer.available`, reported as `features.outlook_email` by
`/api/auth/me` and `/api/auth/login`, checked on every request):
`outlook_email_available(settings)` — `sys.platform == "win32"`, `OUTLOOK_EMAIL` not `off`, and
either `OUTLOOK_EMAIL=on` or (`auto`, the default) `AUTH_MODE=local` with `HOST` one of
`127.0.0.1`, `localhost`, `::1` (the browser and Outlook are on the same PC) — **and**, unless
`OUTLOOK_EMAIL=on`, `classic_outlook_ready()`: the `Outlook.Application\CLSID` class is registered
(HKCR) and `UseNewOutlook` under `HKCU\Software\Microsoft\Office\16.0\Outlook\Preferences` is not 1.
With the "New Outlook" toggle on, classic Outlook started for automation hands over to the new
Outlook and exits; Windows only reports that after ~30 s (DCOM event 10010,
CO_E_SERVER_EXEC_FAILURE 0x80080005), so the app checks first. Registry errors count as "not
ready". app.yaml sets `off`.

`POST /api/report/email`, body `{"to": "<string>"}` (`to` defaults to ""; empty means "choose
recipients in Outlook"). A body over 64 KB gets 413 from the middleware first; after that the
checks run in this order:

| Status | When | Body |
|---|---|---|
| 401 | not signed in | usual 401 message |
| 422 | malformed JSON, or `to` not a string | usual 422 message |
| 501 | draft not available (rule above) | `{"detail":"Outlook can only open the email here when the app runs on your own computer with the classic Outlook app. Download the PDF and attach it to an email instead."}` |
| 400 | bad recipient list (rules below) | `{"detail":"<plain message naming the first bad address>"}` |
| 404 | the session has no report | `{"detail":"No workbook uploaded yet."}` |
| 409 | the report has errors | `{"detail":"Fix the errors listed before previewing or exporting.","error_count":n}` (as the PDF endpoint) |
| 500 | the PDF render failed | as the PDF endpoint |
| 429 | another Outlook launch is still running in this process (non-blocking, process-wide lock) | `{"detail":"Outlook is still opening the previous email. Please wait a moment."}` |
| 502 | PowerShell could not start, exited non-zero (Outlook missing, not signed in, COM error) or took over 120 s | `{"detail":"Outlook could not open a new email. Make sure Outlook is installed and signed in, or download the PDF and attach it yourself."}` |
| 200 | the email is open in Outlook | `{"status":"opened","recipients":[…],"attachment":"<file name>"}` |

So a 501 or 400 can arrive even when the workbook is already gone; the frontend treats a 404 as
"Workbook closed" whenever it arrives.

Recipient rules (`parse_recipients`; the browser runs the same check first, `src/lib/email.js`):
- the typed text is at most 2000 characters ("The list of email addresses is too long. Enter at most
  20 addresses.");
- split on `;`, `,` and whitespace including new lines (the server's whitespace set equals
  JavaScript's `\s`); drop empty entries (no further trimming, so other control characters at the
  edges are refused, not dropped); de-duplicate ignoring case, keeping the first spelling; at most
  20 addresses after de-duplication ("Enter at most 20 email addresses.");
- each address: exactly one `@`, a non-empty local part, a domain with at least one dot and no empty
  labels, at most 254 characters, and no spaces, control or format characters (Unicode C* and Z*:
  zero-width, bidi marks, soft hyphen, C1 controls, private use), double quotes, angle brackets,
  commas or semicolons; an apostrophe is allowed (`o'name@…`);
- error: `"<address>" is not a valid email address. Check it and try again.` (address shown with
  control/space characters as `?`, cut to 80 characters). The browser gives exactly the same
  messages (lengths counted in characters, as on the server) and sends the list it accepted joined
  with `";"`, which is never longer than what was typed, so it always passes the length check.

Email content:
- Subject `FMEA Report - <station> - <analysis_date_text>`; a missing part is left out with its
  dash (`FMEA Report - <station>`, `FMEA Report`). Line breaks and control characters in the values
  become single spaces.
- HTML introduction inserted at the **top** of the body, right after the `<body…>` tag (prepended
  when there is none), so Outlook's default signature, added when the email is displayed, stays
  below it: `Hello,<br><br>Please find attached the Failure Mode Effect Analysis (FMEA) report for
  <b>{station}</b> (Date of Analysis: {date}).<br><br>`, values HTML-escaped; without a station the
  `for <b>{station}</b>` part is dropped, without a date the bracketed part is dropped.
- Attachment name = `safe_attachment_name(report.pdf_filename)`: characters Windows forbids
  (`<>:"/\|?*`) and control/format characters -> `_`, spaces collapsed, leading/trailing spaces and
  dots removed, Windows device names (CON, NUL, COM1…) prefixed with `_`, ends in `.pdf`, at most 150
  characters, `FMEA_Report.pdf` when nothing is left. Applying it twice changes nothing.

Launch (`OutlookMailer.open_draft`, run in the threadpool):
- PDF bytes come from the same per-session cache as `GET /api/report/pdf` (rendered once, reused).
- Takes the process-wide lock without waiting (`OutlookBusy` -> 429 when held).
- Writes the PDF into a fresh `tempfile.mkdtemp(prefix="fmea-mail-")` folder under the attachment
  name, then runs `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile
  -NonInteractive -ExecutionPolicy Bypass -Command <POWERSHELL_SCRIPT>`. PowerShell is started by
  full path (a bare `powershell.exe` could be picked up from the current folder).
- `POWERSHELL_SCRIPT` is fixed text with no double quotes. Values reach it **only** through the
  environment variables `FMEA_MAIL_TO` (addresses joined with `"; "`), `FMEA_MAIL_SUBJECT`,
  `FMEA_MAIL_INTRO_HTML` and `FMEA_MAIL_ATTACHMENT` (NUL characters removed); they are never
  interpolated into the script. The script checks the attachment exists, creates
  `Outlook.Application`, `CreateItem(0)`, HTML format, sets To (when given) and Subject,
  `Attachments.Add(path)`, `Display($false)`, inserts the introduction as above, then brings the
  email window to the front (best effort: a failure there does not fail the request, the email is
  already open). Any other failure exits 1.
- `creationflags=CREATE_NO_WINDOW` on Windows, stdin/stdout discarded, stderr captured; timeout
  120 s.
- **Always** deletes the temporary folder in `finally`, whatever happened (Outlook copied the file
  into the email when it was attached); up to three tries with short waits (a virus scanner may still
  hold the file), then a warning naming the folder.
- Logging: only the number of recipients, never the addresses; PowerShell's error text is logged at
  most 300 characters with anything address-like replaced by `<address>`.
- The runner (`runner(args, env, timeout) -> RunResult`) is injectable. Tests always pass a fake
  runner and a non-Windows platform unless a test asks for Windows, so they never start PowerShell
  or Outlook. `python tools/check_outlook_script.py` (Windows, outside the test suite) only parses
  the script with PowerShell's parser and checks that a broken copy is rejected.

## 5. PDF (PDF owner)

- ReportLab platypus, `BaseDocTemplate`, fonts registered from `backend/assets/fonts` as
  `Sans`, `Sans-Bold`, `Sans-Italic`, `Sans-BoldItalic` (Liberation Sans), embedded as subsets.
  Selectable text; no screenshots. No default Helvetica/Times references (drawings and tables set
  the font explicitly).
- Symbol fallback: a character missing from Liberation Sans that exists in the standard
  **ZapfDingbats** font (✓ ✔ ✗ ✘ ★ …) is drawn in ZapfDingbats (a standard, non-embedded PDF font).
  Characters in neither (⚠ ☐ CJK emoji) print as empty boxes (see 7).
- Page templates: `cover` A4 portrait (no header/footer); `a4` A4 portrait; `a3` A3 landscape.
  Margins: top 20 mm, bottom 16 mm, sides 15 mm (A4) / 12 mm (A3); every body frame has the same
  height. Every non-cover page: header "FMEA Report · <station>" (station whitespace collapsed;
  just "FMEA Report" when blank; shortened with "…" to fit one line; 7.5 pt muted, left, with a
  hairline under it) and footer "Page X of Y" (right). Page numbers count the cover. Use a
  NumberedCanvas; take page size from the canvas per page (doc.width/pagesize stay A4 in mixed
  documents).
- White, print-friendly pages with restrained blue: primary `#1A5A9A`, headings ink `#0A2340`,
  body ink `#1F2933`, muted `#5B6770`; table header fill `#1E6FBF` with white bold text, zebra
  `#F4F8FC`, hairlines `#D5E1EC` (inner grid), **rule `#A9BFD4`** (table
  outline, lines between merged groups, legend rules).
- Body table text: 8 pt on A4 pages, 7.5 pt on A3 analysis pages.
- Order:
  1. **Cover** — port `design-preview/front_page_preview.py` exactly (approved design, verified
     pixel-identical): gradient, motif, "ALCM - Maintenance Strategy" + pulse icon, TNB GENCO logo card
     (`backend/assets/tnb-genco-logo.png`), 3-line title, "Station : <station>",
     "Date of Analysis : <analysis_date_text>", blank white PREPARED BY / APPROVED BY cards (never
     filled). Very long values step the detail text down from 13 pt to 9 pt and are shortened with
     "…" only if they still do not fit above the cards; a word wider than the value column is broken
     between characters. Normal names render exactly as approved.
  2. **Introduction** (A4) — "Introduction"; "Failure Details" table with columns from
     `FAILURE_DETAILS_LABELS` (UOIR ID, Title, Faulty Date, UOIR ID Date, Corrective Action (CA),
     Preventive Action (PA), Equipment), one row per `failure_details` entry, long/multiline text
     wrapped (keep `\n` as line breaks), header repeated; then "Team Members" table (No, Name, Staff
     No, Section). Empty lists show "No failure details were found in the workbook." / "No team
     members were found in the workbook."
  3. For each UOIR in order:
     - **A3 landscape** page: "Analysis: FMEA Analysis", then aligned key/value rows "UOIR ID : <id>",
       "Title : <title>", one "Note : <text>" row per note; then the full `analysis` table: every
       column (header text exactly as in the workbook) and every row, in order. Body 7.5 pt, header
       bold 7.5 pt, header repeated on continuation pages. No analysis -> "No analysis worksheet is
       linked to this UOIR, so there is no table to show."; no columns -> "The analysis worksheet has
       no table columns."; no rows -> header plus "The analysis worksheet has no data rows."
       - Column widths: flag columns (H, S, E, O, 1, 2, 3, H4, H5, S4) 16 pt and centred; No., New
         Task and Frequency centred; width hints for known columns (No. 24, Failure Mode 112, Failure
         Effect 132, RecommendedStrategy 64, Task 168, Frequency 48, Trade 54, KKS 90, New Task 34,
         Review task 78, Maintenance Plan No 62, Remark 100; others 70), text columns scaled to the
         frame. When extra columns make it narrower, each text column keeps at least 26 pt while there
         is room; with very many columns everything shrinks evenly and cell side padding is reduced
         (so 300+ columns still lay out, though unreadably).
       - Long tokens never overflow: break opportunities after `/ \ - _ . , ; : + |` and at
         lower→upper case or letter↔digit changes; a word only slightly too wide sets **that cell**
         up to 20 % smaller (7.5 -> 6 pt); a word wider still is broken between characters.
       - Header labels: a label taller than its share of 35 % of the page height is set smaller in
         that cell only (down to 4 pt) and shortened with "…" only if it still does not fit.
       - Merges: ranges are used as SPAN unless they overlap an earlier range or their covered cells
         hold text (then drawn unmerged, text never hidden). Rows joined by vertical merges form a
         band (shared zebra, rule line between bands). A merged group ≤ 40 % of the frame height moves
         to the next page intact; a larger group splits between rows with the value repeated on the
         next page followed by "(cont.)". An empty merged cell never shows "(cont.)". A one-row
         horizontal merge that fitted completely above a row split is not repeated below it.
       - A single row taller than a page (or the first row where it must be placed) splits inside the
         row at line boundaries; the identifying column(s) are repeated with "(cont.)" on the
         continuation (No. and Failure Mode in the analysis table; the first column in other
         tables). Merged text taller than an empty page -> that one group is drawn unmerged (text
         splits inside its row); later groups keep their merges.
     - **A4 portrait** page: "Analysis: FMEA Summary", "UOIR ID : <id>", "Title : <title>"; summary
       None -> "No summary is available for this UOIR."; otherwise three cards in a row: Failure
       Mode, Maintenance Task, Task Executed (label + big number); section "Existing vs Revised" with
       sub-heading "Recommended Strategy": vector pie chart (reportlab.graphics, plain pie, white
       slice separators, a single slice drawn as a full disc, colours from `PieSlice.color`) with a
       legend table Strategy | Count | % for every slice and a final **Total** row (empty pie ->
       "No strategy values to chart."). When pie + legend would take more than 80 % of the page (in
       practice dozens of strategies) the pie is drawn first and a full-width legend follows,
       continuing on the next page with its header repeated; the headings stay with the pie and the
       first legend rows. Then the table Code | Strategy | Existing | New from `strategy_rows` (blank
       code shows "—"); section "Work-Centre Execution": table Work Centre | Total | Executed |
       Pending (none -> "No rows with New Task set to Yes or No."); under it one line per
       `not_counted` row ("Not counted: row 8 (OC, SYNMECH-A) — New Task blank.") and per duplicate
       ("Row 9 is identical to an earlier row and was counted once."). Keep the summary on one page
       when it fits; otherwise flow with repeated table headers.
  4. **Recommendation** (A4, starts on a new page, continuous): "Recommendation"; for each UOIR a
     heading "UOIR ID <id>: <title>"; for each group a sub-heading `group.heading` ("KKS not
     specified" when empty); table with a 2-row header: "Failure Mode" (spans both header rows) |
     "Recommendations" (spans Task and Frequency) / "Task" | "Frequency"; rows in order; header
     repeated on continuation pages; keep headings with the header + first 2 rows (CondPageBreak,
     capped at 80 % of the page), never orphan a heading. Do not force a page break per UOIR. No
     groups -> "No recommendations for this UOIR."; no UOIRs -> "No UOIRs were found in the workbook."
- Escape `& < >` in Paragraph text; empty cells render empty.
- PDF metadata: title "Failure Mode Effect Analysis (FMEA) Report", subject = station with whitespace
  and newlines collapsed, creator "FMEA Report Generator".
- Performance guide: ~0.3 s for a normal report; about 6 ms per analysis row for very large tables.

## 6. Frontend (FRONTEND owner)

- React + Vite, **JavaScript** (JSX), plain CSS with design tokens (CSS variables), `recharts` for the
  pie (loaded lazily), `lucide-react` icons. No UI framework. Dev server proxies `/api` to
  `http://127.0.0.1:8000`; `npm run build` -> `frontend/dist` (base "/", no source maps). All fetches
  use `credentials: "same-origin"`. Requires Node 20.19+ / 22.12+ to build.
- A mock mode (`VITE_MOCK=1`, via `npm run dev:mock` which loads `frontend/.env.mock`) serves a
  SYNTHETIC report JSON from `src/mocks/` so screens can be built and checked without the backend.
  Mock code is only reachable behind `import.meta.env.DEV && VITE_MOCK === '1'`, so a production build
  never contains it. As in the real app the mock report lives only in page memory (a refresh starts
  again on Upload); only the mock sign-in is remembered in `sessionStorage`. Switches: `?mock_reset=1`,
  `?mock_signed_in=1`, `?mock_auth=databricks`, `?mock_outlook=0` (Email the PDF not available);
  passwords `wrong`/`locked`; upload names containing `error`/`broken`/`slow`; Email recipients
  containing `outlook-fail` (502) or `outlook-busy` (429); `window.fmeaMock.expireSession()` (next
  request 401) and `window.fmeaMock.closeWorkbook()` (next preview/download/email 404, as after another
  tab). The mock answers `POST /api/report/email` with the same 200/400/404/409/429/501/502 replies
  as the server (it checks 404/409 before 501/400). If the model changes, regenerate `src/mocks/synthetic-report.json` and validate it
  against `backend/report/models.py`.
- Visual direction: engineering reliability workspace. Deep navy sidebar `#0A2340` with a subtle
  technical grid; electric blue/cyan accents (`#1E6FBF`, `#22B8E6`); light content surfaces
  (`#F4F7FB` page, white cards, hairline `#DCE4EE`); amber `#B7791F`/`#FAB219` only for warnings and red
  `#C53030` only for blocking errors, each with an icon + label. Rounded cards (10–12px), generous
  spacing, crisp tables, restrained animation (the pie is drawn without animation). Font: system UI
  sans. Must work down to 1280px wide and degrade sensibly on tablet (≤ 1100px: the sidebar becomes a
  drawer; hidden when closed, focus moves to Close, Escape/Close/backdrop return focus to the menu
  button).
- Accessibility as built: keyboard focus ring blue `#1E6FBF` on light surfaces (cyan only on the navy
  sidebar); faint text token `#66727e` (≥ 4.5:1); UOIR status in the sidebar uses icons with labels,
  not colour alone; the pie is not a keyboard stop and carries an `aria-label` listing every slice;
  disabled Export button keeps ≥ 4.5:1 contrast.
- Screens / flow: **Sign in** -> workspace with stepper **Upload Excel → Review Data → Preview Report → Export PDF**.
  - Sign in: "FMEA Report" + "ALCM - Maintenance Strategy"; username/password; plain error messages
    (empty fields, 401, 429); skipped entirely when `/api/auth/me` returns `auth_mode: "databricks"`
    (no Sign out button; "Signed in with Databricks"). Any 401 from a signed-in call returns to sign-in
    with a "Session ended" notice. Footer: "Workbooks are read in memory only and never saved. They
    are discarded when you sign out or leave the page."
  - `features` comes from `/api/auth/me` and `/api/auth/login` (`App.jsx`; `outlook_email` is true only
    when the server sends exactly `true`) and flows App -> Workspace -> ExportView.
  - Workspace lifecycle: one-time use as in 4.1 (discard on mount behind "Preparing your workspace…",
    discard on `pagehide`, reload on a back/forward-cache `pageshow`, 404 -> Upload with the "Workbook
    closed" notice).
  - Shell: navy sidebar (brand, stepper, section nav: **Data Checks**, Front Page, Introduction,
    Analysis (UOIR list), Recommendation; user + Sign out at the bottom). Top bar: file name, station/
    date (full text in a tooltip), status chips (n errors / n warnings, opening Data Checks), "Upload
    another", prominent **Export PDF** (disabled with a visible reason when errors; when enabled it
    opens the Export step and starts the download once).
  - Upload: drag-and-drop zone + browse; client checks `~$` lock files, `.xls` (save as .xlsx),
    other extensions, empty files and size (hard-coded 20 MB in `src/api/client.js`, see 7); upload
    progress, Cancel, then a "reading workbook" state; errors from the API shown above the dropzone;
    focus returns to "Browse files" after Cancel or failure. A note under the header: "Your workbook
    is read in memory only and never saved. It is discarded, with its report and PDF, when you sign
    out or leave the page." The "Workbook closed" notice (4.1) shows here until dismissed or a new
    upload starts. With a report open, **Remove** discards it (`DELETE /api/workbook`).
  - Data Checks (validation panel): fact cards; "Ready to export" or "Export blocked" banner; groups
    "Must fix before export" (errors) and "Please check" (warnings), hidden when empty; "For
    information" (info) collapsed by default and hidden when empty; each item shows the message and
    location chips (sheet, row, column, cell) and, when it points into an analysis table, **Show in
    table** (switches UOIR, scrolls to the column and marks the row/cell).
  - Front Page: HTML rendition of the cover data (station, date, blank Prepared by / Approved by boxes)
    plus a note of where each value comes from.
  - Introduction: Failure Details and Team Members tables (wrapping, multiline preserved).
  - Analysis: UOIR list/selector (ID, title, counts); tabs **FMEA Analysis** (notes above; full table
    with horizontal scroll, sticky header and an extra muted **Row** column with the Excel row number,
    not part of the report; merged cells via rowSpan/colSpan; cells drawn by header column so short or
    long `cells` lists never shift columns; merges outside the table ignored, others clipped, overlaps
    skipped; duplicate and warning rows marked) and **FMEA Summary** (3 cards; "Existing vs Revised"
    pie + legend with counts & % + strategy table, same colours, standard zero rows muted;
    "Work-Centre Execution" table; not-counted/duplicate notes; empty states when `summary` is None or
    the pie is empty).
  - Recommendation: UOIR selector; tabs **New Task = Yes** and **New Task = No**, plus **New Task not
    set** only when such rows exist. "Not set" holds **every row whose new_task is not "yes" or "no"**
    (blank, invalid or unexpected), so each row is in exactly one tab; rows there are tagged "NSM · not
    required", "Blank" or "Not Yes or No: "<value>"". Switching to a UOIR without such rows falls back
    to the Yes tab. Groups with `heading`; table Failure Mode | Recommendations (Task, Frequency) with
    the Row column. Tabs are view filters only ("Tabs only filter this view. The PDF lists every row.").
  - Preview: first `GET /api/report/pdf?download=0` with fetch, abandoning the body once the headers
    arrive, so 409/500 show as plain messages; then `<iframe src="/api/report/pdf?download=0">` (served
    from the PDF cache) with a hint for browsers that cannot show PDFs inline. Shows a "Preview blocked"
    state listing the errors instead when `can_export` is false. A 404 -> "Workbook closed" (4.1).
  - Export: downloads via `fetch('/api/report/pdf?download=1')` -> blob -> `<a download=pdf_filename>`,
    so a failure shows a clear message instead of a JSON page; success message after the download
    starts; "Export blocked" state when `can_export` is false. A 404 -> "Workbook closed" (4.1).
  - Export, **Email the PDF** card (under the download card, only when `report.can_export`; always
    shown): an optional text input labelled "Recipients (optional)" (label/for, hint linked by
    `aria-describedby`), and one button chosen by `features.outlook_email`:
    - true: "Open in Outlook" (lucide `Mail` icon), hint "Separate several addresses with a semicolon.
      Leave empty to choose recipients in Outlook.", working state "Opening Outlook…", success alert
      "Outlook opened a new email with the PDF attached. Check it, then press Send in Outlook.", error
      alert with the server message; on 502 or 501 the alert also has a "Download PDF & open email
      instead" button (the fallback below).
    - false: "Download PDF & open email", hint "… Leave empty to choose recipients in your mail app.";
      the click opens the `mailto:` link (4.2) straight away (while it still counts as the user's
      action), then downloads the PDF ("Downloading PDF…"); success alert "A new email was opened in
      your mail app and <pdf_filename> was saved to your Downloads folder. Attach the PDF to the email,
      then press Send."
    The recipient check of 4.2 runs in the browser first (`src/lib/email.js`); a bad address marks the
    input `aria-invalid` and points it at the error. Status messages sit in an `aria-live="polite"`
    region. A 404 -> "Workbook closed".
  - Error messages: server `detail` strings are shown when plain; otherwise per-status fallbacks,
    including 502/503/504 ("The FMEA service is not available right now…") and network failures.
  - **ErrorBoundary** (`src/components/ErrorBoundary.jsx`): a "section" boundary around the content
    area shows a plain "This part of the report could not be shown" message (sidebar and top bar keep
    working; it resets when the section, UOIR or tab changes); an outer "page" boundary offers
    "Reload the page". Details go to the console only.
  - Loading, empty ("Upload a workbook to begin"), error and success states everywhere. No technical
    jargon, no raw JSON, no stack traces.

## 7. Open change requests (not decided; current behaviour stays until the owner decides)

| Area | Request | Current behaviour |
|---|---|---|
| Parser 3.6 | Severity for extra tabs with the same UOIR ID when the title picks one (a warning is safer: that tab's data is left out) | info `SHEET_NOT_USED` |
| Parser 3.5 | Should `ROWS_AFTER_BLANK_ROW` be an error for UOIR rows (a whole UOIR is left out)? | warning |
| Mapping | Move the Team Member label words ("station", "date of analysis") into `mapping.py` | constant `_TEAM_LABELS` in `builder.py` |
| Mapping / summary | Distinct fallback colours for unknown and extra `R-` strategy codes | all share `#c3c2b7` |
| PDF fonts | Embed a symbol-capable font (e.g. a DejaVu Sans subset) or formally allow non-embedded ZapfDingbats | ZapfDingbats fallback; other symbols print as boxes |
| API / frontend | Expose `max_upload_mb` to the browser (e.g. in `/api/auth/me`) | frontend hard-codes 20 MB |
| API | Lightweight PDF readiness check (`HEAD /api/report/pdf` or a status endpoint) | frontend GETs and abandons the body |
| API | Force `Secure` cookies automatically in databricks mode | depends on `COOKIE_SECURE` (true in app.yaml) |
| API | Concurrency limit (semaphore) for parsing/rendering per process, taken before the body is read | signed-in users trusted; parallel uploads each hold up to `MAX_UPLOAD_MB` in memory |
| Tests (owner) | Starlette 1.6 deprecates `TestClient` with httpx; pin a compatible client before upgrading | warning only |
| Frontend | Trap focus in the open tablet drawer; more room in the top bar at 1280px; sidebar UOIR links from Recommendation stay in Recommendation | not done |
| Parser | Two-row analysis headers (group header above sub-headers) | not supported; sub-header row read as data (blank-value errors) |
| Email | Try "Open in Outlook" against a real classic Outlook (introduction above the default signature, Outlook's "another program is accessing" security prompt) | the only PC tried (2026-11-04) uses the new Outlook, so the draft was refused by Windows (DCOM 10010) and the app now offers the mail-app fallback there; the draft itself is checked with a fake runner and the PowerShell parse check only |
| API / frontend | Tie the report to the page that uploaded it (e.g. a report id checked by preview, download and email), so a stale tab can never get another tab's PDF | one report per browser session: opening a second tab closes the first tab's workbook, but if the second tab then uploads, a not-refreshed first tab's Preview/Export/Email serve the second tab's workbook |

## Change log

- **2026-11-04 — Email the PDF works with the new Outlook (mail-app fallback).**
  - Real test: on a PC with the "New Outlook" toggle on, the Outlook draft failed after ~34 s
    (CO_E_SERVER_EXEC_FAILURE; the new Outlook cannot be automated).
  - `classic_outlook_ready()` (registry: Outlook.Application class registered, UseNewOutlook != 1)
    now gates `features.outlook_email` unless `OUTLOOK_EMAIL=on`; checked on every request.
  - When drafts are not offered, the Export card shows "Download PDF & open email" (mailto: link
    + PDF download, 4.2/5) instead of a note; a 502/501 from "Open in Outlook" offers the same
    fallback. 501 message reworded.
- **2026-11-04 — review fixes for one-time use and Email the PDF.**
  - Security: `LocalOnlyMiddleware` (local-only Host and Origin check, 403) when the app runs only
    for this computer; `create_app(extra_local_hosts=...)` for tests.
  - 4.1: an upload still being read keeps nothing when the workbook is discarded, a newer upload
    starts or the browser disconnects (409); `pagehide` discards only when the page holds a report
    or an upload; a workspace that fails to draw discards at once.
  - 4.2: apostrophes allowed in addresses; the browser check gives the server's exact rules and
    messages (Unicode C*/Z* refused, no extra trimming) and sends the list joined with `";"`.
  - 3.11 / tests: the sample-like workbook's rows were changed so none of its counts match a real
    workbook; remaining real-looking fragments (a KKS unit range, a date, a UOIR ID, a user folder
    path) were replaced in tests. The PowerShell parse check moved out of the test suite to
    `tools/check_outlook_script.py`.

- **2026-11-04 — one-time use, Email the PDF, real data removed.**
  - 4.1 (new): no database; the workbook is read in memory and never saved; the frontend no longer
    restores the report with `GET /api/report` but calls `DELETE /api/workbook` when the workspace
    opens and on `pagehide` (keepalive), reloads on a back/forward-cache `pageshow`, and turns a 404
    from preview/download/email into the "Workbook closed" notice. Sign-in footer and Upload note
    say so.
  - 4.2 (new): optional "Email the PDF" on the Export step opens a new classic-Outlook email (Display,
    never Send) through PowerShell COM automation, local Windows only; `OUTLOOK_EMAIL`
    (auto/on/off, app.yaml off); `features.outlook_email` in `/api/auth/me` and `/api/auth/login`;
    `POST /api/report/email`; `backend/mail/outlook.py`; `create_app(outlook=...)`. The PDF is copied
    to a temporary folder only while Outlook attaches it.
  - 1, 3.11, tests: the real sample workbook (its path and its expected values) is gone. Tests use the
    SYNTHETIC sample-like workbook (`--variant sample`), which never skips; `FMEA_SAMPLE_WORKBOOK` now
    only drives the opt-in value-free smoke test `test_local_workbook_smoke.py`. Work-centre codes in
    tests and examples are SYN* codes.
  - 6: mock switches `?mock_outlook=0`, `outlook-fail`/`outlook-busy` recipients and
    `window.fmeaMock.closeWorkbook()`; `?mock_report` removed (the mock no longer keeps a report).

- **2026-11-04 — Date of Analysis taken as written.** Removed the `DATE_OF_ANALYSIS_BEFORE_FAULT`
  warning: Date of Analysis comes from `B3` on Team Member and is not compared with the fault dates
  (user decision). B3 blank / not a date are still errors. Sample workbook now has no issues.
- **2026-09-17 — final verification fixes.** Pre-filled whole numbers in the No. column below an
  analysis table are no longer collected as notes; tests no longer hold a real staff number;
  README.md may document the initial development account (password-location test updated).
- **2026-09-17 — as-built update after component builds and adversarial reviews.**
  - Added `README.md` (setup, workbook rules, calculations, messages, PDF, deployment, security,
    limitations) and made the contract describe the accepted implementation.
  - 1–2: layout lists the modules actually built (`api/services.py`, `api/upload.py`, PDF modules,
    `ErrorBoundary`, review test files); `WorkbookOpenError` lives in `excel/reader.py`;
    `make_pdf_filename` trims `_`; `create_app` test keyword arguments and the services interface;
    `server_options`. The 3.11 check is syntactic only.
  - 3.1: `FORMULA_NO_VALUE` found by an XML scan; `keep_links=False`; only used sheets read.
  - 3.2: zero-padding only for whole numbers, sign before the padding.
  - 3.2a (new): merged-cell carry rule — carry down only within the same column from a merge that
    starts on a data row, applied to Team Member, UOIR and analysis rows; `MERGED_CELLS_CARRIED` only
    for real carries.
  - 3.4/3.5/3.7: new warning `ROWS_AFTER_BLANK_ROW` with its thresholds; header-missing behaviour;
    UOIR IDs keyed without leading zeros; first non-blank Title used and named in
    `UOIR_DUPLICATE_ID_CONFLICT`; Excel datetimes keep their time in the text.
  - 3.6: title checks skipped when the Title is blank; `B1` check skipped when `B1` is inside the
    table; info `SHEET_NOT_USED` for extra same-ID tabs; `ANALYSIS_SHEET_TITLE_MISMATCH` only for a
    single candidate.
  - 3.7/3.8: `summary` None on missing/duplicate headers, all zeros on `ANALYSIS_NO_ROWS`; issue
    granularity; one-line header in `REQUIRED_VALUE_BLANK`.
  - 3.9: heading rule for blank KKS/equipment. 3.10: issue sort key. 3.12 (new): issue catalogue.
  - 4: extra plain responses (400 no file / upload incomplete, 422, 404 unknown API path, 401 wording
    per mode, default messages); 64 KB body limit (413); per-client sign-in ceiling (50 / 5 min) and
    `Retry-After`; hashed limiter keys; `filename*` in `Content-Disposition`; failed uploads keep the
    previous report; databricks per-user session cap (5); `proxy_headers` only in databricks mode;
    Windows Selector event loop, `server_header=False`; static-file path safety, top-level dist files,
    `/assets` 404, `index.html` no-cache; docs disabled; invalid `SESSION_COOKIE_NAME` fails at startup.
  - 5: rule colour `#A9BFD4`; ZapfDingbats symbol fallback; per-cell shrink (≤ 20 %); header shrink
    to 4 pt then ellipsis; column width floor and padding shrink; pie-then-legend for long legends
    and legend Total row; single-row split repeats identifying columns with "(cont.)"; unmerged
    fallback for merged text taller than a page; no repeat of completed one-row merges; no "(cont.)"
    on empty merged cells; "KKS not specified"; empty-section messages; header ellipsis and cover
    station fallback; metadata subject collapsed; render lock.
  - 6: Data Checks section, Row column, Preview fetch-then-iframe, Export via blob, top-bar Export
    behaviour, "New Task not set" tab includes invalid/unexpected values, ErrorBoundary,
    accessibility fixes (focus ring, faint token, status icons, pie tab stops, tablet drawer),
    502/503/504 messages, mock-mode script and switches.
  - 7 (new): open change requests collected from builders and reviewers.
  - Example messages outside 3.11 now use SYNTHETIC values. 3.11 (the real-workbook expectations
    asserted by `test_excel_sample_workbook.py`) is unchanged.
