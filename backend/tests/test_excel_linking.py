"""Linking analysis tabs to UOIRs (CONTRACT.md section 3.6)."""
from __future__ import annotations

import pytest

from backend.excel.linking import (
    expected_tab_name,
    fragment_matches_title,
    parse_analysis_tab_name,
    uoir_id_key,
)
from backend.report.builder import build_report

TAB_601 = "UOIR ID 601 - Clean Pump Trip"
TAB_602 = "UOIR ID 602 - Clean Valve Fault"


def _codes(report):
    return [(i.severity, i.code, i.sheet) for i in report.issues]


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("UOIR ID 901 - SYNTHETIC Trip (M", ("901", "SYNTHETIC Trip (M")),
        ("UOIR ID 902 - Lube Oil Pressure", ("902", "Lube Oil Pressure")),
        ("uoir id:0901 -: SYNTHETIC", ("0901", "SYNTHETIC")),
        ("UOIRID903SYN COOLING", ("903", "SYN COOLING")),
        ("UOIR ID 999", ("999", "")),
        ("UOIR", None),
        ("Sheet3", None),
        ("Team Member", None),
    ],
)
def test_parse_analysis_tab_name(name, expected):
    assert parse_analysis_tab_name(name) == expected


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


def test_expected_tab_name_fits_excel_limit():
    assert expected_tab_name("901", "SYNTHETIC Trip (Main Relay) due to both cooling fans stopped") == (
        "UOIR ID 901 - SYNTHETIC Trip (M…"
    )
    assert expected_tab_name("7", "Short") == "UOIR ID 7 - Short"


# --------------------------------------------------------------------------- #
# Workbook-level rules (SYNTHETIC clean workbook with one change)
# --------------------------------------------------------------------------- #
def test_missing_tab_is_an_error_and_other_id_is_unlisted(clean_workbook_with):
    def rename(wb):
        wb[TAB_602].title = "UOIR ID 603 - Clean Valve Fault"

    report = build_report(clean_workbook_with(rename), "SYNTHETIC.xlsx")
    assert _codes(report) == [
        ("error", "ANALYSIS_SHEET_MISSING", "UOIR"),
        ("warning", "ANALYSIS_SHEET_UNLISTED", "UOIR ID 603 - Clean Valve Fault"),
    ]
    missing = report.issues[0]
    assert (missing.row, missing.cell, missing.column, missing.uoir_id) == (6, "B6", "UOIR ID", "602")
    assert missing.message == (
        "No worksheet found for UOIR ID 602. Expected a tab named like 'UOIR ID 602 - SYNTHETIC Clean V…'."
    )
    assert report.can_export is False
    section = next(u for u in report.uoirs if u.uoir_id == "602")
    assert (section.sheet_name, section.analysis, section.summary) == (None, None, None)


@pytest.mark.filterwarnings("ignore:Title is more than 31 characters")
def test_two_tabs_resolved_by_title_fragment(clean_workbook_with):
    def copy_tab(wb):
        copy = wb.copy_worksheet(wb[TAB_601])
        copy.title = "UOIR ID 601 - Something Else"

    report = build_report(clean_workbook_with(copy_tab), "SYNTHETIC.xlsx")
    assert _codes(report) == [("info", "SHEET_NOT_USED", "UOIR ID 601 - Something Else")]
    assert report.uoirs[0].sheet_name == TAB_601
    assert report.can_export is True


@pytest.mark.filterwarnings("ignore:Title is more than 31 characters")
def test_two_matching_tabs_are_ambiguous(clean_workbook_with):
    def copy_tab(wb):
        copy = wb.copy_worksheet(wb[TAB_601])
        copy.title = "UOIR ID 0601 - Clean Pump"

    report = build_report(clean_workbook_with(copy_tab), "SYNTHETIC.xlsx")
    assert _codes(report) == [("error", "ANALYSIS_SHEET_AMBIGUOUS", "UOIR")]
    issue = report.issues[0]
    assert f"'{TAB_601}'" in issue.message and "'UOIR ID 0601 - Clean Pump'" in issue.message
    assert report.uoirs[0].sheet_name is None


def test_title_fragment_mismatch_still_links_by_id(clean_workbook_with):
    def rename(wb):
        wb[TAB_601].title = "UOIR ID 601 - Wrong Words"

    report = build_report(clean_workbook_with(rename), "SYNTHETIC.xlsx")
    assert _codes(report) == [("warning", "ANALYSIS_SHEET_TITLE_MISMATCH", "UOIR ID 601 - Wrong Words")]
    assert report.uoirs[0].sheet_name == "UOIR ID 601 - Wrong Words"
    assert report.uoirs[0].summary.failure_mode_count == 4


def test_leading_zeros_in_tab_id_link(clean_workbook_with):
    def rename(wb):
        wb[TAB_601].title = "UOIR ID 00601 - Clean Pump Trip"

    report = build_report(clean_workbook_with(rename), "SYNTHETIC.xlsx")
    assert report.issues == []
    assert report.uoirs[0].sheet_name == "UOIR ID 00601 - Clean Pump Trip"


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
    assert report.uoirs[1].analysis is not None
