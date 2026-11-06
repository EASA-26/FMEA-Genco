# Analysis per tab — design

Date: 2026-11-06 · Status: approved in chat ("Approved & Proceed"); this file awaits review ·
Branch: `feature/analysis-per-tab`

All examples are SYNTHETIC: IDs 901, 902, 903 and 999, and invented titles. Nothing here comes
from an engineer workbook.

## 1. Why

Today every distinct UOIR ID on the UOIR sheet must have its own analysis tab, named
`UOIR ID <id> - <title>`. A tab name holds one ID, and a UOIR with no tab is the blocking error
`ANALYSIS_SHEET_MISSING`.

Engineers often analyse several UOIRs in one tab when they are about the same topic. So the UOIR
sheet can list more UOIRs than there are tabs, for example 7 UOIR rows and 3 tabs. Such a workbook
cannot be exported today.

## 2. Decisions

The user chose these in chat:

| Topic | Decision |
|---|---|
| Failure Details (Review Data) and the Introduction page | Still one row per UOIR sheet row. Unchanged. |
| FMEA Analysis and FMEA Summary | One section per analysis **tab**, not per UOIR ID. |
| Which UOIRs a tab covers | Every UOIR ID named in the tab name: `UOIR ID 901 902 - SYNTHETIC Pump trip` covers 901 and 902. |
| UOIR on the UOIR sheet that no tab names | **Info** note only. Does not block preview or export. |
| Heading of a tab covering several UOIRs | `UOIR ID : 901, 902` and `Title : <cell B1 of the tab>`. If B1 is empty, the UOIR sheet Title. |
| Tab whose ID is not on the UOIR sheet | **Included** in the report, with a warning. |

These were part of the design the user approved in chat:

- Recommendation follows Analysis: one section per tab.
- The Recommendation group headings combine the Equipment of every UOIR the tab covers (3.4).
- The "UOIRs" figures count distinct UOIR IDs on the UOIR sheet. The "Analysis" figures count tabs.
- Sections follow the UOIR sheet order (3.5).
- One UOIR ID named in two tabs: both tabs are used, with a warning.
- The check on the title part of a tab name warns only when it matches neither B1 nor any covered
  UOIR's Title.
- The B1 cross-check is skipped for tabs that cover several UOIRs.
- Issues inside a tab show all the tab's IDs.
- UOIR sheet problems show in Data Checks only.

New points that came out of the spec review are listed in section 9 for confirmation.

## 3. Rules

**Terms used in this section:**

- **Listed ID:** a UOIR ID that is on the UOIR sheet.
- **Single-UOIR tab:** a tab whose name gives exactly one ID, and that ID is listed.

### 3.1 Which tabs are analysis tabs, and which are read

- **Which sheets are analysis tabs:** unchanged. A worksheet whose name matches
  `ANALYSIS_SHEET_PATTERN` is an analysis tab: `UOIR`, optional spaces, `ID`, optional spaces,
  optional `:`, `#` or `-`, then digits, then the rest of the name. `Notifications` and `Sheet3`
  are still ignored.
- **One section per tab:** every analysis tab becomes one analysis section, even when none of its
  IDs is listed.
- **What is read (change):** today only the linked tabs are read. From now on **every analysis tab
  is read and checked**, including hidden tabs, tabs with an unlisted ID and tabs that share an ID.
  - An error inside any of them blocks export, as an error in any tab does (see 9b).
  - A tab that cannot be read at all fails the upload, as a linked tab does today.
- **Sorting sheets happens before the UOIR sheet is read:** at that point, recognising an analysis
  tab uses the pattern only. Reading the IDs in its name (3.2) needs the UOIR list, so it happens
  after the UOIR sheet has been read.

### 3.2 The UOIR IDs in a tab name

1. The **first number** after "UOIR ID" is always an ID, as today.
2. Right after it, a further number counts as an ID while all three of these hold:
   - It is separated from the previous ID by whitespace (including non-breaking spaces), a comma
     or `&`, in any mix: `901 902`, `901, 902`, `901,902`, `901 & 902`, `901, 902 & 903`.
   - It ends at the end of the name, at whitespace, or at one of `,` `&` `-` `:`. So `132kV` or
     `2x` is never an ID.
   - It **is a listed ID** (compared without leading zeros).
3. Scanning stops at the first number or word that does not qualify. The **title fragment** starts
   there. Leading separators (`-`, `:`, `,`, `&`, whitespace) are removed from the fragment.
4. An ID repeated in the same name counts once.
5. A `-` between IDs is not an ID separator, so `901-902` and `901 - 902` stop after 901.
6. If no UOIR row could be read (UOIR sheet missing, header not found, or no rows), only the first
   number counts.

| Tab name | Listed IDs | IDs | Fragment |
|---|---|---|---|
| `UOIR ID 901 902 - SYNTHETIC Pump trip` | 901, 902 | 901, 902 | `SYNTHETIC Pump trip` |
| `UOIR ID 901, 902 & 903 - Fan` | 901, 902, 903 | 901, 902, 903 | `Fan` |
| `UOIR ID 901,902,903` | 901, 902, 903 | 901, 902, 903 | (empty) |
| `UOIR ID 901\xa0902 - Fan` (non-breaking space) | 901, 902 | 901, 902 | `Fan` |
| `UOIR ID 905 2 fans trip` | 905 | 905 | `2 fans trip` |
| `UOIR ID 901 132kV breaker` | 901 | 901 | `132kV breaker` |
| `UOIR ID 901 - 902 - Pump` | 901, 902 | 901 | `902 - Pump` (see `UOIR_ID_NOT_READ`, 3.6) |
| `UOIR ID 999 902 - Valve` | 902 | 999, 902 | `Valve` |
| `UOIR ID 0901 902` | 901, 902 | 901, 902 | (empty) |

**How IDs are shown:** each ID is shown as written on the UOIR sheet (the first row with that ID,
as `uoir_id` is today). An unlisted ID is shown as written in the tab name.

**Known limits:**

- A title that starts with a number that is also a listed ID is read as an ID.
- Excel allows 31 characters in a tab name. `UOIR ID ` plus about 4 characters per three-digit ID
  leaves room for about 5 IDs with no title.
  - The compact form `UOIR ID 901,902,903` saves room.
  - A UOIR that does not fit in any tab name can only appear in Failure Details. It gets the
    `ANALYSIS_SHEET_MISSING` info note.

### 3.3 Title of a section

**Single-UOIR tab: as today.** The first non-blank of:

1. the UOIR sheet Title of that ID (the first non-blank Title, contract 3.5);
2. B1;
3. the fragment.

**Any other tab** (several IDs, or an unlisted ID). The first non-blank of:

1. cell `B1` (`ANALYSIS_TITLE_CELL`), unless B1 lies inside the analysis table (header on row 1;
   existing rule);
2. the first non-blank UOIR sheet Title among the tab's listed IDs, in tab-name order;
3. the fragment.

If all of these are blank, the title is "".

### 3.4 Equipment of a section

Equipment is used for the Recommendation group headings (`"<equipment>, <kks>"`; that rule is
unchanged).

- It is the Equipment values of every listed UOIR the tab covers, taken in UOIR sheet order, with
  each UOIR's own values in their existing order.
- Duplicates are removed by `text_key`. The values are joined with `" / "`.
- A tab with no listed ID has no equipment, so its group headings are the KKS alone.
- For a single-UOIR tab this is the same as today.

### 3.5 Order of sections

Sort the tabs by:

1. the earliest UOIR sheet position (first-appearance order of distinct IDs) of any listed ID the
   tab covers;
2. then workbook tab order.

Tabs with no listed ID come after all the others, in workbook tab order.

### 3.6 Checks

| Code | Severity | When | `sheet` / `uoir_id` | Message (SYNTHETIC example) |
|---|---|---|---|---|
| `ANALYSIS_SHEET_MISSING` | **info** (was error) | A listed ID is named by no tab. Not raised when `ANALYSIS_SHEET_NONE` is raised, nor for an ID that gets `UOIR_ID_NOT_READ`. | UOIR sheet, first row of that ID (UOIR ID cell) / that ID | "UOIR ID 903 is not named in any analysis tab, so it is only shown in Failure Details. If a tab covers it, add 903 to that tab's name and upload again." |
| `UOIR_ID_NOT_READ` | **warning (new, 9c)** | A listed ID that no tab names appears as a separate number elsewhere in a tab or sheet name. Either it is in the fragment of an analysis tab, or it is in the name of a sheet that starts with "UOIR" and gets `ANALYSIS_SHEET_NAME_UNREADABLE`. | UOIR sheet row of that ID / that ID | "UOIR ID 902 appears in the name of tab 'UOIR ID 901 - 902 - Pump', but it was not read as one of the tab's IDs. Write every ID right after 'UOIR ID', separated by spaces, commas or &, for example 'UOIR ID 901 902 - Pump', and upload again." |
| `ANALYSIS_SHEET_NAME_UNREADABLE` | **warning (new, 9c)** | A worksheet whose trimmed name starts with "UOIR" (any case) does not match the analysis tab pattern and is not the UOIR sheet. It replaces the info `SHEET_NOT_USED` for such sheets. | that sheet / none | "Sheet 'UOIR 901 - Fan' looks like an analysis tab, but its name does not start with 'UOIR ID' and a number, so it is not in the report. Rename it like 'UOIR ID 901 - Fan' and upload again." |
| `ANALYSIS_SHEET_UNLISTED` | warning (now **included**) | A tab names an ID that is not listed. Only the first ID can be unlisted (3.2). Skipped when no UOIR row was read. | the tab / the tab's IDs joined | "Tab 'UOIR ID 999 - SYNTHETIC Valve' is for UOIR ID 999, which is not in the UOIR list. It is included in the report. Add UOIR ID 999 to the UOIR sheet if it belongs there." |
| `UOIR_IN_SEVERAL_TABS` | **warning (new)** | A listed ID is named by two or more tabs. Not raised for unlisted IDs, because each such tab already gets `ANALYSIS_SHEET_UNLISTED`. | UOIR sheet row of that ID / that ID | "UOIR ID 902 is named in 2 tabs: 'UOIR ID 901 902 - SYNTHETIC Pump' and 'UOIR ID 902 - SYNTHETIC Pump'. Both are in the report. Check that this is intended." Tab names are listed in workbook order. |
| `ANALYSIS_SHEET_TITLE_MISMATCH` | warning | Raised while the tab is read, once it is known whether B1 counts as a title (3.3). The fragment is not empty and matches **none** of: B1 (when it counts), and the non-blank UOIR sheet Titles of the tab's listed IDs. The matching rule is unchanged (normalised fragment ⊆ normalised title). Skipped when there is nothing to compare with, or when no UOIR row was read. | the tab / the tab's IDs joined | It names only what was compared, joined with "or": "The name of tab 'UOIR ID 901 902 - Fan' does not match cell B1 ('SYNTHETIC Pump trip') or the Title of UOIR ID 901 ('…') or 902 ('…'). It is still used; check that it is the right tab." |
| `ANALYSIS_TITLE_CELL_MISMATCH` | warning | **Single-UOIR tabs only.** The condition and message are unchanged; the tab prints the UOIR sheet Title, as today. Skipped for every other tab. | unchanged | unchanged |
| `ANALYSIS_SHEET_HIDDEN` | warning | Unchanged: the tab is hidden and still included. | the tab / the tab's IDs joined | "Tab '…' (UOIR ID 901, 902) is hidden in Excel. It is included in the report." |
| `ANALYSIS_SHEET_NONE` | **error (new, 9a)** | The workbook has no analysis tab at all. Skipped when no UOIR row was read, because that error already blocks export. | none / none | "The workbook has no analysis tabs, so the report would have no FMEA Analysis. Add a tab named like 'UOIR ID 123 - Title of the UOIR' and upload again." (fixed text, same example as the Upload page) |

**Removed:**

- `ANALYSIS_SHEET_AMBIGUOUS` (error). Several tabs with one ID are now all used.
- The tie-break that picked one of several tabs by title and marked the others `SHEET_NOT_USED`.
  `SHEET_NOT_USED` (info) stays for other sheets that are not used.

**Locations:**

- **Issues raised inside a tab** carry `sheet` = the tab name and `uoir_id` = the tab's IDs joined
  with `", "` (`"901, 902"`, or `"901"` for a one-ID tab, as today). This covers every
  table-reading issue, plus `ANALYSIS_SHEET_UNLISTED`, `ANALYSIS_SHEET_HIDDEN`,
  `ANALYSIS_SHEET_TITLE_MISMATCH` and `ANALYSIS_TITLE_CELL_MISMATCH`.
- **UOIR sheet issues** (`UOIR_*`, `ROWS_AFTER_BLANK_ROW` on the UOIR sheet,
  `ANALYSIS_SHEET_MISSING`, `UOIR_ID_NOT_READ`, `UOIR_IN_SEVERAL_TABS`) keep `sheet` = the UOIR
  sheet and a single ID.
- **In the app**, a section is found by `sheet`, never by `uoir_id`.

**Order:** the issue sort is unchanged. On one tab, `ANALYSIS_SHEET_UNLISTED` and
`ANALYSIS_SHEET_HIDDEN` are raised when the tab list is built, which is before the tab is read. So
among issues with the same severity and no row, they come before `ANALYSIS_SHEET_TITLE_MISMATCH`,
which is raised while reading.

**Reworded:**

- `ROWS_AFTER_BLANK_ROW` on the UOIR sheet: "…so it is not in Failure Details. Remove the empty rows
  in between and upload again." Its analysis tab, if any, is now included as an unlisted tab.

### 3.7 Unchanged

- **Reading one tab** works per tab exactly as before: header row, table extent, merges, notes,
  task records, duplicates and every row-level check.
- **Counts and grouping:** the summary counts (contract 3.8) and the recommendation grouping (3.9)
  work on one tab's task records. Counts, titles and equipment for a single-UOIR tab do not change.
- **UOIR sheet rules** (3.5), including `UOIR_DUPLICATE_ID_CONFLICT`, and the Introduction.

## 4. Report data and code structure (approach: replace the per-UOIR list)

**Why this approach.** It was chosen over two alternatives:

- **A per-tab list beside the per-UOIR list:** the two lists would have to stay in step, and the
  per-UOIR one mostly repeats `failure_details`.
- **Keeping the key `uoirs` with tab items:** fewer renames, but the key would be misleading from
  then on.

**`backend/report/models.py`:**

```python
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
    ...
    failure_details: list[FailureDetail]          # unchanged
    uoir_ids: list[str]                           # NEW: see below
    analyses: list[AnalysisSection]               # NEW: replaces `uoirs`, ordered by 3.5
    ...
```

- **`Report.uoir_ids`:** the distinct UOIR IDs on the UOIR sheet. They are distinct by
  `uoir_id_key` (leading zeros ignored), blank IDs are excluded, they are in first-appearance
  order, and each is shown as its first row's text. This is the same set as today's sections.
- **Removed:** `UoirSection` and `Report.uoirs`. The JSON the browser receives changes the same way.
- **Nothing to migrate:** the session store keeps `Report` objects in memory only.

**Build order** (`backend/report/builder.py`):

1. Sort the sheets. An analysis tab is recognised by the pattern only.
2. Read Team Member and the UOIR sheet. The UOIR records are kept by `uoir_id_key` (ID text, Title,
   Equipment, first row), as today's `_Section` without the analysis fields.
3. Parse every analysis tab's name with the listed keys (3.2). Raise `ANALYSIS_SHEET_UNLISTED`,
   `ANALYSIS_SHEET_HIDDEN` and `ANALYSIS_SHEET_NAME_UNREADABLE`, then the coverage checks:
   `ANALYSIS_SHEET_NONE`, `UOIR_IN_SEVERAL_TABS`, `UOIR_ID_NOT_READ` and `ANALYSIS_SHEET_MISSING`.
4. Read each tab once. Build its `AnalysisSection`: title (3.3), equipment (3.4), then table,
   notes, tasks, summary and recommendations as today. Raise the two title checks here. Stamp every
   tab issue with the joined IDs.
5. Sort the sections (3.5).

**`backend/excel/linking.py`** becomes pure helpers with no workbook access:

- `parse_analysis_tab_name(name, listed_keys=frozenset())` returns the IDs and the fragment, or
  None;
- building the tab list and its tab-level checks;
- the coverage checks;
- a fragment-mismatch helper and `check_title_cell`.

`expected_tab_name` is no longer used by any message, so it and its test are removed.

## 5. PDF

- **Cover and Introduction:** unchanged. Failure Details prints one row per UOIR sheet row.
- **Analysis:** for each section in order, one A3 "Analysis: FMEA Analysis" page and one A4
  "Analysis: FMEA Summary" page.
  - Both are headed `UOIR ID : 901, 902` and `Title : <title>`. The label stays "UOIR ID".
  - The Analysis page adds the `Note` rows as today.
  - Empty states:
    - "No analysis table was read from this tab." (header not found; export is blocked then
      anyway)
    - "No summary is available for this tab."
- **Recommendation:** one heading per section, "UOIR ID 901, 902: <title>", then the groups as
  today.
  - Empty states:
    - "No recommendations for this tab."
    - "No analysis tabs were found in the workbook."
  - The second empty state is blocked from export by `ANALYSIS_SHEET_NONE`.

## 6. App screens

**Data and keys**
- **Selection:** the selected section is keyed by `sheet_name`, not a UOIR ID. This applies in
  Workspace and WorkbookData and to the "Show in table" focus.
- **React keys:** use `sheet_name`.
- **DOM `id`s and `aria-labelledby`:** use the section index, because tab names and joined IDs
  contain spaces. Today `SummaryPanel` uses `evr-${uoir_id}` and `wc-${uoir_id}`.
- **Error boundary:** the `resetKey` uses `sheet_name`.

**Lists and headings**
- **Section lists:** the sidebar Analysis items, the section cards on Analysis and Recommendation,
  and the Analysis tab under Workbook data all show one entry per section. Each entry shows all
  its IDs (`901, 902`) and its title.
- **Tab name:** shown only as a tooltip on the entry, so two tabs that name the same ID can be told
  apart. No sheet captions are added to the screens.
- **Entry markers:** the error or warning marker on an entry comes from issues whose `sheet` is that
  tab.
- **Headings and labels:** they read "UOIR ID 901, 902", for example the table label "FMEA Analysis
  table for UOIR ID 901, 902". The selector label becomes "Choose an analysis tab".

**Counts**
- **"UOIRs"** (Data Checks fact card, sidebar step detail, upload card): `report.uoir_ids.length`.
- **Workbook data "Analysis" tab:** `report.analyses.length`.
- **Export "PDF contents" card:**
  - "3 analysis tabs (7 UOIRs): FMEA Analysis on A3 landscape and FMEA Summary on A4"
  - "Tasks grouped by Equipment and KKS for every analysis tab"

**Issues and "Show in table"**
- **UOIR sheet problems** show in Data Checks only. They no longer mark an analysis entry.
- **"Show in table"** finds the section whose `sheet_name` equals the issue's `sheet`.

**Texts**
- **Upload page, "What the workbook needs":**
  - The analysis tab line is titled "Analysis tabs named by UOIR ID".
  - It reads: "Named like 'UOIR ID 123 - Title of the UOIR'. A tab that covers several UOIRs lists
    every ID after 'UOIR ID', separated by spaces, commas or &: 'UOIR ID 123 124 - Title' or 'UOIR
    ID 123,124,125'. Excel allows 31 characters, so shorten the title part if needed."
- **Empty states:**
  - No sections: "No analysis tabs were found in the workbook. See Data checks."
  - A section whose table could not be read: "The analysis table could not be read from this tab.
    See Data checks."
  - "No analysis tab linked" in the heading can no longer happen and is removed.
- **"UOIR" wording:** texts that say "this UOIR" or "every UOIR" about analysis or recommendations
  say "this tab" or "every analysis tab" instead. This covers RecommendationView, SummaryPanel,
  ExportView, the page subtitles and the ErrorBoundary text.

**Mocks and build**
- **Mocks:** the mock server and `synthetic-report.json` follow the new JSON, including one two-ID
  section. The mock "errors" variant gets an analysis section with `analysis` null (and a
  `sheet_name`) plus `ANALYSIS_HEADER_MISSING`, instead of relying on `ANALYSIS_SHEET_MISSING`
  being an error.
- **Build:** `frontend/dist` is rebuilt with the build command in the project notes, not
  `npm run build`.

## 7. Docs and tests

**`docs/CONTRACT.md`**
- Section 1: layout lines for linking.py and summary.py.
- 3.1: which sheets are read.
- 3.3.
- 3.5: last bullets and the `ROWS_AFTER_BLANK_ROW` text.
- 3.6: rewritten.
- 3.8 and 3.9: "per UOIR" becomes "per tab".
- 3.10.
- 3.12: issue catalogue.
- Section 5 (PDF).
- Section 6 (frontend, including the accessibility labels).
- Section 7: remove the tie-break row and reword the `ROWS_AFTER_BLANK_ROW` row.
- Change log entry.

**`README.md`**
- The page subtitle table.
- The PDF page table and the PDF order ("for each UOIR").
- The workbook rules table: tab naming, and B1 as the title of a multi-UOIR tab.
- "Linking analysis tabs to UOIRs".
- "All counts are per UOIR".
- "One block per UOIR".
- The "Checks and messages" tables.

**Test workbooks** (`tools/make_synthetic_workbook.py`)
- **Sample-like workbook** (contract 3.11): stays as it is, with no issues and the same counts, now
  read through `analyses`.
- **Edge workbook:** expectations change. Tab `UOIR ID 999 - Not in list` is now read and
  included. Its `ANALYSIS_SHEET_UNLISTED` text changes, and its fragment no longer matches its B1.
  The fix is to either adjust that fixture's B1 or expect the new `ANALYSIS_SHEET_TITLE_MISMATCH`;
  this is decided when the tests are written. The exact-issue-list tests are updated.
- **Rule tests** build variants with `clean_workbook_with`:
  - a tab covering two listed IDs;
  - three IDs with `,`, `&` and no spaces;
  - a non-breaking-space separator;
  - a number in the title that is not a listed ID;
  - `UOIR ID 901 - 902 - Pump` (`UOIR_ID_NOT_READ`);
  - a sheet `UOIR 901 - Fan` (`ANALYSIS_SHEET_NAME_UNREADABLE` + `UOIR_ID_NOT_READ`);
  - a listed UOIR named by no tab (info);
  - an unlisted tab (included, warning; an error inside it blocks export);
  - one ID in two tabs (warning, both used);
  - title rules for single-UOIR and multi-UOIR tabs (B1 blank, B1 inside the table);
  - no analysis tab at all (error, no MISSING infos);
  - UOIR sheet missing (no UNLISTED, TITLE_MISMATCH or SEVERAL_TABS noise);
  - ordering;
  - equipment union;
  - joined `uoir_id` on tab issues.
- `test_excel_linking.py`: its parse and linking tests are rewritten for the new helpers.

**End-to-end, PDF and smoke tests**
- **e2e workbook** (`build_extended_clean_workbook`): gains one two-ID tab and one UOIR with no
  tab. The JSON, the PDF text and the frontend data checks then cover the new shape.
- **PDF tests:** `test_pdf_fixtures.py` builds `AnalysisSection`s. Its "UOIR without a linked
  worksheet" case becomes "tab whose table could not be read". The tests assert one
  Analysis/Summary pair per section and the multi-ID headings.
- **All tests** that read `report.uoirs` move to `report.analyses` or `report.uoir_ids`.
- **Real-workbook smoke test** (opt-in, `FMEA_SAMPLE_WORKBOOK`): asserts `len(report.uoir_ids) >= 1`
  and stays value-free.

**Frontend**
- Checked in the browser against the mock server and the real backend: sidebar, Analysis,
  Recommendation, Workbook data, Data Checks with "Show in table", Preview and Export.

## 8. Out of scope

- PDF bookmarks or a table of contents (there are none today).
- Linking UOIRs to tabs by title or topic instead of by IDs in the tab name.
- Showing tab names in the PDF, or as captions on the screens.

## 9. Points to confirm in review

These were not discussed in chat. Each one is built as written below unless you say otherwise.

- **a. A workbook with no analysis tab at all is an error** (`ANALYSIS_SHEET_NONE`). Today such a
  workbook is already blocked, because every UOIR raises the `ANALYSIS_SHEET_MISSING` error. Error
  keeps that. A warning would let a report with no FMEA Analysis pages be exported.
- **b. Every analysis tab is now read and checked**, including unlisted tabs, hidden tabs and tabs
  sharing an ID (this follows from "include it, with a warning"). Today a stale tab such as `UOIR
  ID 999 - old copy` gives one warning and is otherwise ignored. From now on, an error inside it,
  such as a blank required cell, blocks export until it is fixed or the tab is deleted.
- **c. Safety net for misnamed tabs.** With "info only" for UOIRs without a tab, a misnamed tab
  would silently drop its analysis, and Data Checks would still say there are no problems.
  - Examples: `UOIR 901 - Fan` (no "ID"), or `UOIR ID 901 - 902 - Pump` (902 after the dash).
  - Today such workbooks are blocked. The two new warnings, `ANALYSIS_SHEET_NAME_UNREADABLE` and
    `UOIR_ID_NOT_READ`, point at the name to fix without blocking export.
- **d. Single-UOIR tabs keep today's title** (the UOIR sheet Title). B1 is the title only for tabs
  that cover several UOIRs or an unlisted ID, so existing reports print exactly as before.
- **e. Smaller choices:**
  - the tab-name fragment is the last title fallback;
  - tabs with no listed ID come last;
  - reading IDs stops at the first number that is not a listed ID, so in `UOIR ID 901 930 902`,
    where 930 is a typo, 902 is not read. 902 then gets `UOIR_ID_NOT_READ`, which points at the
    name.
