# Accept Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let engineers accept value errors (and mark warnings as checked) on Data Checks, so a
report can be previewed and exported with the data exactly as written.

**Architecture:**
- **Every built report gets ids.** `report_id`, per-issue `id`, `acceptable` and `accepted`.
- **The rule lives in one place.** `export_allowed` / `open_error_count` decide whether export is
  allowed.
- **The session holds the state.** A new `POST /api/report/issues/acceptance` changes the
  session's report copy-on-write. The PDF and email gates use the same rule.
- **The screens count open issues.** The React app counts only issues that are not accepted, and
  `ChecksView` gets Accept / Accept all / Undo and an Accepted group.

**Tech Stack:**
- Backend: Python (FastAPI, pydantic) and pytest.
- Frontend: React 19 + Vite 8, plain CSS, verified by a build and in the browser.

**Spec:** `docs/superpowers/specs/2026-11-07-accept-issues-design.md`. Read it before any task;
"spec 4.2" means its section 4.2.

## Global Constraints

- **Branch:** `feature/accept-issues`. Commit per task. Never push, merge or touch `main`.
  Merging later updates the public Render app.
- **Python 3.11 syntax only.** No new dependencies.
- **SYNTHETIC data only.** Before every commit, scan the staged files against
  `.claude/hooks/forbidden-terms.txt` with Python (no hits allowed, never print the terms). Never
  open the `.xlsx` in the project root.
- **Exact copy.** Every message and UI string in the spec is exact copy.
- **Owner files.** `models.py`, `mapping.py` and `CONTRACT.md` change only as the spec says.
- **Frontend build checks** go to a scratch folder, from `frontend/`:
  `node -e "import('vite').then(v => v.build({ build: { outDir: '<scratchpad>/dist-check', emptyOutDir: true } })).then(() => process.exit(0))"`.
  Only Task 6 rebuilds `frontend/dist`. Never `npm run build`.
- **Commits:** end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Tests:** run with `python -m pytest …` from the project root.

## Review Focus

1. **Accept all, then Undo one error.** Export must be blocked again at once: the PDF returns
   409, and Next shows "Fix 1 error to preview". Owner: Task 2
   (`test_undo_blocks_the_pdf_again`) and Task 4 (browser step).
2. **Two quick clicks on different items.** Only one request may run; the screen must end in the
   server's state. Owner: Task 4 (all buttons disabled while busy; browser step).
3. **Workbook replaced in another tab.** Accept gets 409 and must return to Upload with the
   "Workbook closed" notice, never showing the other workbook. Owner: Task 2
   (`test_stale_report_id_is_refused`) and Task 3 (`ChecksView` → `onWorkbookClosed`).
4. **An accepted invalid date ("TBC June 2026").** It must render on the cover and in the email
   subject without errors, with file name `…_undated.pdf`. Owner: Task 1
   (`test_invalid_date_keeps_its_text`) and Task 2 (`test_pdf_renders_with_accepted_value_errors`).
5. **Structural and value errors together.** After the value errors are accepted, the banner must
   say "Fix them in Excel…" with no "accept" hint, and export stays blocked. Owner: Task 2
   (`test_structural_error_keeps_export_blocked`) and Task 4 (banner state).

---

### Task 1: Issue ids, acceptability and the two parser changes

**Files:**
- Modify: `backend/config/mapping.py`. Add `ACCEPTABLE_ERROR_CODES` (spec 3.1).
- Modify: `backend/report/models.py`:
  - `Issue.id: str = ""`, `Issue.acceptable: bool = False`, `Issue.accepted: bool = False`;
  - `Report.report_id: str = ""`;
  - functions `export_allowed`, `open_error_count` and `finalise_report`.
- Modify: `backend/report/builder.py`:
  - call `finalise_report`;
  - the all-blank-row exception;
  - keep the invalid date's text;
  - pass `uoir_table_read` to `coverage_issues`.
- Modify: `backend/excel/linking.py`. `coverage_issues(..., uoir_table_read: bool | None = None)`;
  `ANALYSIS_SHEET_NONE` uses it (None means the same as `uoir_list_read`).
- Modify: `backend/tests/test_api_support.py`.
  `make_report(errors=0, codes=None, …)` builds issues with real codes and returns
  `finalise_report(...)`.
- Test: create `backend/tests/test_issue_acceptance.py`.

**Interfaces:**
- **Produces (`backend/report/models.py`):**
  - `export_allowed(issues: list[Issue]) -> bool`
  - `open_error_count(issues: list[Issue]) -> int`
  - `finalise_report(report: Report, not_acceptable_rows: Collection[tuple[str, int]] = ()) -> Report`:
    - returns a deep copy;
    - sets `report_id = secrets.token_hex(8)` and ids "1".. in list order;
    - sets `acceptable`: warning → True; error with code in `ACCEPTABLE_ERROR_CODES` → True,
      except a `REQUIRED_VALUE_BLANK` whose `(sheet, row)` is in `not_acceptable_rows`; everything
      else → False;
    - sets `can_export = export_allowed(issues)`.
- **Produces (`backend/config/mapping.py`):**
  - `ACCEPTABLE_ERROR_CODES = frozenset({"REQUIRED_VALUE_BLANK", "NEW_TASK_INVALID", "UOIR_VALUE_BLANK", "STATION_BLANK", "ANALYSIS_DATE_BLANK", "ANALYSIS_DATE_INVALID"})`.
- **Produces (`backend/tests/test_api_support.py`):**
  - `make_report(*, errors: int = 0, codes: list[str] | None = None, station=…, source_filename=…, pdf_filename=…) -> Report`.
  - When `codes` is given, it makes one error per code. The message is
    `f"SYNTHETIC {code} {n}"`; `sheet`, `row` and `cell` are SYNTHETIC values such as
    `"UOIR ID 901 - SYNTHETIC"`, `3 + n` and `"R3"`.
  - It always adds one warning and finalises the report.
  - `errors=N` keeps today's behaviour (`SYNTHETIC_ERROR`, not acceptable).

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_issue_acceptance.py`, using
  `clean_workbook_with`, `synthetic_tool` and `build_report`:
  - **`test_issue_ids_follow_report_order`:**
    `[i.id for i in report.issues] == [str(n) for n in range(1, len(report.issues) + 1)]`.
    Use the edge workbook (`edge_workbook_bytes`), which has many issues.
  - **`test_acceptable_by_code_group`:** on the edge workbook, every warning is acceptable; every
    info is not; every error is acceptable iff its code is in `ACCEPTABLE_ERROR_CODES` and it is
    not an all-blank row.
  - **`test_report_id_differs_between_builds`:** build the clean workbook twice; the two ids are
    16 hex chars and differ.
  - **`test_can_export_unchanged_when_nothing_accepted`:** clean → True; one blank KKS (clear
    `CLEAN_TAB_601` R3) → False.
  - **`test_all_blank_row_is_not_acceptable`:** on tab 601 write a row 7 whose only filled cells are
    `No.=5` and `Frequency="1M"`, then build. Its `REQUIRED_VALUE_BLANK` issues all have
    `acceptable is False`, while a blank KKS on row 3 has `acceptable is True`.
  - **`test_invalid_date_keeps_its_text`:** Team Member B3 = `"TBC June 2026"` gives
    `analysis_date is None`, `analysis_date_text == "TBC June 2026"`,
    `pdf_filename.endswith("_undated.pdf")`, and one `ANALYSIS_DATE_INVALID` that is acceptable.
  - **`test_all_uoir_ids_blank_and_no_tabs_stays_blocked`:** blank B5 and B6 on the UOIR sheet and
    delete both tabs. Then:
    - `"ANALYSIS_SHEET_NONE"` is in the codes and is not acceptable;
    - after setting `accepted=True` on every acceptable issue,
      `export_allowed(report.issues) is False`.
- [ ] **Step 2: Run them and check that they fail.**
  Run: `python -m pytest backend/tests/test_issue_acceptance.py -q -p no:cacheprovider`
  Expected: FAIL (ImportError / AttributeError).
- [ ] **Step 3: Implement** the model fields and helpers, the mapping constant and the builder
  changes:
  - **`uoir_table_read`:** True once `_read_uoirs` found the header row.
  - **All-blank rows:** collected in `_task_records` when every
    `ANALYSIS_REQUIRED_VALUES` field of the row is blank.
  - **Invalid date:** `analysis_date_text` = `format_date(date)` if a date was read, else the
    trimmed raw text for `ANALYSIS_DATE_INVALID`, else "".
  - **`linking.coverage_issues`:** the new keyword, plus `make_report`.
  - **Message fields:** `analysis_date_text` feeds the email subject/intro and the
    `ChecksView`/`ExportView` facts unchanged; no other code changes.
- [ ] **Step 4: Run the tests and check that they pass.**
  Run: `python -m pytest backend/tests -q -p no:cacheprovider`
  Expected: all PASS, with the existing tests unchanged apart from any that asserted
  `analysis_date_text == ""` for an invalid date. Update those to the typed text and comment
  "spec 3.4 (9a)".
- [ ] **Step 5: Commit.**
  `git commit -m "Issue ids and acceptability; keep invalid date text; no-tabs check with blank IDs"`

---

### Task 2: Acceptance endpoint and export gate

**Files:**
- Modify: `backend/sessions/store.py`. Add
  `update_issue_acceptance(session: Session, report_id: str, ids: list[str], accepted: bool) -> Report`.
  It raises `AcceptanceError(status: int, detail: str)`, a new exception class in the same module.
- Modify: `backend/api/routes_report.py`:
  - add `AcceptanceRequest(BaseModel)` with `report_id: str`, `ids: list[str]`, `accepted: bool`;
  - add `POST /report/issues/acceptance`;
  - `_error_count` → `open_error_count`.
- Test: `backend/tests/test_api_report.py` (new tests) and `backend/tests/test_api_local_only.py`
  (add the route to the refused-origin test).

**Interfaces:**
- **Consumes (Task 1):** `finalise_report`, `export_allowed`, `open_error_count`, and
  `make_report(codes=[...])`.
- **Produces:** the route and its JSON (the full report).
- **Exact `AcceptanceError` messages and order** (spec 4.2):
  1. 404 "No workbook uploaded yet."
  2. 409 "This workbook is no longer open here. Upload it again."
  3. 400 "Choose at least one item."
  4. 400 "Too many items in one request."
  5. 400 "Some of these items are no longer in the report. Upload the workbook again."
  6. 400 "This item can't be accepted. Fix it in the workbook and upload again."
- **Store rules:**
  - Copy-on-write under `self._lock`; never edit `session.report` in place.
  - No `report_version` bump, and the PDF cache is kept.
  - Duplicate ids count once.
  - The route returns `_report_response(returned_report)`.

- [ ] **Step 1: Write the failing tests** in `test_api_report.py`. Use the existing app/client
  fixtures. Upload with `services.next_report = make_report(codes=[…])`; read `report_id` and the
  ids from `GET /api/report`. Tests:
  - **`test_accept_value_error_unblocks_pdf`:** codes `["REQUIRED_VALUE_BLANK"]` → PDF 409 → accept
    the error's id → 200 with `can_export` true and the issue accepted → `GET /api/report/pdf` 200.
  - **`test_accept_all_errors_in_one_request`:** codes `["REQUIRED_VALUE_BLANK", "NEW_TASK_INVALID", "STATION_BLANK"]`.
  - **`test_undo_blocks_the_pdf_again`:** accept, PDF 200, undo, PDF 409 with `error_count == 1`.
  - **`test_structural_error_keeps_export_blocked`:** codes
    `["REQUIRED_VALUE_BLANK", "ANALYSIS_HEADER_MISSING"]`. Accepting the structural id → 400
    "This item can't be accepted…", and nothing changes. Accepting the value id → 200, but
    `can_export` stays false and the PDF 409 has `error_count == 1`.
  - **`test_unknown_id_is_refused`:** 400 "Some of these items…".
  - **`test_stale_report_id_is_refused`:** an empty `report_id` → 409; a different `report_id`
    → 409; nothing changes.
  - **`test_empty_ids_are_refused`:** 400 "Choose at least one item.".
  - **`test_duplicate_ids_count_once`:** 200.
  - **`test_undo_on_structural_id_is_refused`:** 400.
  - **`test_accept_warning_marks_it_only`:** `can_export` is unchanged.
  - **`test_info_cannot_be_accepted`:** use the real builder through `FakeServices.build_report`
    returning a finalised report with an info issue → 400.
  - **`test_new_upload_resets_acceptance`:** set a fresh `make_report` before the second upload;
    the new `report_id` differs and nothing is accepted.
  - **`test_pdf_cache_kept_across_acceptance`:** `services.render_calls` stays 1 across accept,
    undo and accept.
  - **`test_email_gate_follows_acceptance`:** use the existing email-test setup (fake Outlook).
    It gives 409 before accept and goes past the gate after.
  - **`test_plain_text_body_is_refused`:** `content=b'{}'` with `Content-Type: text/plain` → 422.
  - **`test_pdf_renders_with_accepted_value_errors`:** use the real `build_report` +
    `render_pdf` (not the fakes) on a clean SYNTHETIC workbook with:
    - a blank KKS;
    - New Task "Done";
    - a blank Station;
    - Date of Analysis "TBC June 2026".

    Accept all → the PDF bytes start with `%PDF`.
  - **In `test_api_local_only.py`**, extend `test_changes_from_a_page_on_another_origin_are_refused`
    to also POST `/api/report/issues/acceptance` (`json={"report_id": "x", "ids": ["1"], "accepted": True}`)
    → 403 for each foreign origin.
- [ ] **Step 2: Run them and check that they fail.**
  Run: `python -m pytest backend/tests/test_api_report.py backend/tests/test_api_local_only.py -q -p no:cacheprovider`
  Expected: the new tests FAIL (404 route).
- [ ] **Step 3: Implement** the store method, the request model, the route and the
  `_error_count` change.
- [ ] **Step 4: Run the whole suite.**
  Run: `python -m pytest -q -p no:cacheprovider` → all PASS.
- [ ] **Step 5: Commit.** `git commit -m "Accept or undo issues for this report; export follows open errors"`

---

### Task 3: Frontend data layer, Workspace and counts

**Files:**
- Modify: `frontend/src/lib/report.js`. Add
  `openIssues(issues) => issues.filter(i => !i.accepted)`; `countIssues` is unchanged.
- Modify: `frontend/src/api/client.js`. Add
  `setIssueAcceptance(reportId, ids, accepted)` → `requestJson('/api/report/issues/acceptance', { method: 'POST', json: { report_id: reportId, ids, accepted } })`.
  It returns the report and throws `ApiError` with `status`.
- Modify: `frontend/src/screens/Workspace.jsx`:
  - `counts = countIssues(openIssues(report.issues))`;
  - add `replaceReport(next)`: it calls `setReport(next)` only if
    `report && next && next.report_id === report.report_id`, and never resets the navigation;
  - pass `onAcceptance={(ids, accepted) => …}` and `onWorkbookClosed` to `ChecksView`;
  - `acceptance` state `{ busy: boolean }`.
- Modify: `frontend/src/components/StepNav.jsx`. `ReviewStepNav`'s Next is
  `disabled: !report.can_export` (it needs the `report` prop or a `canExport` prop). The reason
  text is unchanged and uses the open count.
- Modify: `components/SectionSelector.jsx`, `components/SectionHeading.jsx` and
  `components/Sidebar.jsx` (the section markers). Use `openIssues(...)` before
  `countIssues(issuesForSection(...))`.
- Modify: `frontend/src/mocks/mockServer.js`, `frontend/src/mocks/synthetic-report.json` (spec 5.3).

**Interfaces:**
- **Consumes:** the report JSON fields `report_id`, `issues[].id`, `acceptable`, `accepted`,
  `can_export`, and the route from Task 2.
- **Produces, for Task 4:**
  - `ChecksView` props `onAcceptance(ids: string[], accepted: boolean): Promise<void>`,
    `acceptanceBusy: boolean` and `onWorkbookClosed()`;
  - `openIssues` from `lib/report.js`.
- **`onAcceptance` in Workspace:**
  - sets busy;
  - calls `setIssueAcceptance(report.report_id, ids, accepted)`;
  - on success, `replaceReport(result)`;
  - on `ApiError` 404 or 409, calls `workbookClosed()`;
  - on 400, rethrows the message for `ChecksView` to show;
  - always clears busy.
- **Mock server:**
  - `state.reportId` is a new random hex on every `mockUpload`;
  - `state.accepted` is a `Set`, cleared in `clearReport`/`mockUpload`;
  - `currentReport()` numbers ids "1".. after the variant, sets `acceptable` (warning → true;
    error → code in the spec 3.1 list; info → false), applies `accepted`, and recomputes
    `can_export` and `errorCount` from open errors;
  - the route has the same validation, order and messages as Task 2;
  - new variant: a name containing `value-error` gives `withValueErrors(report)`, which adds a
    blank Failure Effect (`REQUIRED_VALUE_BLANK` on the 901 tab, row 5, cell C5), New Task
    "Done" (`NEW_TASK_INVALID`, row 6, S6) and `STATION_BLANK` (with `report.station = ""`);
  - the variant check order is `no-tabs`, then `value-error`, then `error`, then `ok`;
  - the "errors" variant gains one acceptable `REQUIRED_VALUE_BLANK` next to its structural
    `ANALYSIS_HEADER_MISSING`.
- **Mock JSON:** `synthetic-report.json` gains `"report_id": "0000000000000000"` only.
  Validate with the `Report.model_validate` command (`python -c "import json; from backend.report.models import Report; Report.model_validate(json.load(open('frontend/src/mocks/synthetic-report.json', encoding='utf-8')))"`).

- [ ] **Step 1: Baseline build** (scratch outDir) succeeds.
- [ ] **Step 2: Implement** the data layer, client, Workspace, StepNav, markers and mock.
- [ ] **Step 3: Build** succeeds; the mock JSON validates.
- [ ] **Step 4: Browser check (mock).** Run `preview_start` with `{name: "fmea-frontend-mock"}`
  and upload `SYNTHETIC-value-error.xlsx`. In the page, call the mock route through the app's own
  client module or `fetch('/api/report/issues/acceptance', …)` (testing only) to accept all
  errors, then trigger a re-render by navigating. Expected:
  - the top bar shows "Ready to export";
  - Next is enabled;
  - the sidebar no longer says "Blocked".

  Stop the preview server.
- [ ] **Step 5: Commit.** `git commit -m "Frontend: count open issues, acceptance call and mock support"`

---

### Task 4: Data Checks UI, table marks and blocked lists

**Files:**
- Modify: `frontend/src/views/ChecksView.jsx`:
  - groups (spec 5.1), including the collapsed "Accepted" group with its count;
  - item actions and "Accept all" with the exact copy;
  - the banner matrix;
  - focus rules;
  - busy handling;
  - the 400 alert;
  - items keyed by `issue.id`.
- Modify: `frontend/src/components/AnalysisTable.jsx`. A row whose issues are all accepted gets
  the grey "Accepted" mark and the tooltip `Accepted: <message>`.
- Modify: `frontend/src/views/PreviewView.jsx` and `frontend/src/views/ExportView.jsx`. The
  blocked lists use open errors, and "or accept them on Data Checks" is shown only when an open
  error is acceptable.
- Modify: `frontend/src/styles/views.css` (or the existing checks stylesheet) for the
  Accept/Undo buttons, the muted note and the grey mark.

**Interfaces:**
- **Consumes (Task 3):** `onAcceptance`, `acceptanceBusy`, `onWorkbookClosed` and `openIssues`.
- **Exact copy (spec 5.1):**
  - **Buttons:** "Accept" (accessible name `Accept: ${message.slice(0, 80)}`), "Accept all",
    "Undo".
  - **Note on unacceptable errors:** "Fix this in the workbook".
  - **Group title:** "Accepted".
  - **Note line:** "Accepted values go into the PDF exactly as they are in the workbook."
  - **Banner titles and bodies:**
    - "Export blocked · N errors left", with the body "Fix them in the workbook, or accept the
      ones with an Accept button." when any open error is acceptable, else the existing body;
    - "Ready to export · M accepted", with the body "Accepted values go into the PDF exactly as
      they are in the workbook.";
    - the existing warnings title + " · M accepted" when warnings remain open.
  - **Blocked-list hint:** "or accept them on Data Checks".

- [ ] **Step 1: Implement** the copy, states, focus moves and marks above.
- [ ] **Step 2: Build** (scratch outDir) succeeds, and
  `grep -rn "issue.code}-\${index}" frontend/src/views/ChecksView.jsx` returns nothing.
- [ ] **Step 3: Browser check (mock):**
  - **"value-error" variant:**
    - Accept one → it moves to Accepted and focus goes to the next Accept;
    - Accept all → banner "Ready to export · 3 accepted" and the note line shows;
    - Undo one → "Export blocked · 1 error left", Next disabled with "Fix 1 error to preview";
    - accept it again → Preview shows the mock PDF.
  - **While a request runs:** every Accept, Accept all and Undo button is disabled (check the
    `disabled` attribute right after clicking).
  - **"errors" variant:** the structural item shows "Fix this in the workbook" and no button.
    After accepting the value error, the banner body is the existing "Fix them in Excel…" text,
    not the accept hint.
  - **Analysis tab:** a row with an accepted issue shows the grey mark, with the tooltip
    "Accepted: …".
  - **Console:** no errors. Stop the server.
- [ ] **Step 4: Commit.** `git commit -m "Data Checks: Accept, Accept all, Undo and the Accepted group"`

---

### Task 5: Contract and README

**Files:**
- Modify: `docs/CONTRACT.md`, the sections listed in spec 6:
  - 3.4 (invalid date text) and 3.6 (`ANALYSIS_SHEET_NONE` condition);
  - 3.10 and the 3.12 "Acceptable" column;
  - 4 (endpoint and `error_count`) and 4.1 (the acceptance 404/409 path);
  - 6 (Data Checks, TopBar/StepNav lines, AnalysisTable marks);
  - a Change log entry dated 2026-11-07.
- Modify: `README.md`, the "Checks and messages" section: what Accept does, which errors can be
  accepted, that accepted values go into the PDF as written, and that it lasts for this upload
  only.

- [ ] **Step 1: Edit** both files. Quote the code's exact messages.
- [ ] **Step 2: Check consistency.** Every code in `ACCEPTABLE_ERROR_CODES` is marked acceptable
  in 3.12. Every message in `AcceptanceError` appears in CONTRACT 4. Python forbidden-term scan:
  no hits.
- [ ] **Step 3: Commit.** `git commit -m "Contract and README: accepting issues"`

---

### Task 6: Final verification and dist

- [ ] **Step 1: Run the full suite.** `python -m pytest -q -p no:cacheprovider` → all pass.
  Then run the Python 3.11 `ast` check over `backend/` and `tools/` → ok.
- [ ] **Step 2: Scan for forbidden terms** (Python) over `git diff --name-only main...` (existing
  files only) → no hits.
- [ ] **Step 3: Rebuild `frontend/dist`** with
  `node -e "import('vite').then(v => v.build()).then(() => process.exit(0))"`. Commit
  "Rebuild frontend/dist".
- [ ] **Step 4: Browser pass on the branch app.**
  - **Setup:** add a temporary `.claude/launch.json` entry on port 8010 (same as before, removed
    afterwards; never commit it). Build a SYNTHETIC workbook from `make_clean_workbook` with a
    blank KKS (601 R3) and New Task "Done" (602 S3). Serve it once for upload through a temporary
    copy in `frontend/dist`, deleted right after (as in the last release).
  - **Expected:**
    - 2 errors with Accept buttons;
    - Accept all → "Ready to export · 2 accepted";
    - Preview loads the PDF (`/api/report/pdf?download=0` returns 200);
    - Export offers the download.
  - **Clean up:** stop the server and remove the temporary entry and file.
- [ ] **Step 5: Whole-branch review** on the most capable model, then report. Do not push or merge.
