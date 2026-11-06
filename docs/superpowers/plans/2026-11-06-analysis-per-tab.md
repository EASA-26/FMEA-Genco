# Analysis per Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FMEA Analysis, FMEA Summary and Recommendation one section per "UOIR ID …" tab. A
tab name may list several UOIR IDs. Failure Details and the Introduction stay driven by the UOIR
sheet rows.

**Architecture:**
- `backend/excel/linking.py` becomes pure helpers. They read the IDs in a tab name and raise the
  tab-level and coverage checks.
- `backend/report/builder.py` reads the UOIR sheet first, then each analysis tab once, into a new
  `AnalysisSection`.
- `Report.uoirs` is replaced by `Report.analyses` (per tab) and `Report.uoir_ids` (distinct UOIR
  sheet IDs).
- The PDF and the React screens loop over `analyses`. The screens key every section by
  `sheet_name`.

**Tech Stack:**
- Backend: Python (FastAPI, pydantic, openpyxl, ReportLab) and pytest.
- Frontend: React 19 + Vite 8, plain CSS, no test runner. The frontend is verified by a build and
  in the browser.

**Spec:** `docs/superpowers/specs/2026-11-06-analysis-per-tab-design.md`. Read it before any task.
Section numbers below ("spec 3.6") refer to it.

## Global Constraints

- **Branch:** work on `feature/analysis-per-tab`. Commit per task. Never push, never merge, never
  touch `main`.
- **Python 3.11 syntax only.** No PEP 695, no 3.12+ APIs, no f-strings that reuse quotes inside
  braces. Checked with `ast.parse(src, feature_version=(3, 11))`.
- **No new dependencies.**
- **SYNTHETIC data only** in code, tests, mocks and docs. Before every commit, scan the staged files
  against `.claude/hooks/forbidden-terms.txt` (the scan command is in Task 7). It must find nothing.
- **Plain-language messages for engineers.** Every message text in this plan is exact copy.
- **Owner files** `backend/report/models.py`, `backend/config/mapping.py` and `docs/CONTRACT.md` are
  changed only as this plan says (owner-approved spec).
- **Frontend build:** run from `frontend/`:
  `node -e "import('vite').then(v => v.build()).then(() => process.exit(0))"`.
  Never `npm run build`, which hangs on this PC.
- **Commits:** end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Test commands:** run from the project root with `python -m pytest …`.

## Review Focus

1. **Typical tab names:** `UOIR ID 901 902 - Pump tr` (cut at 31 characters) and `UOIR ID 901 902`
   (no title). Both IDs must be read, and an empty fragment must raise no title warning. Owner:
   Task 1 (`test_parse_tab_name` rows 3, 9 and 10).
2. **More UOIRs than tabs, with one UOIR uncovered.** A workbook with 3 UOIR IDs, one two-ID tab, one
   single tab and one UOIR named by no tab exports with exactly one info and no warning. Owner: Task 2
   (`test_more_uoirs_than_tabs_exports_with_one_info`) and Task 3 (e2e workbook).
3. **Leading zeros:** an extra ID written with a leading zero (`UOIR ID 602 0603`) must still cover
   UOIR 603. Owner: Task 1 (`test_parse_tab_name` row 9).
4. **"Show in table" on an issue from a two-ID tab** must open that tab's section, not the first
   section. Owner: Task 4 (browser step).
5. **Empty and changing section lists.** When `analyses` is empty (`ANALYSIS_SHEET_NONE`), or when a
   new upload no longer has the selected `sheet_name`, every screen shows an empty state or falls
   back to the first section, with no crash. Owner: Task 4 (browser step with the mock "no tabs"
   variant).

---

### Task 1: Tab-name IDs and tab checks (pure helpers)

**Files:**
- Modify: `backend/config/mapping.py`. Add `ANALYSIS_EXTRA_ID_PATTERN` next to
  `ANALYSIS_SHEET_PATTERN`. Change the comment on `ANALYSIS_TITLE_CELL` to
  `# title cell: cross-check for one-UOIR tabs, the title for multi-UOIR tabs`.
- Modify: `backend/excel/linking.py`. Add the new helpers below. Leave the old
  `parse_analysis_tab_name`, `AnalysisTab`, `find_analysis_tabs`, `link_analysis_tabs`,
  `LinkOutcome` and `expected_tab_name` in place; Task 2 deletes them.
- Test: `backend/tests/test_excel_linking.py`. Add the new unit tests. Keep the old ones until Task 2.

**Interfaces:**
- Produces, in `backend/config/mapping.py`:
  - `ANALYSIS_EXTRA_ID_PATTERN = re.compile(r"[\s,&]+(\d+)(?=$|[\s,&:\-])")`, used with `.match`.
    Python's `\s` matches the non-breaking space.
- Produces, in `backend/excel/linking.py`:
  - `UoirRef` gains a field `position: int = 0`: the index in the distinct UOIR list.
  - `@dataclass(frozen=True) class AnalysisTabRef` with fields `sheet: SheetInfo`,
    `ids: tuple[str, ...]` (as written in the tab name, tab-name order, repeats removed by key),
    `keys: tuple[str, ...]` (`uoir_id_key` of each) and `fragment: str`.
  - `parse_tab_name(name: str, listed_keys: Collection[str] = frozenset()) -> tuple[list[str], str] | None`.
    It returns None when `ANALYSIS_SHEET_PATTERN` does not match. Otherwise:
    - the first ID is `match.group(1)`;
    - the rest is `name[match.end(1):]`;
    - repeat `ANALYSIS_EXTRA_ID_PATTERN.match(rest)` while the captured number's key is in
      `listed_keys`;
    - the fragment is the remaining text with `"-:,& \t\xa0"` stripped from the left.
  - `read_analysis_tabs(sheets: list[SheetInfo], listed_keys: Collection[str]) -> list[AnalysisTabRef]`
    returns the tabs in the order of `sheets`. It skips sheets the pattern does not match.
  - `display_ids(tab: AnalysisTabRef, listed: Mapping[str, UoirRef]) -> list[str]`. A listed key
    gives `listed[key].uoir_id`; otherwise the ID is as written in the tab name.
  - `tab_label(tab, listed) -> str` returns `", ".join(display_ids(tab, listed))`.
  - `is_single_uoir(tab, listed) -> bool` is true when `len(tab.keys) == 1` and that key is listed.
  - `tab_issues(tabs, listed, uoir_list_read: bool) -> list[Issue]`. For each tab in order it
    raises `ANALYSIS_SHEET_UNLISTED` (only when `uoir_list_read` and `tab.keys[0]` is not listed),
    then `ANALYSIS_SHEET_HIDDEN` (when `tab.sheet.hidden`).
  - `coverage_issues(tabs, listed, unreadable_names: list[str], uoir_list_read: bool) -> list[Issue]`:
    - First, `ANALYSIS_SHEET_NONE` when `uoir_list_read` and there are no tabs.
    - Then, for each listed UOIR in `position` order:
      - `UOIR_IN_SEVERAL_TABS` when two or more tabs name it;
      - when no tab names it: `UOIR_ID_NOT_READ` if its key equals the key of a separate number
        found in a tab fragment or in an unreadable sheet name (tabs first, then unreadable
        names, both in workbook order; the first hit is named);
      - otherwise `ANALYSIS_SHEET_MISSING`, unless NONE was raised.
    - A "separate number" is
      `re.findall(r"(?<![0-9A-Za-z])\d+(?![0-9A-Za-z])", text)`.
  - `fragment_mismatch(tab, listed, b1_title: str) -> Issue | None`. It returns None when:
    - the fragment is empty;
    - nothing is left to compare with (`b1_title` blank and every listed covered Title blank); or
    - `fragment_matches_title` is true for `b1_title` or for any listed covered Title.
  - `check_title_cell` is unchanged.

**Exact message copy (spec 3.6)**

`{id}` means the display ID, `{label}` is `tab_label`, and `{name}` is the sheet name. For locations,
"UOIR row" means `sheet=ref.sheet, row=ref.row, column=ref.column, cell=ref.cell, uoir_id=ref.uoir_id`.

- **`ANALYSIS_SHEET_MISSING`** (info, UOIR row):
  "UOIR ID {id} is not named in any analysis tab, so it is only shown in Failure Details. If a tab
  covers it, add {id} to that tab's name and upload again."
- **`UOIR_ID_NOT_READ`** (warning, UOIR row):
  "UOIR ID {id} appears in the name of tab '{name}', but it was not read as one of the tab's IDs.
  Write every ID right after 'UOIR ID', separated by spaces, commas or &, for example 'UOIR ID 123
  124 - Title', and upload again."
- **`ANALYSIS_SHEET_NAME_UNREADABLE`** (warning, `sheet=name`; raised by the builder in Task 2,
  but the copy lives here as a module constant `UNREADABLE_MESSAGE` with a `{name}` placeholder):
  "Sheet '{name}' looks like an analysis tab, but its name does not start with 'UOIR ID' and a
  number, so it is not in the report. Rename it like 'UOIR ID 123 - Title of the UOIR' and upload
  again."
- **`ANALYSIS_SHEET_UNLISTED`** (warning, `sheet=name, uoir_id=label`):
  "Tab '{name}' is for UOIR ID {id}, which is not in the UOIR list. It is included in the report.
  Add UOIR ID {id} to the UOIR sheet if it belongs there."
- **`UOIR_IN_SEVERAL_TABS`** (warning, UOIR row):
  "UOIR ID {id} is named in {n} tabs: {quote_list(names in workbook order)}. Both are in the report.
  Check that this is intended." When `n > 2`, use "All of them are in the report." instead of
  "Both are in the report."
- **`ANALYSIS_SHEET_HIDDEN`** (warning, `sheet=name, uoir_id=label`):
  "Tab '{name}' (UOIR ID {label}) is hidden in Excel. It is included in the report."
- **`ANALYSIS_SHEET_NONE`** (error, no location):
  "The workbook has no analysis tabs, so the report would have no FMEA Analysis. Add a tab named
  like 'UOIR ID 123 - Title of the UOIR' and upload again."
- **`ANALYSIS_SHEET_TITLE_MISMATCH`** (warning, `sheet=name, uoir_id=label`):
  "The name of tab '{name}' does not match {parts}. It is still used; check that it is the right
  tab."
  - `parts` joins with `" or "`:
    - `cell B1 ('{shorten(b1)}')` when B1 is not blank;
    - `the Title of UOIR ID {id} ('{shorten(t)}')` for the first listed covered UOIR with a Title;
    - further titled UOIRs as `{id} ('{shorten(t)}')`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_excel_linking.py`:

```python
LISTED = {"901", "902", "903", "905"}

@pytest.mark.parametrize("name, ids, fragment", [
    ("UOIR ID 901 902 - SYNTHETIC Pump trip", ["901", "902"], "SYNTHETIC Pump trip"),
    ("UOIR ID 901, 902 & 903 - Fan", ["901", "902", "903"], "Fan"),
    ("UOIR ID 901,902,903", ["901", "902", "903"], ""),
    ("UOIR ID 901\xa0902 - Fan", ["901", "902"], "Fan"),
    ("UOIR ID 905 2 fans trip", ["905"], "2 fans trip"),
    ("UOIR ID 901 132kV breaker", ["901"], "132kV breaker"),
    ("UOIR ID 901 - 902 - Pump", ["901"], "902 - Pump"),
    ("UOIR ID 999 902 - Valve", ["999", "902"], "Valve"),
    ("UOIR ID 902 0903", ["902", "0903"], ""),
    ("UOIR ID 901 902 - Pump tr", ["901", "902"], "Pump tr"),
    ("UOIR ID 901 901 - Fan", ["901"], "Fan"),
    ("UOIRID903SYN COOLING", ["903"], "SYN COOLING"),
    ("Notifications", None, None),
])
def test_parse_tab_name(name, ids, fragment):
    parsed = parse_tab_name(name, LISTED)
    assert parsed == (None if ids is None else (ids, fragment))

def test_parse_tab_name_without_uoir_list_reads_only_the_first_id():
    assert parse_tab_name("UOIR ID 901 902 - Fan") == (["901"], "902 - Fan")
```

  Also add pure tests that build `SheetInfo`/`UoirRef` values directly. They assert:
  - **`test_coverage_info_for_uncovered_uoir`:** the exact MISSING issue, info severity and UOIR
    row location.
  - **`test_coverage_not_read_replaces_missing`:** for the fragment `"902 - Pump"`, one
    `UOIR_ID_NOT_READ` and no MISSING.
  - **`test_coverage_none_suppresses_missing`:** with `[]` tabs, exactly one
    `("error", "ANALYSIS_SHEET_NONE")`.
  - **`test_coverage_several_tabs_lists_names_in_workbook_order`.**
  - **`test_tab_issues_skip_unlisted_when_uoir_list_not_read`.**
  - **`test_hidden_multi_id_tab_warns_once_with_joined_ids`:** `uoir_id == "901, 902"`.
  - **`test_fragment_mismatch_matches_b1_or_any_title`:** returns None when the fragment is in
    B1 only, or in the second title only. Returns the exact message when it matches none.

- [ ] **Step 2: Run them and check that they fail.**
  Run: `python -m pytest backend/tests/test_excel_linking.py -q`
  Expected: the new tests FAIL with ImportError / NameError.
- [ ] **Step 3: Implement** the mapping constant and the helpers with the signatures and copy above.
- [ ] **Step 4: Run them and check that they pass.**
  Run: `python -m pytest backend/tests/test_excel_linking.py -q`
  Expected: all PASS, old tests included.
- [ ] **Step 5: Commit.**
  `git commit -m "Tab names can list several UOIR IDs: parsing and tab checks"` (with trailer).

---

### Task 2: Report model and builder (one section per tab)

**Files:**
- Modify: `backend/report/models.py`. Add `AnalysisSection` (spec 4, field order as written there).
  Add `Report.uoir_ids: list[str] = Field(default_factory=list)` and
  `Report.analyses: list[AnalysisSection] = Field(default_factory=list)`. Delete `UoirSection` and
  `Report.uoirs`. Change the `RecommendationGroup.equipment` comment to
  `# Equipment of every UOIR the tab covers, joined with " / "`.
- Modify: `backend/report/builder.py`.
- Modify: `backend/excel/linking.py`. Delete `parse_analysis_tab_name`, `AnalysisTab`,
  `find_analysis_tabs`, `link_analysis_tabs`, `LinkOutcome` and `expected_tab_name`.
- Modify: `backend/report/summary.py`. Docstrings only: say "one analysis tab" instead of "one UOIR".
- Modify: `tools/make_synthetic_workbook.py`. Add `add_uoir_row`, and let `analysis_tab_name`
  accept several IDs.
- Create: `backend/tests/test_excel_analysis_tabs.py`. The rule tests below.
- Modify (migrate `report.uoirs` → `report.analyses` / `report.uoir_ids`; expected values unchanged
  unless stated):
  - `backend/tests/test_excel_linking.py`: delete the old parse, link and `expected_tab_name` tests,
    and rewrite the workbook-level ones per the rules below;
  - `test_excel_reader.py`;
  - `test_excel_review_regressions.py`;
  - `test_excel_sample_workbook.py`;
  - `test_excel_synthetic_edge_cases.py`;
  - `test_excel_validation_rules.py`;
  - `test_local_workbook_smoke.py`: assert `len(local_report.uoir_ids) >= 1`.

**Interfaces:**
- **Consumes (Task 1):** `parse_tab_name`, `read_analysis_tabs`, `AnalysisTabRef`, `display_ids`,
  `tab_label`, `is_single_uoir`, `tab_issues`, `coverage_issues`, `fragment_mismatch`,
  `check_title_cell`, `UNREADABLE_MESSAGE` and `UoirRef(position=…)`.
- **Produces (for Tasks 3 and 4):** `Report.analyses: list[AnalysisSection]` ordered per spec 3.5, and
  `Report.uoir_ids: list[str]`. Each tab issue has `sheet` = tab name and `uoir_id` = `tab_label`.
- **Produces (for tests):** `tools/make_synthetic_workbook.py` gets
  `add_uoir_row(wb: Workbook, uoir_id: int | str, title: str, equipment: str) -> int`. It writes
  the row under the last UOIR row, with dates 2026-05-01 and 2026-05-20 (`d-mmm-yy`) and the CA/PA
  text "SYNTHETIC action.", and returns the row number. `analysis_tab_name(uoir_id, fragment)`
  joins a list or tuple of IDs with spaces.

**Builder changes** (spec 3.1–3.5 and section 4):
- **`_classify_sheets`** returns `(team_sheet, uoir_sheet, analysis_sheets, unreadable_sheets)`.
  - A worksheet is an analysis sheet when `ANALYSIS_SHEET_PATTERN.match(name)`.
  - A worksheet whose trimmed name starts with `"uoir"` (casefolded) and does not match the pattern
    is unreadable. It gets warning `ANALYSIS_SHEET_NAME_UNREADABLE` (`sheet=name`) instead of info
    `SHEET_NOT_USED`. The UOIR sheet itself is excluded.
- **Per-UOIR records:** `_Section` becomes a per-UOIR record `_Uoir(ref: UoirRef, title: str,
  equipment: list[str], title_row: int)`. `ref.position` is set on creation.
  `UOIR_DUPLICATE_ID_CONFLICT` behaviour is unchanged.
- **UOIR-sheet `ROWS_AFTER_BLANK_ROW`:** its `left_out` text becomes `"not in Failure Details"`.
- **`build()` order:**
  1. classify;
  2. team;
  3. UOIRs; `uoir_list_read = bool(self.uoirs)`;
  4. `tabs = read_analysis_tabs(analysis_sheets, listed_keys)`;
  5. issues from `tab_issues`, then `coverage_issues`;
  6. one `_read_analysis(tab)` per tab;
  7. sort the sections by `(min(position of listed covered keys), sheet.index)`, with uncovered
     tabs keyed `(math.inf, sheet.index)`.
- **`_read_analysis(tab) -> AnalysisSection`:**
  - Pass `tab_label` wherever the old code passed `uoir_id` for issue locations.
  - **Title (spec 3.3):** for `is_single_uoir`, use the UOIR Title, else B1, else the fragment. For
    any other tab, use B1 (when it counts), else the first non-blank listed Title in tab-name
    order, else the fragment.
  - **"B1 counts"** is the existing rule: not inside the table rectangle, and checked in both the
    header-found and header-not-found branches.
  - **Title checks:** at the existing `check_title()` call points, raise `fragment_mismatch` first.
    Raise `check_title_cell` only when `is_single_uoir`. Skip `fragment_mismatch` when not
    `uoir_list_read`.
  - **Equipment (spec 3.4):** the listed covered UOIRs sorted by `position`, each record's
    `equipment` in order, deduplicated by `text_key`. The result goes to `build_recommendations`.

- [ ] **Step 1: Write the failing rule tests** in `backend/tests/test_excel_analysis_tabs.py`. They
  use the `clean_workbook_with` and `synthetic_tool` fixtures. The constants come from the tool:
  `CLEAN_TAB_601`, `CLEAN_TAB_602`, `CLEAN_TITLE_601` and `CLEAN_TITLE_602`.
  `TITLE_603 = "SYNTHETIC Clean Valve Fault During Shutdown"`, and `TWO_ID_TAB = "UOIR ID 602 603 - Clean Valve"`.
  `two_id(wb)` = `add_uoir_row(wb, 603, TITLE_603, "Clean Valve Positioner")` plus renaming
  `CLEAN_TAB_602` to `TWO_ID_TAB`. Tests and key assertions:
  - **`test_two_id_tab_is_one_section`:**
    - `uoir_ids == ["601", "602", "603"]` and `len(failure_details) == 3`;
    - `[(s.sheet_name, s.uoir_ids) for s in analyses] == [(CLEAN_TAB_601, ["601"]), (TWO_ID_TAB, ["602", "603"])]`;
    - for the two-ID section: `title == CLEAN_TITLE_602` (from B1),
      `equipment == ["Clean Valve", "Clean Valve Positioner"]`,
      `recommendations[0].heading == "Clean Valve / Clean Valve Positioner, KKS-CLEAN-3"` and
      `summary.failure_mode_count == 2`;
    - `report.issues == []` and `can_export`.
  - **`test_multi_id_title_is_b1_and_falls_back`:**
    - B1 = `"SYNTHETIC Clean Valve Topic"` gives that title;
    - B1 blank gives `CLEAN_TITLE_602`;
    - neither gives a `ANALYSIS_TITLE_CELL_MISMATCH`.
  - **`test_single_uoir_tab_keeps_uoir_sheet_title`:**
    - B1 of 602 = `CLEAN_TITLE_602.lower()` keeps title `CLEAN_TITLE_602` with no issue;
    - B1 = `"SYNTHETIC Other"` keeps title `CLEAN_TITLE_602` and gives one
      `ANALYSIS_TITLE_CELL_MISMATCH`.
  - **`test_more_uoirs_than_tabs_exports_with_one_info`:** `two_id` plus `add_uoir_row(wb, 604,
    "SYNTHETIC Clean Fan Stop", "Clean Fan")`. The issue codes are exactly
    `[("info", "ANALYSIS_SHEET_MISSING", "UOIR", "604")]`, `can_export`, and `len(analyses) == 2`.
  - **`test_uoir_id_not_read_after_a_dash`:** add 603, and rename 602's tab to
    `"UOIR ID 602 - 603 - Clean Valve"`. The codes, sorted, are
    `[("warning", "UOIR_ID_NOT_READ", "UOIR"), ("warning", "ANALYSIS_SHEET_TITLE_MISMATCH", "UOIR ID 602 - 603 - Clean Valve")]`.
    There is no MISSING.
  - **`test_unreadable_uoir_sheet_name_warns`:** rename 602's tab to `"UOIR 602 - Clean Valve"`. The
    codes are `[("warning", "UOIR_ID_NOT_READ", "UOIR"), ("warning", "ANALYSIS_SHEET_NAME_UNREADABLE", "UOIR 602 - Clean Valve")]`,
    `can_export` is true, and the analyses are `[CLEAN_TAB_601]` only.
  - **`test_unlisted_tab_is_included_last`:** add a copy of tab 601 named `"UOIR ID 999 - Clean
    Pump"` and move it to index 2.
    - The order is `[CLEAN_TAB_601, CLEAN_TAB_602, "UOIR ID 999 - Clean Pump"]`.
    - The 999 section has `uoir_ids == ["999"]`, `equipment == []` and
      `recommendations[0].heading == "KKS-CLEAN-1"`.
    - There is one UNLISTED warning with `uoir_id == "999"` and the exact message.
  - **`test_error_in_unlisted_tab_blocks_export`:** the same tab with C3 blank gives
    `REQUIRED_VALUE_BLANK` and `can_export is False`.
  - **`test_same_id_in_two_tabs_warns_and_keeps_both`:** copy 602's tab as `"UOIR ID 0602 - Clean
    Valve"`.
    - Both are in `analyses`, in workbook order.
    - There is one `UOIR_IN_SEVERAL_TABS` on UOIR row 6 with the exact message, "Both are in the
      report".
  - **`test_no_analysis_tab_is_an_error_without_missing_infos`:** delete both tabs. The issues are
    exactly `[("error", "ANALYSIS_SHEET_NONE")]` and `analyses == []`.
  - **`test_uoir_sheet_missing_adds_no_tab_noise`:** delete `"UOIR"`. The issue codes are exactly
    `["SHEET_MISSING"]`. There are 2 sections with `uoir_ids == ["601"]` and `["602"]`, and the
    titles come from B1.
  - **`test_sections_follow_uoir_sheet_order_not_tab_order`:** with `two_id`, move `TWO_ID_TAB` to
    index 2. The order is still `[CLEAN_TAB_601, TWO_ID_TAB]`. Then add UOIR 600 with `add_uoir_row`
    (listed after 603) and a tab `"UOIR ID 600 - Clean Pump"` copied from 601, moved to index 2. 600
    is listed last, so the order is `[CLEAN_TAB_601, TWO_ID_TAB, "UOIR ID 600 - Clean Pump"]`.
  - **`test_tab_issues_carry_joined_ids`:** with `two_id`, blank C3 of `TWO_ID_TAB`. One
    `REQUIRED_VALUE_BLANK` with `uoir_id == "602, 603"`.
  - **`test_hidden_two_id_tab_warns_once`.**
  - **`test_rows_after_blank_uoir_row_message`:** the existing scenario. The message ends
    "…so it is not in Failure Details. Remove the empty rows in between and upload again."

- [ ] **Step 2: Run them and check that they fail.**
  Run: `python -m pytest backend/tests/test_excel_analysis_tabs.py -q`
  Expected: FAIL (`add_uoir_row` missing; `Report` has no `analyses`).
- [ ] **Step 3: Implement** the model, builder, tool and linking-cleanup changes above.
- [ ] **Step 4: Migrate the existing parser tests.**
  - Replace `report.uoirs[i]` with `report.analyses[i]`; for single-UOIR tabs the indexes and values
    stay the same. Use `report.uoir_ids` where the test asserts the UOIR list.
  - Rewrite the tie-break tests in `test_excel_linking.py` as "both tabs used plus
    `UOIR_IN_SEVERAL_TABS`".
  - Rewrite `test_missing_tab_is_an_error_and_other_id_is_unlisted` as "info MISSING, plus the
    UNLISTED tab included".
  - **Edge workbook** (`test_excel_synthetic_edge_cases.py`):
    - `TAB_999` is now read and included last.
    - Update its UNLISTED message and the exact issue list and counts to what the new rules
      produce.
    - Add the expected `ANALYSIS_SHEET_TITLE_MISMATCH` for `TAB_999` (its fragment "Not in list" is
      not in its B1). Do not change the fixture.
    - Every added or changed entry must be explained by spec 3.1 or 3.6. Write one comment per
      changed entry saying which rule.
  - **Sample workbook:** `test_excel_sample_workbook.py` expectations are unchanged apart from the
    access path.
- [ ] **Step 5: Run the parser suite.**
  Run: `python -m pytest backend/tests/test_excel_*.py backend/tests/test_summary_*.py backend/tests/test_local_workbook_smoke.py -q`
  Expected: all PASS. The PDF and e2e tests fail until Task 3; that is expected.
- [ ] **Step 6: Commit.**
  `git commit -m "One analysis section per tab in the report model and builder"`

---

### Task 3: PDF per tab, and the backend end-to-end tests

**Files:**
- Modify: `backend/pdf/sections.py`. `analysis_page(section: AnalysisSection)`,
  `summary_page(section)`, `recommendation_section(report)` and `build_story` loop over
  `report.analyses`. Update the docstring and imports.
- Modify tests:
  - `backend/tests/test_pdf_fixtures.py`: builders make `AnalysisSection`s; `normal_report` gets one
    two-ID section with `failure_details` having more rows than sections; rename `pages_per_uoir`
    to `pages_per_section`;
  - `test_pdf_render.py`;
  - `test_pdf_adversarial.py`;
  - `test_pdf_stress.py`;
  - `test_pdf_units.py` (if it references `uoirs`);
  - `test_e2e_report_consistency.py`.

**Interfaces:**
- **Consumes:** `Report.analyses`, `AnalysisSection` (Task 2).
- **Produces (exact PDF copy):**
  - The key/value rows on both pages are `("UOIR ID", ", ".join(section.uoir_ids))` and
    `("Title", section.title)`.
  - The Recommendation H2 is `f"UOIR ID {', '.join(section.uoir_ids)}: {section.title}"`.
  - Empty states:
    - "No analysis table was read from this tab."
    - "No summary is available for this tab."
    - "No recommendations for this tab."
    - "No analysis tabs were found in the workbook."

- [ ] **Step 1: Write the failing tests:**
  - **`test_pdf_render.py::test_two_id_section_prints_one_page_pair_with_both_ids`:**
    - the starts are `['cover', 'intro'] + ['analysis', 'summary'] * len(report.analyses) + ['recommendation']`;
    - the two-ID A3 page has the key/value pair `("UOIR ID", "901, 902")`;
    - the Recommendation text contains `"UOIR ID 901, 902: "`;
    - the Failure Details table has `len(report.failure_details)` rows.
  - **`test_pdf_render.py::test_empty_states_say_tab`:** the four strings above.
  - In `test_e2e_report_consistency.py`, `build_extended_clean_workbook` adds
    `add_uoir_row(wb, 603, "SYNTHETIC Clean Valve Fault During Shutdown", "Clean Valve Positioner")`,
    renames `CLEAN_TAB_602` to `"UOIR ID 602 603 - Clean Valve"`, and adds
    `add_uoir_row(wb, 604, "SYNTHETIC Clean Fan Stop", "Clean Fan")` (no tab). Then:
    - the existing per-section assertions zip with `report["analyses"]`;
    - add an assertion that the JSON has `uoir_ids == ["601", "602", "603", "604"]`, 2 analyses,
      and exactly one info `ANALYSIS_SHEET_MISSING` for 604;
    - the PDF shows `UOIR ID : 602, 603` on that section's A3 and A4 pages.
- [ ] **Step 2: Run them and check that they fail.**
  Run: `python -m pytest backend/tests/test_pdf_render.py backend/tests/test_e2e_report_consistency.py -q`
  Expected: FAIL.
- [ ] **Step 3: Implement** the `sections.py` changes. Migrate the remaining PDF tests: zip with
  `analyses`, and use the new empty-state texts. The adversarial "UOIR without a linked worksheet"
  case becomes a section with `analysis=None`, expecting "No analysis table was read from this tab."
- [ ] **Step 4: Run the whole suite.**
  Run: `python -m pytest -q`
  Expected: all PASS (about 1000 tests, plus 2 skipped smoke tests).
- [ ] **Step 5: Commit.**
  `git commit -m "PDF: one Analysis and Summary page pair per tab"`

---

### Task 4: Frontend sections keyed by tab (data layer, selection, section screens, mocks)

**Files:**
- Modify: `frontend/src/lib/report.js`.
- Modify: `frontend/src/screens/Workspace.jsx`.
- Rename with `git mv`: `components/UoirSelector.jsx` → `components/SectionSelector.jsx`, and
  `components/UoirHeading.jsx` → `components/SectionHeading.jsx`. Update every import.
- Modify: `components/Sidebar.jsx`, `components/WorkbookData.jsx`, `components/SummaryPanel.jsx`,
  `components/AnalysisTable.jsx`, `views/AnalysisView.jsx`, `views/RecommendationView.jsx` and
  `styles/shell.css` (the `.uoir-link-id` chip).
- Modify: `frontend/src/mocks/synthetic-report.json` and `frontend/src/mocks/mockServer.js`.

**Interfaces:**
- **Consumes:** the JSON `report.analyses[]` with keys `sheet_name`, `uoir_ids`, `title`,
  `equipment`, `notes`, `analysis`, `tasks`, `summary` and `recommendations`; `report.uoir_ids[]`;
  issues with `sheet`/`uoir_id`.
- **Produces, in `lib/report.js`:**
  - `sectionLabel(section) => section.uoir_ids.join(', ')`;
  - `issuesForSection(issues, section) => issues.filter(i => i.sheet === section.sheet_name)`;
  - `findSection(report, sheetName)`;
  - `issueTarget(report, issue)`: the section by `issue.sheet`, plus the existing row and cell
    checks, returning `{ section, row, cell }`;
  - `newTaskCounts(section)` (parameter renamed only).
  - Delete `issuesForUoir`.
- **Produces, in Workspace:**
  - state `sectionKey` (`sheet_name` or null), defaulting to `next.analyses[0]?.sheet_name ?? null`;
  - `selectedSection = findSection(report, sectionKey) || report.analyses[0] || null`;
  - `showInTable(issue)` sets `sectionKey = issue.sheet` and `focus = { sheet, row, cell }`.
    Views receive `focus` only when `focus.sheet === selectedSection.sheet_name`;
  - the ErrorBoundary `resetKey` uses `selectedSection?.sheet_name`;
  - views get the prop `section` (not `uoir`) and `onSelectSection`.
- **Section screens:**
  - React `key`s use `sheet_name`.
  - DOM ids in `SummaryPanel` come from React `useId()`, not from IDs.
  - Labels read `UOIR ID ${sectionLabel(section)}`, for example
    `aria-label="FMEA Analysis table for UOIR ID 901, 902"`.
  - The selector group label is "Choose an analysis tab".
  - The sidebar and selector entries show `sectionLabel` and `title`, with
    `title={section.sheet_name}` as a tooltip. No visible sheet caption.
  - Markers come from `issuesForSection`.
  - `.uoir-link-id` gets `max-width: 50%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`.
- **Exact empty-state copy:**
  - No sections, as heading / body: "No analysis tabs found" / "No analysis tabs were found in the
    workbook. See Data checks."
  - A section with `analysis` null: "No analysis table for this tab" / "The analysis table could not
    be read from this tab. See Data checks."
  - A section with `summary` null: "No summary for this tab" / "The summary could not be worked out
    for this tab. See Data checks."
  - Remove the "No analysis tab linked" branch from `SectionHeading`.
  - RecommendationView's `EMPTY_TEXT` and its no-groups text say "this tab" instead of "this UOIR".
- **Mock data:** convert `synthetic-report.json` with a one-off script in the scratchpad. Do not
  commit the script.
  - `uoirs` becomes `analyses` (`uoir_id` → `uoir_ids: [id]`, drop nothing else).
  - Add `uoir_ids`.
  - Add `failure_details` row 904: "SYNTHETIC - Cooling water pump motor 2 bearing vibration high",
    Equipment "CW Pump Motor 2 Bearing".
    - The 902 section becomes `sheet_name` "UOIR ID 902 904 - CW pump motor" with
      `uoir_ids` ["902", "904"].
    - Its equipment is ["CW Pump Motor 2", "CW Pump Motor 2 Bearing"], and the recommendation
      headings are updated to match.
    - Its tab issues get `sheet` = that name and `uoir_id` "902, 904".
  - Add `failure_details` row 905 (no tab) plus the info `ANALYSIS_SHEET_MISSING` with the spec
    copy.
  - Validate with
    `python -c "import json; from backend.report.models import Report; Report.model_validate(json.load(open('frontend/src/mocks/synthetic-report.json', encoding='utf-8')))"`.
- **Mock server:**
  - The `withErrors` variant pushes a section `{sheet_name: 'UOIR ID 906 - Ash conveyor belt',
    uoir_ids: ['906'], analysis: null, summary: null, …}` plus the error `ANALYSIS_HEADER_MISSING`
    on that sheet, instead of `ANALYSIS_SHEET_MISSING`.
  - Add a mock variant with `analyses: []` plus `ANALYSIS_SHEET_NONE`, chosen the same way the
    existing variants are chosen in `mockServer.js`.

- [ ] **Step 1: Build check.** Run the build command (Global Constraints) from `frontend/`.
  Expected before the changes: it succeeds. This is the baseline.
- [ ] **Step 2: Implement** the data layer, Workspace, renames, section screens, CSS and mocks.
- [ ] **Step 3: Build.** Expected: the build succeeds with no warnings about missing imports.
- [ ] **Step 4: Browser check (mock server).** Run `preview_start` with `{name: "fmea-frontend-mock"}`.
  Sign in, upload, go to Review Data. Expected:
  - Data Checks shows the 905 info under "For information" with badge "UOIR ID 905".
  - The sidebar Analysis list has 3 entries. The second shows "902, 904" with tooltip
    "UOIR ID 902 904 - CW pump motor".
  - **Review Focus 4:** an issue from that tab clicked with "Show in table" opens that section and
    marks the cell.
  - The Analysis, Recommendation and Workbook data Analysis tabs follow the selected section.
  - The console has no errors.
  - **Review Focus 5:** switch to the "no tabs" variant and upload. Every section screen shows the
    no-sections empty state with no crash. Upload the normal mock again: the first section is
    selected.
- [ ] **Step 5: Commit.**
  `git commit -m "Frontend: analysis sections keyed by tab"`

---

### Task 5: Frontend counts and texts

**Files:**
- Modify: `components/Sidebar.jsx` (step detail count), `views/ChecksView.jsx` (fact card),
  `views/UploadView.jsx` (file meta, requirement card), `views/ExportView.jsx` (PDF contents card),
  `lib/pageHeading.js`, `components/ErrorBoundary.jsx` and `components/IntroTables.jsx` (comment
  only).

**Interfaces:**
- **Consumes:** `report.uoir_ids` and `report.analyses`.
- **Exact copy and counts:**
  - "UOIRs" figures (sidebar step detail, Data Checks fact card, upload file meta) use
    `report.uoir_ids.length`.
  - Workbook data "Analysis" tab count: `report.analyses.length` (done in Task 4 if it touched
    WorkbookData; otherwise here).
  - Export Analysis line:
    `` `${plural(report.analyses.length, 'analysis tab')} (${plural(report.uoir_ids.length, 'UOIR')}): FMEA Analysis on A3 landscape and FMEA Summary on A4` ``.
  - Export Recommendation line: "Tasks grouped by Equipment and KKS for every analysis tab".
  - Upload requirement card:
    - title "Analysis tabs named by UOIR ID";
    - text "Named like 'UOIR ID 123 - Title of the UOIR'. A tab that covers several UOIRs lists
      every ID after 'UOIR ID', separated by spaces, commas or &: 'UOIR ID 123 124 - Title' or
      'UOIR ID 123,124,125'. Excel allows 31 characters, so shorten the title part if needed."
    - Keep the existing list of required columns after it.
  - `pageHeading.js` subtitles:
    - Analysis: "Report section · The FMEA Analysis table and FMEA Summary counts for each analysis
      tab"
    - Recommendation: "Report section · Maintenance tasks for each analysis tab, grouped by
      Equipment and KKS"
  - ErrorBoundary text: "Choose another section, analysis tab or tab" becomes "Choose another
    section or analysis tab".

- [ ] **Step 1: Implement** the copy and counts above.
- [ ] **Step 2: Check the build and look for leftover wording.**
  - Run the build. Expected: it succeeds.
  - Run `grep -rn "uoirs\|issuesForUoir\|this UOIR\|every UOIR\|UoirSelector\|UoirHeading" frontend/src`.
    Expected: no hits.
- [ ] **Step 3: Browser check (mock).**
  - The Data Checks fact card "UOIRs" shows 5.
  - The Workbook data "Failure Details" tab shows 6 and "Analysis" shows 3.
  - The Export card reads "3 analysis tabs (5 UOIRs): …".
  - Take a screenshot of each for the final report.
- [ ] **Step 4: Commit.** `git commit -m "Frontend: UOIR and analysis-tab counts and wording"`

---

### Task 6: Contract and README

**Files:**
- Modify: `docs/CONTRACT.md`, as listed in spec section 7.
  - Add a Change log entry: "2026-11-06 — Analysis per tab: …" summarising spec section 2 and the
    new and removed codes.
  - Remove the section 7 row about the tie-break.
  - Update the 3.12 catalogue:
    - errors: remove `ANALYSIS_SHEET_MISSING` and `ANALYSIS_SHEET_AMBIGUOUS`, add
      `ANALYSIS_SHEET_NONE`;
    - warnings: add `UOIR_ID_NOT_READ`, `ANALYSIS_SHEET_NAME_UNREADABLE` and `UOIR_IN_SEVERAL_TABS`;
    - info: add `ANALYSIS_SHEET_MISSING`.
- Modify: `README.md`, the sections listed in spec section 7, including the "Checks and messages"
  tables (same code moves as 3.12).

- [ ] **Step 1: Edit** both files. Message examples use SYNTHETIC IDs (901, 902, 999) and the exact
  copy from Task 1.
- [ ] **Step 2: Check consistency.**
  - Run `grep -n "ANALYSIS_SHEET_AMBIGUOUS\|report.uoirs\|UoirSection\|per UOIR\|For each UOIR\|one per UOIR" docs/CONTRACT.md README.md`.
    Expected: hits only in the Change log.
  - Every code in `grep -rhoE '"(ANALYSIS|UOIR)_[A-Z_]+"' backend --include=*.py | sort -u` appears
    in both catalogues.
- [ ] **Step 3: Commit.** `git commit -m "Contract and README: analysis per tab"`

---

### Task 7: Final verification and dist

- [ ] **Step 1: Run the full suite.**
  Run: `python -m pytest -q`. Expected: all PASS.
- [ ] **Step 2: Run the smoke test on the real workbook** (local only, value-free).
  Run (bash): `FMEA_SAMPLE_WORKBOOK="$(ls *.xlsx | head -n 1)" python -m pytest backend/tests/test_local_workbook_smoke.py -q`.
  This uses the one `.xlsx` in the project root, which is gitignored.
  Expected: PASS. Never print or record its values.
- [ ] **Step 3: Check Python 3.11 syntax.**
  Run: `python -c "import ast,pathlib; [ast.parse(p.read_text(encoding='utf-8'), feature_version=(3,11)) for p in pathlib.Path('backend').rglob('*.py')]; [ast.parse(p.read_text(encoding='utf-8'), feature_version=(3,11)) for p in pathlib.Path('tools').rglob('*.py')]; print('ok')"`.
  Expected: `ok`.
- [ ] **Step 4: Scan for forbidden terms** over the branch's changed files.
  Run:
  `git diff --name-only main... | while read f; do while IFS= read -r t; do t="${t%$'\r'}"; [ -z "$t" ] && continue; case "$t" in \#*) continue;; esac; grep -qiF -- "$t" "$f" && echo "HIT in $f"; done < .claude/hooks/forbidden-terms.txt; done; echo scanned`.
  Expected: only `scanned`.
- [ ] **Step 5: Rebuild `frontend/dist`** with the build command. Check that `git status` shows only
  the `frontend/dist` changes.
  Commit: `git commit -m "Rebuild frontend/dist"`.
- [ ] **Step 6: Final browser pass with the real backend.**
  - Run `preview_start` with `{name: "fmea-app"}`. If port 8000 is held by the user's own server,
    use theirs; it serves `frontend/dist` live.
  - Upload a SYNTHETIC workbook: the e2e extended workbook, written to the scratchpad with
    `python -c` and `build_extended_clean_workbook`.
  - Check Data Checks (one info for 604), the sidebar ("602, 603"), Preview (the PDF shows
    "UOIR ID : 602, 603") and Export (counts).
  - If file upload cannot be automated, say so in the report. Do not claim it.
- [ ] **Step 7: Whole-branch review** (fresh reviewer against the spec), then report to the user.
  Do not push or merge.
