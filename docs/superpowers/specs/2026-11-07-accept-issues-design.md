# Accept issues — design

**Date:** 2026-11-07. **Status:** approved in chat ("Approved & Proceed"); this file awaits review.
**Branch:** `feature/accept-issues`.

All examples are SYNTHETIC: IDs 901, 902 and invented titles.

## 1. Why

Data Checks lists errors that block Preview and Export until the workbook is fixed and uploaded
again. Some errors are only a blank or odd value, for example a blank KKS or "Done" in New Task.
Engineers sometimes want the report to go out with the data exactly as written, without editing
the workbook.

## 2. Decisions

The user chose these in chat:

| Topic | Decision |
|---|---|
| Which errors can be accepted | **Value errors only**: a blank or wrong value. Structural errors stay blocking, because there is nothing usable to put in the report. |
| PDF | **Looks normal.** No list of accepted issues and no marks. |
| How to accept | **Per item, plus "Accept all"** for each group. Accepted items move to an **Accepted** group, each with **Undo**. |
| Warnings | Accept **marks them as checked**. |

These were also part of the approved design:

- **Data as written.** An accepted value goes into the report as written in the workbook. Counts
  follow the rules that already exist (3.4).
- **Who decides.** The server keeps the accepted state for the session and decides whether
  preview, download and email are allowed. Every screen and the PDF endpoints agree.
- **Lifetime.** Acceptance lasts for this upload only. A new upload, signing out or closing the
  page clears it (one-time use).
- **Show in table.** It still works on accepted items.

Points that came out of the spec review are marked **(9a–9e)** and listed in section 9 for
confirmation.

## 3. Rules

### 3.1 Which issues can be accepted

| Severity | Codes | Accept? |
|---|---|---|
| error, **value** | `REQUIRED_VALUE_BLANK`, `NEW_TASK_INVALID`, `UOIR_VALUE_BLANK`, `STATION_BLANK`, `ANALYSIS_DATE_BLANK`, `ANALYSIS_DATE_INVALID` | **Yes** (with one exception, below) |
| error, **structural** | `SHEET_MISSING`, `TEAM_HEADER_MISSING`, `UOIR_HEADER_MISSING`, `UOIR_NONE`, `ANALYSIS_SHEET_NONE`, `ANALYSIS_HEADER_MISSING`, `ANALYSIS_HEADER_DUPLICATE`, `ANALYSIS_NO_ROWS` | No |
| warning | all | **Yes** (marks it as checked) |
| info | all | No |

- **Where the list lives.** The list of value-error codes is one constant,
  `ACCEPTABLE_ERROR_CODES` in `backend/config/mapping.py`.
- **New error codes.** An error code added later is not acceptable until it is added to that list.
- **Exception (9b).** Sometimes every `ANALYSIS_REQUIRED_VALUES` cell of one analysis row is blank,
  for example a second header row, or a row holding only a Frequency. Then that row's
  `REQUIRED_VALUE_BLANK` issues are **not acceptable**: it is not a row with a missing value, it
  is not an analysis row at all. The builder decides this per row.

### 3.2 Export rule

```
can_export = no issue with severity "error" and accepted == False
```

- **One helper.** The rule lives in `backend/report/models.py` as `export_allowed(issues)`, next
  to `open_error_count(issues)` (errors with `accepted == False`). The builder, the session store
  and the API's 409 `error_count` all use them.
- **Before any Accept.** Nothing is accepted, so `can_export` is exactly what it is today.
- **Who checks the rule.** The server applies it in `GET /api/report/pdf` (preview and download)
  and `POST /api/report/email`, as today. The screens read `report.can_export`.

### 3.3 Lifetime

- **New upload.** Acceptance belongs to one built report. A new upload builds a new report with a
  new `report_id`, in which nothing is accepted.
- **Signing out, closing the page or idle timeout.** These discard the report and its acceptance,
  as today.
- **Stale requests.** A request that names another report is refused (4.2).

### 3.4 What the report shows for accepted values

| Accepted error | In the report (existing rules unless marked) |
|---|---|
| `REQUIRED_VALUE_BLANK` | The cell is blank in the FMEA Analysis table and wherever that value shows.<br>• blank Strategy → "Not specified" row and slice<br>• blank Trade → "Trade not specified"<br>• blank KKS → those rows form their own Recommendation group, headed by the Equipment alone (or "KKS not specified" when there is no Equipment either; 3.9) |
| `NEW_TASK_INVALID` | The value shows as written ("Done") in the table. The row is left out of the Existing/New and Work-Centre counts, and is listed in the "Not counted" note ("New Task is not Yes or No"). Exception: NSM rows are never listed in that note (3.8). |
| `UOIR_VALUE_BLANK` | **Blank Title:** the Failure Details cell is blank. Section headings use the existing fallback: another row's Title for the same ID, then B1, then the tab name.<br>**Blank UOIR ID:** that row shows in Failure Details with a blank ID, but it is not a UOIR. So a tab that names the ID it should have had becomes an unlisted tab (warning, included, placed last), and its Recommendation headings lose that UOIR's Equipment. |
| `STATION_BLANK` | The cover and the running header show the station blank. The file name uses `Station`. |
| `ANALYSIS_DATE_BLANK` | The cover shows the date blank. The file name uses `undated`. |
| `ANALYSIS_DATE_INVALID` | **(9a) Changed:** the cover shows the date **as typed** (e.g. "TBC June 2026"), and so do the app's Date of Analysis fact and the email subject and intro. The file name uses `undated`. Today the typed text is thrown away and the date shows blank. |

Two parser changes, and nothing else in the parser, counts or PDF:

- **Invalid date text (9a).** When B3 holds text that is not a date, `analysis_date_text` keeps
  that text (trimmed). `analysis_date` stays None.
- **No analysis tabs (9e).** `ANALYSIS_SHEET_NONE` is raised whenever the UOIR sheet's header was
  found and the workbook has no analysis tab, even if every UOIR ID is blank. Today it is skipped
  when no UOIR ID was read. Without this, accepting the blank IDs would let a report with no
  analysis at all be exported.

## 4. Data and API

### 4.1 Model (`backend/report/models.py`)

```python
class Issue(BaseModel):
    ...                                  # existing fields unchanged
    id: str = ""                         # NEW: "1", "2", … in report order (after sorting)
    acceptable: bool = False             # NEW: 3.1
    accepted: bool = False               # NEW: changed only through the API (4.2)


class Report(BaseModel):
    ...
    report_id: str = ""                  # NEW: random hex token per built report
    can_export: bool                     # 3.2


def export_allowed(issues: list[Issue]) -> bool: ...
def open_error_count(issues: list[Issue]) -> int: ...
```

**`finalise_report(report) -> Report`** (in `backend/report/models.py` or a small
`backend/report/issues.py`) returns a copy with:
- `report_id = secrets.token_hex(8)`;
- each issue's `id` = its position in the final sorted list, from "1";
- `acceptable` per 3.1 (the per-row exception needs builder knowledge, so the builder marks those
  issues before calling it);
- `can_export = export_allowed(issues)`.

The builder calls it last. The API test helper (`backend/tests/test_api_support.py`,
`make_report` / `FakeServices`) calls it too, so API tests get real ids and a real `report_id`.

### 4.2 New endpoint

`POST /api/report/issues/acceptance` (signed in).

The body is a pydantic model, `AcceptanceRequest(report_id: str, ids: list[str], accepted: bool)`,
like `EmailRequest`. It is never read with `request.json()`, so a `text/plain` body gets 422 and
the existing Origin check applies.

```json
{ "report_id": "<from the report>", "ids": ["3", "7"], "accepted": true }
```

**Success:** **200**. The response is the updated report JSON (same shape as `GET /api/report`).
`accepted: false` undoes.
- **Idempotent:** accepting an accepted item, or undoing one that is not accepted, changes nothing.
- **Duplicate ids** count once.

**Errors.** Checked in this order; the first that applies wins, and nothing changes. All are
plain-language `{"detail": ...}`.

| # | Status | When | Message |
|---|---|---|---|
| 1 | 404 | No report | "No workbook uploaded yet." (existing `MSG_NO_REPORT`) |
| 2 | 409 | `report_id` is empty or not the current report | "This workbook is no longer open here. Upload it again." |
| 3 | 400 | `ids` is empty | "Choose at least one item." |
| 4 | 400 | More ids than the report has issues | "Too many items in one request." |
| 5 | 400 | An id is unknown | "Some of these items are no longer in the report. Upload the workbook again." |
| 6 | 400 | An id is not acceptable (3.1), in either direction | "This item can't be accepted. Fix it in the workbook and upload again." |

**Session store.** `SessionStore.update_issue_acceptance(session, report_id, ids, accepted) -> Report`
is **copy-on-write** and runs under the store lock:
1. Check that a report exists.
2. Check `report_id`.
3. Validate every id.
4. Build `report.model_copy(update={"issues": [...updated copies...], "can_export": export_allowed(...)})`.
5. Assign it to `session.report` and return it.

The route serialises the **returned** object. The method never edits the stored report in place.

**PDF cache.** The method does not bump `report_version` and does not drop the cached PDF, because
the PDF content does not depend on acceptance. `_pdf_for_session` checks `can_export` before using
the cache, as today, so an Undo blocks the PDF again at once.

**Blocked-export responses.** `_error_count` in the 409 responses of the PDF and email endpoints
becomes `open_error_count`.

## 5. Screens

### 5.1 Data Checks (`ChecksView`)

**Groups, in order:**

| Group | Contents |
|---|---|
| "Must fix before export" | Errors not yet accepted |
| "Please check" | Warnings not yet accepted |
| "For information" | Info notes (unchanged, collapsed) |
| **"Accepted"** | Accepted errors and warnings, in report order, collapsed by default and showing its count |

**Item actions:**
- **Acceptable, not accepted.** The item has an **Accept** button. Its accessible name is
  "Accept: " followed by the start of the message.
- **Error that can't be accepted.** The item shows the muted note "Fix this in the workbook"
  instead of a button.
- **Accepted.** The item has an **Undo** button.
- **Show in table.** It stays on every item that has a table target.
- **React keys.** Items are keyed by `issue.id`.

**Group actions:**
- "Must fix before export" has **Accept all**, which accepts every acceptable error in the group.
  It is hidden when none is acceptable.
- "Please check" has **Accept all**.

**On-screen note (9d).** The Accepted group, and the area under the error group when it has an
Accept button, say: "Accepted values go into the PDF exactly as they are in the workbook."

**Banner.** "N accepted" counts accepted errors plus accepted warnings.

| State | Title | Body |
|---|---|---|
| Open errors, at least one acceptable | "Export blocked · N errors left" | "Fix them in the workbook, or accept the ones with an Accept button." |
| Open errors, none acceptable | "Export blocked · N errors left" | the existing "Fix them in Excel…" text |
| No open errors; open warnings; some accepted | existing "N items worth checking" title + " · M accepted" | existing warning body |
| No open errors; open warnings; none accepted | existing (unchanged) | existing |
| No open errors or warnings; some accepted | "Ready to export · M accepted" | "Accepted values go into the PDF exactly as they are in the workbook." |
| No open errors or warnings; none accepted | existing (unchanged) | existing |

**While a request runs, and after it:**
- **Disabled buttons.** Every Accept, Accept all and Undo button is disabled while any acceptance
  request runs, so only one request is in flight.
- **Success.** The returned report is applied with a new `replaceReport(next)` in `Workspace`.
  It only calls `setReport`, and only when `next.report_id === report.report_id`. It does not
  reset the page, section, tabs, focus or scroll (`applyReport` does).
- **404 or 409.** These call `onWorkbookClosed` (the existing "Workbook closed" notice, back to
  Upload), as Preview and Export do. `ChecksView` gets an `onWorkbookClosed` prop.
- **400.** The message shows in an alert, and nothing changes.

**Focus after an action:**
- after Accept, it moves to the next item's Accept button in the same group, else to that group's
  heading, else to the Accepted toggle;
- after Undo, it moves to the next item in Accepted, else to the Accepted toggle.

### 5.2 Everywhere else

**Workspace counts.** `Workspace` computes `counts = countIssues(openIssues(report.issues))`, with
`openIssues` in `lib/report.js` filtering out accepted issues. Every `counts` consumer follows
automatically:
- the Review Next button ("Fix N errors to preview"), which now also gates on `report.can_export`;
- the top-bar chips ("N errors" / "Ready to export");
- the Data Checks sidebar badge;
- the sidebar step detail ("Blocked by N errors");
- Preview's Next reason;
- Export's warnings alert;
- the Upload card's "n errors".

**Section counts and markers.** The sidebar and selector cards, and `SectionHeading`, use
`openIssues`.

**Analysis table (9c).** A row whose issues are all accepted shows a neutral grey **"Accepted"**
mark instead of the red or amber one. Its tooltip is "Accepted: <message>". So "Show in table" on
an accepted item lands on a row that explains itself. Rows with open issues keep today's marks.

**Blocked lists.** The Preview and Export blocked lists show open errors only. They say "or accept
them on Data Checks" only when at least one open error is acceptable.

### 5.3 Mock server

- **State.** The mock keeps `report_id` (new on every upload) and a set of accepted ids in its
  `state`, cleared on upload and discard.
- **`currentReport()`.** After building a variant it numbers the issue ids "1".., sets
  `acceptable` by severity and code (3.1), applies the accepted set, and recomputes `can_export`
  and the error count from open errors.
- **Endpoint.** The mock implements `POST /api/report/issues/acceptance` with the same validation
  and messages as 4.2.
- **New variant.** A file name containing **"value-error"** gives a report whose only errors are
  acceptable: a blank Failure Effect, New Task "Done" and a blank Station. This is the variant
  that can be unblocked. The "errors" variant keeps its structural `ANALYSIS_HEADER_MISSING`, plus
  an acceptable error, to show both item states.
- **JSON.** `synthetic-report.json` gains `report_id` only; the issue fields are derived.

## 6. Docs and tests

### Docs

**`docs/CONTRACT.md`:**
- 3.4 (invalid date text)
- 3.6 (`ANALYSIS_SHEET_NONE` condition)
- 3.10 (`can_export`)
- 3.12 (an "Acceptable" column)
- 4 (the new endpoint and the `error_count` change)
- 4.1 (the acceptance 404/409 path)
- 6 (Data Checks, the TopBar and StepNav lines, AnalysisTable marks)
- a Change log entry

**`README.md`:** the "Checks and messages" section explains Accept, which errors can be accepted,
and that accepted values go into the PDF as written.

### Tests

**Parser:**
- ids are "1".."n" in order;
- `acceptable` is set for every code group in 3.1;
- an all-blank row's `REQUIRED_VALUE_BLANK` issues are not acceptable;
- `report_id` is set and differs between two builds;
- `can_export` is unchanged when nothing is accepted;
- an invalid date keeps its typed text in `analysis_date_text`, and the file name is `undated`;
- every UOIR ID blank and no tabs → `ANALYSIS_SHEET_NONE` raised.

**API** (`test_api_report.py`, `test_api_support.py` updated):
- accept a value error → `can_export` true and the PDF returns 200;
- Accept all for several errors;
- undo → the PDF returns 409 again, and `error_count` counts only errors not accepted;
- a structural error → 400, nothing changed;
- an unknown id → 400;
- an empty or stale `report_id` → 409;
- an empty `ids` list → 400;
- duplicate ids are fine;
- undo on a structural id → 400;
- a warning accepted → `accepted` true and `can_export` unchanged;
- info → 400;
- a new upload resets acceptance;
- the PDF cache is kept across acceptance changes;
- email endpoint gate;
- `text/plain` body → 422;
- the route is in `test_api_local_only`'s refused-origin test;
- all IDs blank + no tabs stays blocked after accepting every acceptable error.

**Browser:**
- **Mock server, "value-error" variant:** accept one, Accept all, Undo, banner states, top-bar
  chips, the Next button, Preview unblocked.
- **Mock server, "errors" variant:** the "Fix this in the workbook" note.
- **Branch app with a SYNTHETIC workbook** (one blank KKS, one "Done" New Task): accept both,
  Preview shows the PDF, and Export downloads it.

## 7. Out of scope

- A list of accepted issues in the PDF.
- Remembering acceptance across uploads.
- Accepting structural errors or info notes.
- An "Undo all" button.

## 8. Unchanged

- The parser, apart from 3.4's two changes.
- The counts, recommendations and PDF layout.
- One-time use (nothing saved).
- The Outlook draft flow, apart from the shared export gate.

## 9. Points to confirm in review

These were not discussed in chat. Each one is built as written unless you say otherwise.

- **a. An invalid date shows as typed.** For example "TBC June 2026" on the cover, and in the
  email subject and the app's Date of Analysis fact. Today it shows blank. The file name still
  says `undated`.
- **b. A row with every required cell blank can't be accepted.** For example a stray second
  header row. It isn't a row with a missing value, and accepting it would add an empty failure
  mode to every count.
- **c. Rows with accepted issues get a grey "Accepted" mark** in the analysis table, instead of
  red or amber.
- **d. A one-line note on Data Checks:** "Accepted values go into the PDF exactly as they are in
  the workbook."
- **e. A workbook whose UOIR IDs are all blank and that has no analysis tabs stays blocked.** It
  would otherwise export with no analysis at all once the blanks were accepted.
