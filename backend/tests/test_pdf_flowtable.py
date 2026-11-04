"""FlowTable page-split rules, checked on small SYNTHETIC pages."""
from __future__ import annotations

import io
import re

import fitz  # PyMuPDF (test-only)
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer

from backend.pdf import styles
from backend.pdf.flowtable import FlowTable, Span, TableLayout
from backend.pdf.fonts import register_fonts

PAGE = (420.0, 300.0)
MARGIN = 20.0
FRAME_H = PAGE[1] - 2 * MARGIN
FRAME_W = PAGE[0] - 2 * MARGIN


def build(story, page_size=PAGE) -> fitz.Document:
    """Lay the story out on small pages (frame without padding, like the report)."""
    register_fonts()
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=page_size, initialFontName="Sans")
    frame = Frame(MARGIN, MARGIN, page_size[0] - 2 * MARGIN, page_size[1] - 2 * MARGIN,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="small", frames=[frame], pagesize=page_size)])
    doc.build(story)
    return fitz.open(stream=buffer.getvalue(), filetype="pdf")


def make_table(texts, spans=(), keep_with_previous=False, bands=None) -> FlowTable:
    """Three columns: Group | Item | Detail. `texts` is a list of (group, item, detail)."""
    layout = TableLayout([80.0, 120.0, FRAME_W - 200.0], [styles.A4_CELL] * 3,
                         header_style=styles.A4_HEADER, frame_height=FRAME_H, group_rules=True,
                         repeat_columns=(0, 1))
    layout.set_header([["Group", "Item", "Detail"]])
    rows = [layout.row(row, band=(bands[i] if bands else i)) for i, row in enumerate(texts)]
    return FlowTable(layout, rows, list(spans), keep_with_previous=keep_with_previous)


def pages_with(doc, text):
    return [number for number, page in enumerate(doc, start=1) if text in page.get_text()]


def one_line_rows(count, start=0):
    return [("", f"ITEM{i:03d}", "SYNTHETIC detail") for i in range(start, start + count)]


def test_header_is_repeated_and_every_row_placed_once():
    doc = build([make_table(one_line_rows(60))])
    assert len(doc) > 2
    for page in doc:
        assert page.get_text().splitlines()[:3] == ["Group", "Item", "Detail"]
    text = "".join(page.get_text() for page in doc)
    for i in range(60):
        assert text.count(f"ITEM{i:03d}") == 1


def test_small_merged_group_moves_to_the_next_page_intact():
    table = make_table(one_line_rows(1))
    row_h = table.row_heights()[0]
    per_page = int((FRAME_H - table.layout.header_height()) // row_h)
    # a 3-row merged group starting one row before the end of page 1
    start = per_page - 1
    texts = one_line_rows(per_page + 5)
    texts[start] = ("SYNTHETIC GROUP", texts[start][1], texts[start][2])
    spans = [Span(start, 0, start + 2, 0, text="SYNTHETIC GROUP")]
    bands = [i if i < start else (start if i <= start + 2 else i) for i in range(len(texts))]
    doc = build([make_table(texts, spans, bands=bands)])
    group_items = [f"ITEM{i:03d}" for i in range(start, start + 3)]
    assert [pages_with(doc, item) for item in group_items] == [[2], [2], [2]]
    assert "(cont.)" not in "".join(page.get_text() for page in doc)
    assert pages_with(doc, f"ITEM{start - 1:03d}") == [1]


def test_large_merged_group_splits_and_repeats_its_value():
    texts = one_line_rows(40)
    texts[0] = ("SYNTHETIC BIG GROUP", texts[0][1], texts[0][2])
    spans = [Span(0, 0, 39, 0, text="SYNTHETIC BIG GROUP")]
    doc = build([make_table(texts, spans, bands=[0] * 40)])
    assert len(doc) >= 3
    for number, page in enumerate(doc, start=1):
        text = page.get_text()
        assert "SYNTHETIC BIG GROUP" in text.replace("\n", " "), number
        assert ("(cont.)" in text) == (number > 1), number


def test_row_taller_than_a_page_is_split_inside_the_row():
    detail = "\n".join(f"SYNTHETIC step {i:03d}" for i in range(80))
    texts = one_line_rows(3) + [("", "TALLITEM", detail)] + one_line_rows(3, start=3)
    doc = build([make_table(texts)])
    text = "".join(page.get_text() for page in doc)
    for i in range(80):
        assert text.count(f"SYNTHETIC step {i:03d}") == 1
    step_pages = pages_with(doc, "SYNTHETIC step")
    assert len(step_pages) >= 3
    assert pages_with(doc, "TALLITEM") == step_pages, "the row starts on page 1 and is identified on each page"
    assert pages_with(doc, "TALLITEM (cont.)") == step_pages[1:]


def test_merged_text_taller_than_a_page_falls_back_to_unmerged_cells():
    tall = "\n".join(f"SYNTHETIC merged line {i:03d}" for i in range(80))
    texts = [(tall, "ITEM000", "a"), ("", "ITEM001", "b"), ("", "ITEM002", "c"),
             ("SYNTHETIC NEXT GROUP", "ITEM003", "d"), ("", "ITEM004", "e")]
    spans = [Span(0, 0, 2, 0, text=tall), Span(3, 0, 4, 0, text="SYNTHETIC NEXT GROUP")]
    doc = build([make_table(texts, spans, bands=[0, 0, 0, 1, 1])])
    text = " ".join("".join(page.get_text() for page in doc).split())   # the narrow column wraps lines
    for i in range(80):
        assert f"SYNTHETIC merged line {i:03d}" in text
    for i in range(5):   # each row once; the split first row is also identified on later pages
        assert len(re.findall(rf"ITEM{i:03d}(?! \(cont\.\))", text)) == 1
    assert text.count("ITEM000 (cont.)") >= 1
    assert "SYNTHETIC NEXT GROUP" in text and "(cont.)" not in text.split("SYNTHETIC NEXT GROUP")[1]


def test_first_part_stays_with_its_heading():
    table = make_table(one_line_rows(1))
    row_h = table.row_heights()[0]
    header_h = table.layout.header_height()
    texts = one_line_rows(6)
    texts[0] = ("SYNTHETIC GROUP", texts[0][1], texts[0][2])
    spans = [Span(0, 0, 5, 0, text="SYNTHETIC GROUP")]

    def story(keep_with_previous):
        heading = Paragraph("SYNTHETIC HEADING", styles.HEADING_2)
        heading_h = heading.wrap(FRAME_W, FRAME_H)[1] + heading.getSpaceBefore() + heading.getSpaceAfter()
        # page 1 keeps room for the heading, the table header and three and a half rows
        filler = Spacer(1, FRAME_H - heading_h - header_h - 3.5 * row_h)
        return [filler, heading, make_table(texts, spans, keep_with_previous=keep_with_previous, bands=[0] * 6)]

    doc = build(story(keep_with_previous=True))
    assert pages_with(doc, "SYNTHETIC HEADING") == [1]
    assert pages_with(doc, "ITEM000") == [1], "the table starts under its heading"
    assert pages_with(doc, "ITEM005") == [2]
    # an ordinary table part moves a small merged group to the next page intact instead
    doc = build(story(keep_with_previous=False))
    assert pages_with(doc, "ITEM000") == [2]


def test_every_part_fits_the_space_it_was_split_for():
    detail = "\n".join(f"SYNTHETIC line {i}" for i in range(30))
    texts = [("", f"ITEM{i:03d}", detail if i % 7 == 0 else "short") for i in range(30)]
    remaining, available, parts = make_table(texts), 150.0, 0
    while remaining.wrap(FRAME_W, available)[1] > available:
        head, remaining = remaining.split(FRAME_W, available)
        assert head.wrap(FRAME_W, available)[1] <= available + 1e-3
        available = FRAME_H
        parts += 1
        assert parts < 50, "splitting must make progress"
    assert parts >= 2
