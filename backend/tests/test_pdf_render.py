"""End-to-end PDF checks on a normal SYNTHETIC report (3 UOIRs)."""
from __future__ import annotations

import re

import fitz  # PyMuPDF (test-only)
import pytest

from backend.pdf.cover import SIGNATURE_LABELS, SIGNATURE_RULE_OFFSET, signature_box_rects
from backend.pdf.render import render_pdf
from backend.tests.test_pdf_fixtures import (
    ANALYSIS_COLUMNS,
    NORMAL_STATION,
    analysis_markers,
    compact,
    normal_report,
    page_kind,
    page_lines,
    page_sections,
    recommendation_markers,
    section_starts,
)

HEADER = f"FMEA Report · {NORMAL_STATION}"


@pytest.fixture(scope="module")
def report():
    return normal_report()


@pytest.fixture(scope="module")
def pdf_bytes(report):
    return render_pdf(report)


@pytest.fixture(scope="module")
def doc(pdf_bytes):
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    yield document
    document.close()


def _text(doc, sections, wanted):
    return "\n".join(page.get_text() for page, section in zip(doc, sections) if section == wanted)


def test_returns_pdf_bytes_with_metadata(pdf_bytes, doc):
    assert pdf_bytes.startswith(b"%PDF")
    assert doc.metadata["title"] == "Failure Mode Effect Analysis (FMEA) Report"
    assert doc.metadata["subject"] == NORMAL_STATION


def test_section_order_and_page_sizes(doc, report):
    expected = ["cover", "intro"] + ["analysis", "summary"] * len(report.uoirs) + ["recommendation"]
    assert section_starts(doc) == expected

    expected_kind = {"cover": "A4P", "intro": "A4P", "analysis": "A3L", "summary": "A4P", "recommendation": "A4P"}
    sections = page_sections(doc)
    for number, (page, section) in enumerate(zip(doc, sections), start=1):
        assert page_kind(page) == expected_kind[section], f"page {number} ({section})"
    assert sections[0] == "cover" and sections[-1] == "recommendation"


def test_running_header_on_every_page_except_cover(doc):
    assert HEADER not in doc[0].get_text()
    assert "FMEA Report ·" not in doc[0].get_text()
    for number, page in enumerate(doc, start=1):
        if number == 1:
            continue
        hits = page.search_for(HEADER)
        assert hits, f"header missing on page {number}"
        assert hits[0].y1 < 45, "header must sit above the body frame"


def test_page_x_of_y_on_every_page_except_cover(doc):
    total = len(doc)
    assert not re.search(r"Page \d+ of \d+", doc[0].get_text())
    for number, page in enumerate(doc, start=1):
        if number == 1:
            continue
        found = re.findall(r"Page (\d+) of (\d+)", page.get_text())
        assert found == [(str(number), str(total))], f"page {number}: {found}"
        hit = page.search_for(f"Page {number} of {total}")[0]
        assert hit.y0 > page.rect.height - 40, "page number sits in the footer"
        assert page.rect.width - hit.x1 < 50, "page number is right-aligned"


def test_every_analysis_row_is_on_an_analysis_page(doc, report):
    sections = page_sections(doc)
    text = compact(_text(doc, sections, "analysis"))
    for marker in analysis_markers(report):
        assert text.count(marker) == 1, marker


def test_every_recommendation_row_is_in_the_recommendation_section(doc, report):
    sections = page_sections(doc)
    text = compact(_text(doc, sections, "recommendation"))
    markers = recommendation_markers(report)
    assert len(markers) == sum(len(u.analysis.rows) for u in report.uoirs)
    for marker in markers:
        assert text.count(marker) == 1, marker


def test_every_analysis_column_header_on_every_analysis_page(doc):
    for number, (page, section) in enumerate(zip(doc, page_sections(doc)), start=1):
        if section != "analysis":
            continue
        text = compact(page.get_text())
        for header in ANALYSIS_COLUMNS:
            assert compact(header) in text, f"{header!r} missing on page {number}"


def test_analysis_page_lists_uoir_title_and_notes(doc, report):
    sections = page_sections(doc)
    analysis_pages = [page for page, s in zip(doc, sections) if s == "analysis"]
    for uoir, page in zip(report.uoirs, analysis_pages):
        lines = page_lines(page)
        assert "Analysis: FMEA Analysis" in lines
        assert "UOIR ID" in lines and uoir.uoir_id in lines
        assert "Title" in lines and uoir.title in lines
        assert lines.count("Note") == len(uoir.notes)
        text = page.get_text()
        for note in uoir.notes:
            for note_line in note.text.split("\n"):
                assert note_line in text


def test_introduction_tables(doc, report):
    text = _text(doc, page_sections(doc), "intro")
    for label in ("UOIR ID", "Title", "Faulty Date", "UOIR ID Date", "Corrective Action (CA)",
                  "Preventive Action (PA)", "Equipment", "Failure Details", "Team Members",
                  "No", "Name", "Staff No", "Section"):
        assert label in text, label
    for member in report.team:
        assert member.name in text and member.staff_no in text
    for detail in report.failure_details:
        # workbook line breaks are kept: every line is present, in order
        positions = [compact(text).find(compact(line)) for line in detail.corrective_action.split("\n")]
        assert all(p >= 0 for p in positions) and positions == sorted(positions)


def test_summary_page_content(doc, report):
    sections = page_sections(doc)
    summary_pages = [page for page, s in zip(doc, sections) if s == "summary"]
    assert len(summary_pages) == len(report.uoirs), "each summary fits on one page"
    for uoir, page in zip(report.uoirs, summary_pages):
        lines = page_lines(page)
        summary = uoir.summary
        for label, value in (("Failure Mode", summary.failure_mode_count),
                             ("Maintenance Task", summary.maintenance_task_count),
                             ("Task Executed", summary.task_executed_count)):
            assert lines[lines.index(label) + 1] == str(value)
        for heading in ("Existing vs Revised", "Recommended Strategy", "Work-Centre Execution",
                        "Code", "Strategy", "Existing", "New", "Work Centre", "Total", "Executed", "Pending"):
            assert heading in lines, heading
        for pie_slice in summary.pie:
            assert f"{pie_slice.percent:.1f}%" in lines
        for row in summary.strategy_rows:
            assert row.label in lines
        for row in summary.work_centre_rows:
            assert row.work_centre in lines
        assert "Not counted: row 8 (OC, SYNINCS) — New Task blank." in lines
        if summary.duplicate_rows:
            assert "Row 9 is identical to an earlier row and was counted once." in lines


def test_recommendation_headings_and_grouped_header(doc, report):
    sections = page_sections(doc)
    pages = [page for page, s in zip(doc, sections) if s == "recommendation"]
    text = "\n".join(page.get_text() for page in pages)
    for uoir in report.uoirs:
        assert f"UOIR ID {uoir.uoir_id}: {uoir.title}" in text
        for group in uoir.recommendations:
            assert group.heading in text
    for page in pages:
        lines = page_lines(page)
        # the two-row header: Failure Mode | Recommendations / Task | Frequency
        for index, line in enumerate(lines):
            if line == "Failure Mode":
                assert lines[index + 1:index + 4] == ["Recommendations", "Task", "Frequency"]


def test_headings_are_never_the_last_thing_on_a_page(doc, report):
    headings = {g.heading for u in report.uoirs for g in u.recommendations}
    headings |= {f"UOIR ID {u.uoir_id}: {u.title}" for u in report.uoirs}
    for page, section in zip(doc, page_sections(doc)):
        if section != "recommendation":
            continue
        body = [line for line in page_lines(page) if not line.startswith(("FMEA Report", "Page "))]
        last_heading = max((i for i, line in enumerate(body) if line in headings), default=None)
        if last_heading is not None:
            assert "Failure Mode" in body[last_heading:], "heading kept with its table"


def test_text_is_escaped_not_interpreted(doc):
    text = "".join(page.get_text() for page in doc)
    assert "<terminal block>" in text
    assert "control & actuator <slow>" in text


def test_signature_boxes_are_blank(doc):
    cover = doc[0]
    height = cover.rect.height
    for (x, y, w, h), label in zip(signature_box_rects(), SIGNATURE_LABELS):
        card = fitz.Rect(x, height - (y + h), x + w, height - y)
        words = [word[4] for word in cover.get_text("words", clip=card)]
        assert " ".join(words) == label, words
        signing_area = fitz.Rect(x, height - (y + h) + SIGNATURE_RULE_OFFSET + 1, x + w, height - y)
        assert cover.get_text("words", clip=signing_area) == []


def test_cover_shows_station_and_date(doc, report):
    lines = page_lines(doc[0])
    for expected in ("ALCM - Maintenance Strategy", "Failure Mode Effect", "Analysis (FMEA)", "Report"):
        assert expected in lines, expected
    text = compact(doc[0].get_text())
    assert compact(f"Station : {report.station}") in text
    assert compact(f"Date of Analysis : {report.analysis_date_text}") in text
    assert doc[0].get_images(), "logo image embedded"

    # colons of the two rows share one column
    station_colon = doc[0].search_for(": " + report.station)[0]
    date_colon = doc[0].search_for(": " + report.analysis_date_text)[0]
    assert abs(station_colon.x0 - date_colon.x0) < 0.5


def test_all_fonts_are_embedded(doc):
    for number, page in enumerate(doc, start=1):
        for xref, ext, font_type, basefont, *_ in page.get_fonts(full=True):
            assert ext != "n/a", f"page {number}: {basefont} is not embedded"
            assert "LiberationSans" in basefont, basefont


def test_renders_even_when_export_is_blocked(report):
    blocked = report.model_copy(update={"can_export": False})
    assert render_pdf(blocked).startswith(b"%PDF")


def test_minimal_report_without_uoirs_team_or_details(report):
    empty = report.model_copy(update={"uoirs": [], "team": [], "failure_details": [], "station": ""})
    document = fitz.open(stream=render_pdf(empty), filetype="pdf")
    assert section_starts(document) == ["cover", "intro", "recommendation"]
    text = "".join(page.get_text() for page in document)
    assert "No failure details were found in the workbook." in text
    assert "No team members were found in the workbook." in text
    assert "No UOIRs were found in the workbook." in text
    assert "FMEA Report" in document[1].get_text()


def test_uoir_without_analysis_summary_or_recommendations(report):
    bare = report.uoirs[0].model_copy(update={"analysis": None, "summary": None, "recommendations": [],
                                               "notes": []})
    document = fitz.open(stream=render_pdf(report.model_copy(update={"uoirs": [bare]})), filetype="pdf")
    assert section_starts(document) == ["cover", "intro", "analysis", "summary", "recommendation"]
    text = "".join(page.get_text() for page in document)
    assert "No analysis worksheet is linked to this UOIR" in text
    assert "No summary is available for this UOIR." in text
    assert "No recommendations for this UOIR." in text


def test_very_long_station_name_stays_clear_of_the_signing_cards(report):
    station = "SYNTHETIC " + "extremely long station name " * 150
    document = fitz.open(stream=render_pdf(report.model_copy(update={"station": station, "uoirs": []})),
                         filetype="pdf")
    cover = document[0]
    height = cover.rect.height
    cards_top = height - max(y + h for _, y, _, h in signature_box_rects())
    labels = {word for label in SIGNATURE_LABELS for word in label.split()}
    for x0, y0, x1, y1, word, *_ in cover.get_text("words"):
        if word not in labels:
            assert y1 < cards_top, f"{word!r} runs into the signing cards"
    assert compact(f"Date of Analysis : {report.analysis_date_text}") in compact(cover.get_text())
