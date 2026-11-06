"""Stress checks on a SYNTHETIC report built to break page layout:
400-row analysis table, a merged group taller than a page, a 120-line cell,
merged text taller than a page, long unbreakable KKS codes, 12 strategies, an
empty pie, 200 recommendation rows and a very long title and station name.
"""
from __future__ import annotations

import re
import time

import fitz  # PyMuPDF (test-only)
import pytest

from backend.pdf import styles
from backend.pdf.render import render_pdf
from backend.tests.test_pdf_fixtures import (
    ANALYSIS_COLUMNS,
    LONG_KKS,
    STRESS_STATION,
    STRESS_TITLE,
    analysis_markers,
    compact,
    page_kind,
    page_lines,
    page_sections,
    recommendation_markers,
    section_starts,
    stress_report,
)

# Generous limit for a slow shared machine; a typical local render takes a few seconds.
MAX_RENDER_SECONDS = 45


@pytest.fixture(scope="module")
def report():
    return stress_report()


@pytest.fixture(scope="module")
def rendered(report):
    started = time.perf_counter()
    data = render_pdf(report)
    return data, time.perf_counter() - started


@pytest.fixture(scope="module")
def doc(rendered):
    document = fitz.open(stream=rendered[0], filetype="pdf")
    yield document
    document.close()


@pytest.fixture(scope="module")
def sections(doc):
    return page_sections(doc)


def _section_text(doc, sections, wanted) -> str:
    return "\n".join(page.get_text() for page, s in zip(doc, sections) if s == wanted)


def test_fixture_is_as_large_as_intended(report):
    assert len(report.analyses[0].analysis.rows) == 400
    assert max(m.last_row - m.first_row + 1 for m in report.analyses[0].analysis.merged) == 70
    assert sum(len(g.rows) for s in report.analyses for g in s.recommendations) == 200
    assert len(report.analyses[0].summary.pie) == 12
    assert report.analyses[1].summary.pie == []


def test_render_time(rendered):
    _, seconds = rendered
    print(f"stress render took {seconds:.2f} s")
    assert seconds < MAX_RENDER_SECONDS


def test_section_order_and_page_sizes(doc, sections, report):
    expected = ["cover", "intro"] + ["analysis", "summary"] * len(report.analyses) + ["recommendation"]
    assert section_starts(doc) == expected
    expected_kind = {"cover": "A4P", "intro": "A4P", "analysis": "A3L", "summary": "A4P", "recommendation": "A4P"}
    for number, (page, section) in enumerate(zip(doc, sections), start=1):
        assert page_kind(page) == expected_kind[section], f"page {number}"
    assert sections.count("analysis") > 15, "the 400-row table continues over many A3 pages"


def test_header_and_page_numbers_on_every_page(doc):
    total = len(doc)
    for number, page in enumerate(doc, start=1):
        text = page.get_text()
        if number == 1:
            assert "FMEA Report ·" not in text and "Page 1 of" not in text
            continue
        assert re.findall(r"Page (\d+) of (\d+)", text) == [(str(number), str(total))]
        header = [line for line in page_lines(page) if line.startswith("FMEA Report · ")]
        assert len(header) == 1, f"page {number}"
        # the very long station name is shortened with an ellipsis to stay on one line
        shown = header[0][len("FMEA Report · "):]
        assert STRESS_STATION.startswith(shown.rstrip("…").rstrip())


def test_every_analysis_row_appears_exactly_once(doc, sections, report):
    text = compact(_section_text(doc, sections, "analysis"))
    for marker in analysis_markers(report):
        assert text.count(marker) == 1, marker


def test_every_recommendation_row_appears_exactly_once(doc, sections, report):
    text = compact(_section_text(doc, sections, "recommendation"))
    markers = recommendation_markers(report)
    assert len(markers) == 200
    for marker in markers:
        assert text.count(marker) == 1, marker


def test_header_repeated_on_every_analysis_page(doc, sections):
    for number, (page, section) in enumerate(zip(doc, sections), start=1):
        if section == "analysis":
            text = compact(page.get_text())
            assert all(compact(h) in text for h in ANALYSIS_COLUMNS), f"page {number}"


def test_header_repeated_on_every_recommendation_page(doc, sections):
    for number, (page, section) in enumerate(zip(doc, sections), start=1):
        if section == "recommendation":
            lines = page_lines(page)
            assert "Failure Mode" in lines and "Task" in lines and "Frequency" in lines, f"page {number}"


def test_merged_groups_continue_with_marker(doc, sections, report):
    analysis_pages = [page for page, s in zip(doc, sections) if s == "analysis"]
    continued = [page for page in analysis_pages if "(cont.)" in page.get_text()]
    assert len(continued) >= 3, "the 70-row merged group and the tall merged text continue over pages"
    # the tall group's merged Failure Mode value is repeated where the group continues
    tall_group = next(m for m in report.analyses[0].analysis.merged if m.last_row - m.first_row == 69)
    value = report.analyses[0].analysis.rows[tall_group.first_row].cells[tall_group.first_col]
    pages_with_value = [page for page in analysis_pages if compact(value) in compact(page.get_text())]
    assert len(pages_with_value) >= 2


def test_long_cells_are_complete(doc, sections):
    def words(text):   # narrow columns wrap these lines, so compare word sequences
        return " ".join(text.split())

    everything = words("".join(page.get_text() for page in doc))
    analysis = words(_section_text(doc, sections, "analysis"))
    for i in range(1, 121):
        assert everything.count(f"SYNTHETIC remark line {i:03d}") == 1, i
        assert everything.count(f"SYNTHETIC task step {i:03d}") == 1, i
        assert everything.count(f"SYNTHETIC corrective step {i:03d}") == 1, i
        # merged Failure Mode text taller than a page: every line is on the analysis pages
        assert re.search(rf"SYNTHETIC merged detail line {i}(?!\d)", analysis), i


def test_long_unbreakable_codes_wrap_inside_the_page(doc, report):
    text = compact("".join(page.get_text() for page in doc))
    assert LONG_KKS in text
    assert compact(STRESS_TITLE) in text


def test_no_text_outside_the_body_frame(doc):
    """Nothing overflows a cell far enough to leave the page body (header/footer excepted)."""
    for number, page in enumerate(doc, start=1):
        if number == 1:
            continue
        width, height = page.rect.width, page.rect.height
        side = styles.A3_SIDE_MARGIN if page_kind(page) == "A3L" else styles.A4_SIDE_MARGIN
        top, bottom = styles.TOP_MARGIN, height - styles.BOTTOM_MARGIN
        for x0, y0, x1, y1, word, *_ in page.get_text("words"):
            if y1 < top - 10 or y0 > bottom:     # running header / footer
                continue
            assert side - 1 <= x0 and x1 <= width - side + 1, f"page {number}: {word!r} at x {x0:.1f}-{x1:.1f}"
            assert y0 >= top - 1 and y1 <= bottom + 1, f"page {number}: {word!r} at y {y0:.1f}-{y1:.1f}"


def test_twelve_strategy_legend(doc, sections, report):
    summary_text = _section_text(doc, sections, "summary")
    lines = summary_text.splitlines()
    for pie_slice in report.analyses[0].summary.pie:
        assert pie_slice.label in lines
    percents = [f"{s.percent:.1f}%" for s in report.analyses[0].summary.pie]
    assert all(p in lines for p in percents)


def test_empty_pie_and_blank_code(doc, sections):
    lines = _section_text(doc, sections, "summary").splitlines()
    assert "No strategy values to chart." in lines
    assert "—" in lines, "blank strategy code shows an em dash"
    assert "No rows with New Task set to Yes or No." in lines


def test_summary_that_does_not_fit_flows_with_repeated_header(doc, sections, report):
    summary_pages = [page for page, s in zip(doc, sections) if s == "summary"]
    first_section_pages = summary_pages[:2]
    assert "Analysis: FMEA Summary" in page_lines(first_section_pages[0])
    second = page_lines(first_section_pages[1])
    if "Analysis: FMEA Summary" not in second:   # continuation page repeats the table header
        assert "Work Centre" in second
