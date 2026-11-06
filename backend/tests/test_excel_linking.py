"""Which UOIRs an analysis tab covers, and the tab checks (CONTRACT.md section 3.6)."""
from __future__ import annotations

import pytest

from backend.excel.linking import (
    UoirRef,
    coverage_issues,
    display_ids,
    fragment_mismatch,
    fragment_matches_title,
    is_single_uoir,
    parse_tab_name,
    read_analysis_tabs,
    tab_issues,
    tab_label,
    uoir_id_key,
)
from backend.excel.reader import SheetInfo
from backend.report.builder import build_report

TAB_601 = "UOIR ID 601 - Clean Pump Trip"
TAB_602 = "UOIR ID 602 - Clean Valve Fault"


def _codes(report):
    return [(i.severity, i.code, i.sheet) for i in report.issues]


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("value", "key"), [("901", "901"), ("0901", "901"), ("000", "0"), ("901A", "901A")])
def test_uoir_id_key_strips_leading_zeros(value, key):
    assert uoir_id_key(value) == key


@pytest.mark.parametrize(
    ("fragment", "title", "matches"),
    [
        ("SYNTHETIC Trip (M", "SYNTHETIC Trip (Main Relay) due to both cooling fans stopped", True),
        ("Lube Oil Pressure", "SYNTHETIC Trip due to Lube Oil Pressure Lo Lo", True),   # middle
        ("lube  OIL pressu", "SYNTHETIC Trip due to Lube Oil Pressure Lo Lo", True),
        ("Valve AB", "Valve A/B: stuck", True),                                           # forbidden chars
        ("", "Anything", True),
        ("Pump Trip", "SYNTHETIC Fan Fault", False),
    ],
)
def test_fragment_matches_title(fragment, title, matches):
    assert fragment_matches_title(fragment, title) is matches


# --------------------------------------------------------------------------- #
# Workbook-level rules (SYNTHETIC clean workbook with one change)
# --------------------------------------------------------------------------- #
def test_missing_tab_is_info_and_the_unlisted_tab_is_included(clean_workbook_with):
    def rename(wb):
        wb[TAB_602].title = "UOIR ID 603 - Clean Valve Fault"

    report = build_report(clean_workbook_with(rename), "SYNTHETIC.xlsx")
    assert _codes(report) == [
        ("warning", "ANALYSIS_SHEET_UNLISTED", "UOIR ID 603 - Clean Valve Fault"),
        ("info", "ANALYSIS_SHEET_MISSING", "UOIR"),
    ]
    missing = report.issues[1]
    assert (missing.row, missing.cell, missing.column, missing.uoir_id) == (6, "B6", "UOIR ID", "602")
    assert missing.message == (
        "UOIR ID 602 is not named in any analysis tab, so it is only shown in Failure Details. If a tab "
        "covers it, add 602 to that tab's name and upload again."
    )
    assert report.can_export is True
    assert report.uoir_ids == ["601", "602"]
    assert [(s.sheet_name, s.uoir_ids) for s in report.analyses] == [
        (TAB_601, ["601"]), ("UOIR ID 603 - Clean Valve Fault", ["603"]),
    ]
    unlisted = report.analyses[1]
    assert (unlisted.equipment, unlisted.summary.failure_mode_count) == ([], 2)


@pytest.mark.filterwarnings("ignore:Title is more than 31 characters")
def test_two_tabs_for_one_id_are_both_used_with_a_warning(clean_workbook_with):
    def copy_tab(wb):
        copy = wb.copy_worksheet(wb[TAB_601])
        copy.title = "UOIR ID 601 - Something Else"

    report = build_report(clean_workbook_with(copy_tab), "SYNTHETIC.xlsx")
    assert _codes(report) == [
        ("warning", "UOIR_IN_SEVERAL_TABS", "UOIR"),
        ("warning", "ANALYSIS_SHEET_TITLE_MISMATCH", "UOIR ID 601 - Something Else"),
    ]
    assert [s.sheet_name for s in report.analyses] == [TAB_601, "UOIR ID 601 - Something Else", TAB_602]
    assert report.can_export is True


@pytest.mark.filterwarnings("ignore:Title is more than 31 characters")
def test_two_matching_tabs_for_one_id_are_both_used_with_a_warning(clean_workbook_with):
    def copy_tab(wb):
        copy = wb.copy_worksheet(wb[TAB_601])
        copy.title = "UOIR ID 0601 - Clean Pump"

    report = build_report(clean_workbook_with(copy_tab), "SYNTHETIC.xlsx")
    assert _codes(report) == [("warning", "UOIR_IN_SEVERAL_TABS", "UOIR")]
    issue = report.issues[0]
    assert (issue.row, issue.uoir_id) == (5, "601")
    assert issue.message == (
        f"UOIR ID 601 is named in 2 tabs: '{TAB_601}' and 'UOIR ID 0601 - Clean Pump'. Both are in the "
        "report. Check that this is intended."
    )
    assert [(s.sheet_name, s.uoir_ids) for s in report.analyses] == [
        (TAB_601, ["601"]), ("UOIR ID 0601 - Clean Pump", ["601"]), (TAB_602, ["602"]),
    ]
    assert report.can_export is True


def test_title_fragment_mismatch_still_links_by_id(clean_workbook_with):
    def rename(wb):
        wb[TAB_601].title = "UOIR ID 601 - Wrong Words"

    report = build_report(clean_workbook_with(rename), "SYNTHETIC.xlsx")
    assert _codes(report) == [("warning", "ANALYSIS_SHEET_TITLE_MISMATCH", "UOIR ID 601 - Wrong Words")]
    assert report.analyses[0].sheet_name == "UOIR ID 601 - Wrong Words"
    assert report.analyses[0].summary.failure_mode_count == 4


def test_leading_zeros_in_tab_id_link(clean_workbook_with):
    def rename(wb):
        wb[TAB_601].title = "UOIR ID 00601 - Clean Pump Trip"

    report = build_report(clean_workbook_with(rename), "SYNTHETIC.xlsx")
    assert report.issues == []
    assert report.analyses[0].sheet_name == "UOIR ID 00601 - Clean Pump Trip"
    assert report.analyses[0].uoir_ids == ["601"]           # shown as on the UOIR sheet


def test_title_cell_mismatch_and_case_insensitive_match(clean_workbook_with):
    def change_b1(wb):
        wb[TAB_601]["B1"] = "SYNTHETIC A Different Title"
        wb[TAB_602]["B1"] = "synthetic clean valve fault   during start-up"   # same title, other case/spacing

    report = build_report(clean_workbook_with(change_b1), "SYNTHETIC.xlsx")
    assert [(i.severity, i.code, i.sheet, i.row, i.cell) for i in report.issues] == [
        ("warning", "ANALYSIS_TITLE_CELL_MISMATCH", TAB_601, 1, "B1"),
    ]


def test_blank_title_cell_is_not_checked(clean_workbook_with):
    def clear_b1(wb):
        wb[TAB_601]["B1"] = None

    assert build_report(clean_workbook_with(clear_b1), "SYNTHETIC.xlsx").issues == []


def test_hidden_linked_tab_warns(clean_workbook_with):
    def hide(wb):
        wb[TAB_602].sheet_state = "hidden"

    report = build_report(clean_workbook_with(hide), "SYNTHETIC.xlsx")
    assert _codes(report) == [("warning", "ANALYSIS_SHEET_HIDDEN", TAB_602)]
    assert report.analyses[1].analysis is not None


# --------------------------------------------------------------------------- #
# Tab names that list several UOIR IDs (synthetic values)
# --------------------------------------------------------------------------- #
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


def _ref(uoir_id, title, position):
    return UoirRef(uoir_id, title, "UOIR", 5 + position, cell=f"A{5 + position}", column="A", position=position)


def _listed(*pairs):
    return {uoir_id_key(i): _ref(i, t, n) for n, (i, t) in enumerate(pairs)}


def _tabs(*names, hidden=()):
    sheets = [SheetInfo(n, i, state="hidden" if n in hidden else "visible") for i, n in enumerate(names)]
    return read_analysis_tabs(sheets, LISTED)


def test_read_analysis_tabs_skips_other_sheets_and_keeps_order():
    tabs = _tabs("UOIR", "UOIR ID 902 - B", "Notes", "UOIR ID 901 903 - A")
    assert [t.sheet.name for t in tabs] == ["UOIR ID 902 - B", "UOIR ID 901 903 - A"]
    assert tabs[1].ids == ("901", "903") and tabs[1].keys == ("901", "903") and tabs[1].fragment == "A"


def test_display_ids_prefers_the_uoir_sheet_spelling():
    listed = _listed(("0901", "Pump"))
    tab = _tabs("UOIR ID 901 902 - Pump")[0]
    assert display_ids(tab, listed) == ["0901", "902"]
    assert tab_label(tab, listed) == "0901, 902"
    assert is_single_uoir(_tabs("UOIR ID 901 - Pump")[0], listed)
    assert not is_single_uoir(tab, listed)
    assert not is_single_uoir(_tabs("UOIR ID 999 - Pump")[0], listed)


def test_coverage_info_for_uncovered_uoir():
    listed = _listed(("901", "Pump"), ("902", "Fan"))
    issues = coverage_issues(_tabs("UOIR ID 901 - Pump"), listed, [], True)
    assert len(issues) == 1
    issue = issues[0]
    assert (issue.severity, issue.code) == ("info", "ANALYSIS_SHEET_MISSING")
    assert issue.message == (
        "UOIR ID 902 is not named in any analysis tab, so it is only shown in Failure Details. "
        "If a tab covers it, add 902 to that tab's name and upload again."
    )
    assert (issue.sheet, issue.row, issue.column, issue.cell, issue.uoir_id) == ("UOIR", 6, "A", "A6", "902")


def test_coverage_not_read_replaces_missing():
    listed = _listed(("901", "Pump"), ("902", "Fan"))
    issues = coverage_issues(_tabs("UOIR ID 901 - 902 - Pump"), listed, [], True)
    assert [(i.severity, i.code) for i in issues] == [("warning", "UOIR_ID_NOT_READ")]
    assert issues[0].uoir_id == "902"
    assert issues[0].message == (
        "UOIR ID 902 appears in the name of tab 'UOIR ID 901 - 902 - Pump', but it was not read as one "
        "of the tab's IDs. Write every ID right after 'UOIR ID', separated by spaces, commas or &, for "
        "example 'UOIR ID 123 124 - Title', and upload again."
    )


def test_coverage_not_read_from_unreadable_name():
    listed = _listed(("901", "Pump"), ("902", "Fan"))
    issues = coverage_issues(_tabs("UOIR ID 901 - Pump"), listed, ["Fan 902 trip"], True)
    assert [i.code for i in issues] == ["UOIR_ID_NOT_READ"]
    assert "tab 'Fan 902 trip'" in issues[0].message


def test_coverage_none_suppresses_missing():
    listed = _listed(("901", "Pump"), ("902", "Fan"))
    issues = coverage_issues([], listed, [], True)
    assert [(i.severity, i.code) for i in issues] == [("error", "ANALYSIS_SHEET_NONE")]
    assert issues[0].message == (
        "The workbook has no analysis tabs, so the report would have no FMEA Analysis. Add a tab named "
        "like 'UOIR ID 123 - Title of the UOIR' and upload again."
    )


def test_coverage_several_tabs_lists_names_in_workbook_order():
    listed = _listed(("901", "Pump"))
    issues = coverage_issues(_tabs("UOIR ID 901 - B", "UOIR ID 901 - A"), listed, [], True)
    assert [i.code for i in issues] == ["UOIR_IN_SEVERAL_TABS"]
    assert issues[0].message == (
        "UOIR ID 901 is named in 2 tabs: 'UOIR ID 901 - B' and 'UOIR ID 901 - A'. Both are in the "
        "report. Check that this is intended."
    )
    three = coverage_issues(_tabs("UOIR ID 901 - A", "UOIR ID 901 - B", "UOIR ID 901 - C"), listed, [], True)
    assert "All of them are in the report." in three[0].message and "named in 3 tabs" in three[0].message


def test_tab_issues_skip_unlisted_when_uoir_list_not_read():
    listed = _listed(("901", "Pump"))
    tabs = _tabs("UOIR ID 999 - X")
    assert tab_issues(tabs, {}, False) == []
    issues = tab_issues(tabs, listed, True)
    assert [(i.severity, i.code) for i in issues] == [("warning", "ANALYSIS_SHEET_UNLISTED")]
    assert issues[0].message == (
        "Tab 'UOIR ID 999 - X' is for UOIR ID 999, which is not in the UOIR list. It is included in the "
        "report. Add UOIR ID 999 to the UOIR sheet if it belongs there."
    )
    assert (issues[0].sheet, issues[0].uoir_id) == ("UOIR ID 999 - X", "999")


def test_hidden_multi_id_tab_warns_once_with_joined_ids():
    listed = _listed(("901", "Pump"), ("902", "Fan"))
    name = "UOIR ID 901 902 - Pump"
    issues = tab_issues(_tabs(name, hidden=(name,)), listed, True)
    assert [(i.severity, i.code) for i in issues] == [("warning", "ANALYSIS_SHEET_HIDDEN")]
    assert issues[0].uoir_id == "901, 902"
    assert issues[0].message == f"Tab '{name}' (UOIR ID 901, 902) is hidden in Excel. It is included in the report."


def test_fragment_mismatch_matches_b1_or_any_title():
    listed = _listed(("901", "Main pump trip"), ("902", "Cooling fan fault"))
    tab = _tabs("UOIR ID 901 902 - Fan")[0]
    assert fragment_mismatch(tab, listed, "Something else") is None      # in the second title
    tab = _tabs("UOIR ID 901 902 - Zebra")[0]
    assert fragment_mismatch(tab, listed, "Zebra crossing") is None      # in B1 only
    issue = fragment_mismatch(tab, listed, "B1 title")
    assert (issue.severity, issue.code) == ("warning", "ANALYSIS_SHEET_TITLE_MISMATCH")
    assert issue.uoir_id == "901, 902" and issue.sheet == tab.sheet.name
    assert issue.message == (
        "The name of tab 'UOIR ID 901 902 - Zebra' does not match cell B1 ('B1 title') or the Title of "
        "UOIR ID 901 ('Main pump trip') or 902 ('Cooling fan fault'). It is still used; check that it is "
        "the right tab."
    )


def test_fragment_mismatch_none_when_fragment_empty_or_nothing_to_compare():
    listed = _listed(("901", ""))
    assert fragment_mismatch(_tabs("UOIR ID 901")[0], listed, "x") is None
    assert fragment_mismatch(_tabs("UOIR ID 901 - Zebra")[0], listed, "") is None
