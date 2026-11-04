"""Adversarial PDF checks: SYNTHETIC reports built to break layout or crash the renderer.

Each test here guards a defect found in review (a crash, text running off the
page, a missing glyph, a heading left alone at the foot of a page) or proves that
unusual but possible workbook content still produces a complete report.
"""
from __future__ import annotations

import re

import fitz  # PyMuPDF (test-only)
import pytest
from reportlab.platypus import Paragraph

from backend.config.mapping import strategy_color, strategy_label
from backend.pdf import styles
from backend.pdf.cover import signature_box_rects
from backend.pdf.flowtable import MAX_HEADER_FRACTION, FlowTable, Span, TableLayout
from backend.pdf.render import render_pdf
from backend.pdf.tables import MIN_FLEXIBLE_WIDTH, analysis_column_widths, analysis_table, side_padding_for
from backend.pdf.text import SYMBOL_FONT, escape, font_size_to_fit_words
from backend.report.builder import build_report
from backend.report.models import (
    Note,
    PieSlice,
    RecommendationGroup,
    RecommendationRow,
    StrategyRow,
)
from backend.tests.test_pdf_fixtures import (
    ADVERSARIAL_STATION,
    ANALYSIS_COLUMNS,
    COL,
    FLAG_HEADERS,
    LONG_STRATEGY_CODE,
    WIDE_FLAG_TEXT,
    adversarial_report,
    analysis_markers,
    column_letters,
    compact,
    normal_report,
    page_kind,
    page_lines,
    page_sections,
    pages_per_uoir,
    recommendation_markers,
    section_starts,
    shown_on_pages,
    words_outside_body,
)


def _open(report) -> fitz.Document:
    return fitz.open(stream=render_pdf(report), filetype="pdf")


def _section_text(doc, sections, wanted) -> str:
    return "\n".join(page.get_text() for page, s in zip(doc, sections) if s == wanted)


def _body_lines(page) -> list[str]:
    return [line for line in page_lines(page) if not line.startswith(("FMEA Report", "Page "))]


def _margins(page) -> tuple[float, float, float]:
    side = styles.A3_SIDE_MARGIN if page_kind(page) == "A3L" else styles.A4_SIDE_MARGIN
    return side, styles.TOP_MARGIN, styles.BOTTOM_MARGIN


# --------------------------------------------------------------------------- #
# The adversarial report
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def report():
    return adversarial_report()


@pytest.fixture(scope="module")
def doc(report):
    document = _open(report)
    yield document
    document.close()


@pytest.fixture(scope="module")
def sections(doc):
    return page_sections(doc)


def test_sections_page_sizes_and_numbering(doc, sections, report):
    assert section_starts(doc) == ["cover", "intro"] + ["analysis", "summary"] * 3 + ["recommendation"]
    expected_kind = {"cover": "A4P", "intro": "A4P", "analysis": "A3L", "summary": "A4P", "recommendation": "A4P"}
    total = len(doc)
    header = f"FMEA Report · {ADVERSARIAL_STATION}"
    for number, (page, section) in enumerate(zip(doc, sections), start=1):
        assert page_kind(page) == expected_kind[section], f"page {number}"
        if number == 1:
            continue
        lines = page_lines(page)
        assert lines.count(header) == 1, f"page {number}: station with & and < shown literally in the header"
        assert _body_lines(page), f"page {number} is blank"
        assert re.findall(r"Page (\d+) of (\d+)", page.get_text()) == [(str(number), str(total))]
    assert doc.metadata["subject"] == ADVERSARIAL_STATION
    assert compact(f"Station : {ADVERSARIAL_STATION}") in compact(doc[0].get_text())


def test_every_row_exactly_once(doc, sections, report):
    analysis = compact(_section_text(doc, sections, "analysis"))
    for marker in analysis_markers(report):
        assert analysis.count(marker) == 1, marker
    recommendation = compact(_section_text(doc, sections, "recommendation"))
    markers = recommendation_markers(report)
    assert len(markers) == 512
    for marker in markers:
        assert recommendation.count(marker) == 1, marker


def test_every_analysis_cell_line_is_on_its_uoirs_pages(doc, report):
    groups = pages_per_uoir(doc, "analysis")
    assert len(groups) == len(report.uoirs)
    for uoir, pages in zip(report.uoirs, groups):
        text = compact("".join(page.get_text() for page in pages)).replace("(cont.)", "")
        if uoir.analysis is None:
            assert "No analysis worksheet is linked to this UOIR" in pages[0].get_text()
            continue
        for row in uoir.analysis.rows:
            for cell in row.cells:
                for line in cell.split("\n"):
                    assert compact(line) in text, (uoir.uoir_id, row.source_row, line)
        for page in pages:   # the header repeats on every A3 page
            page_text = compact(page.get_text())
            assert all(compact(h) in page_text for h in ANALYSIS_COLUMNS)


def test_wide_flag_text_stays_in_its_column_complete_and_in_order(doc, report):
    """Read each narrow flag column top to bottom over all pages: the text inside the
    column's edges must be exactly the workbook cells in order (a row split across
    pages continues where it stopped; nothing spills into the next column)."""
    table = report.uoirs[0].analysis
    widths = analysis_column_widths(table.columns, styles.A3_FRAME_WIDTH)
    pages = pages_per_uoir(doc, "analysis")[0]
    for flag in FLAG_HEADERS:
        col = COL[flag]
        left = styles.A3_SIDE_MARGIN + sum(widths[:col])
        right = left + widths[col]
        shown = ""
        for page in pages:
            words = sorted((w for w in page.get_text("words") if left - 0.5 <= w[0] and w[2] <= right + 0.5),
                           key=lambda w: (w[1], w[0]))
            header = next(i for i, w in enumerate(words) if w[4] == flag)   # skip notes above the table
            shown += "".join(w[4] for w in words[header + 1:])
        assert shown == "".join(compact(row.cells[col]) for row in table.rows), flag


def test_nothing_leaves_the_page_body(doc):
    for number, page in enumerate(doc, start=1):
        if number > 1:
            assert words_outside_body(page, *_margins(page)) == [], f"page {number}"


def test_thirty_notes_are_listed(doc, report):
    pages = pages_per_uoir(doc, "analysis")[0]
    lines = [line for page in pages for line in page_lines(page)]
    assert lines.count("Note") == 30
    text = " ".join(" ".join(page.get_text().split()) for page in pages)
    for note in report.uoirs[0].notes:
        assert note.text.strip() in text


def test_analysis_table_with_columns_but_no_rows():
    base = normal_report()
    table = base.uoirs[0].analysis.model_copy(update={"rows": [], "merged": []})
    doc = _open(_normal_with(analysis=table))
    page = next(page for page, s in zip(doc, page_sections(doc)) if s == "analysis")
    text = compact(page.get_text())
    assert all(compact(h) in text for h in ANALYSIS_COLUMNS)
    assert "The analysis worksheet has no data rows." in page.get_text()


def test_uoir_without_analysis_or_summary(doc):
    summary_pages = pages_per_uoir(doc, "summary")[1]
    assert "No summary is available for this UOIR." in summary_pages[0].get_text()
    assert "UOIR ID 8002: SYNTHETIC UOIR without a linked worksheet" in " ".join(
        page.get_text() for page in doc)


def test_long_strategy_label_forty_work_centres_and_notes(doc, report):
    pages = pages_per_uoir(doc, "summary")[0]
    text = compact("".join(page.get_text() for page in pages))
    label = compact(strategy_label(LONG_STRATEGY_CODE))
    assert text.count(label) == 2, "legend and Existing vs Revised table"
    lines = [line for page in pages for line in page_lines(page)]
    for i in range(40):
        assert lines.count(f"SYNTRADE{i:02d}") == 1
    summary = report.uoirs[0].summary
    assert sum(1 for line in lines if line.startswith("Not counted: row ")) == len(summary.not_counted)
    assert sum(1 for line in lines if "is identical to an earlier row" in line) == len(summary.duplicate_rows)


def test_forty_line_ca_and_pa_cells_are_complete(doc, sections, report):
    text = " ".join(_section_text(doc, sections, "intro").split())
    for detail in report.failure_details:
        for line in detail.corrective_action.split("\n") + detail.preventive_action.split("\n"):
            assert len(re.findall(re.escape(line) + r"(?!\d)", text)) == 1, line


def test_five_hundred_rows_in_one_group_repeat_the_two_row_header(doc, sections):
    pages = [page for page, s in zip(doc, sections) if s == "recommendation"]
    assert len(pages) > 10
    for page in pages:
        lines = page_lines(page)
        index = lines.index("Failure Mode")
        assert lines[index + 1:index + 4] == ["Recommendations", "Task", "Frequency"]


# --------------------------------------------------------------------------- #
# Crashes found in review
# --------------------------------------------------------------------------- #
def _normal_with(**uoir_update):
    base = normal_report()
    return base.model_copy(update={"uoirs": [base.uoirs[0].model_copy(update=uoir_update)]})


def test_legend_with_sixty_strategies_flows_over_pages():
    """A legend taller than a page used to raise LayoutError (no PDF at all)."""
    base = normal_report()
    codes = [f"R-SYN{i:02d}" for i in range(60)]
    pie = [PieSlice(code=c, label=strategy_label(c), count=1, percent=1.7, color=strategy_color(c)) for c in codes]
    summary = base.uoirs[0].summary.model_copy(update={"pie": pie, "pie_total": 60})
    doc = _open(_normal_with(summary=summary))
    sections = page_sections(doc)
    pages = [page for page, s in zip(doc, sections) if s == "summary"]
    assert len(pages) >= 2
    lines = [line for page in pages for line in page_lines(page)]
    for c in codes:
        assert lines.count(strategy_label(c)) == 1
    assert "Recommended Strategy" in page_lines(pages[0]) and "R-SYN00 - Redesign Syn00" in page_lines(pages[0])
    continuation = _body_lines(pages[1])
    assert {"Strategy", "Count", "%"} <= set(continuation[:4]), "legend header repeated on the next page"
    assert lines.count("Total") >= 2 and "60" in lines


def test_many_strategy_rows_and_tall_legend_labels_render():
    base = normal_report()
    codes = [f"R-SYN{i:02d}" for i in range(45)]
    long_label = "SYNTHETIC " + "very long strategy name " * 60
    pie = [PieSlice(code=c, label=f"{c} {long_label}", count=1, percent=2.2, color=strategy_color(c)) for c in codes]
    rows = [StrategyRow(code=c, label=strategy_label(c), existing=1, new=0, total=1,
                        color=strategy_color(c), standard=False) for c in codes]
    summary = base.uoirs[0].summary.model_copy(update={"pie": pie, "pie_total": 45, "strategy_rows": rows})
    doc = _open(_normal_with(summary=summary))
    text = compact(_section_text(doc, page_sections(doc), "summary"))
    for c in codes:
        assert compact(f"{c} {long_label}") in text


def test_long_header_label_is_shrunk_so_the_table_still_renders():
    """A header cell taller than a page used to raise LayoutError."""
    base = normal_report()
    table = base.uoirs[0].analysis.model_copy(deep=True)
    table.columns[COL["Remark"]] = "SYNTHETIC remark header " * 400
    layout = analysis_table(table, styles.A3_FRAME_WIDTH).layout
    assert layout.header_height() <= MAX_HEADER_FRACTION * styles.FRAME_HEIGHT + 1
    doc = _open(_normal_with(analysis=table))
    first = next(page for page, s in zip(doc, page_sections(doc)) if s == "analysis")
    text = compact(first.get_text())
    assert "AR9101N000" in text and "Failure Mode" in first.get_text()
    # the short headers keep the normal size: only the long cell is shrunk
    sizes = {span["size"] for block in first.get_text("dict")["blocks"] for line in block.get("lines", [])
             for span in line["spans"] if span["text"].strip() == "Task"}
    assert sizes == {styles.A3_TABLE_FONT_SIZE}


@pytest.mark.parametrize("extra_columns", [8, 80])
def test_many_columns_render_every_value(extra_columns):
    """More columns than fit their padding used to raise a negative-width error."""
    base = normal_report()
    table = base.uoirs[0].analysis.model_copy(deep=True)
    table.columns = table.columns + [f"SYNX{i}" for i in range(extra_columns)]
    table.column_letters = column_letters(len(table.columns))
    for r, row in enumerate(table.rows):
        row.cells = row.cells + [f"V{r}X{i}" for i in range(extra_columns)]
    doc = _open(_normal_with(analysis=table))
    text = compact(_section_text(doc, page_sections(doc), "analysis"))
    for r in range(len(table.rows)):
        for i in range(extra_columns):
            assert f"V{r}X{i}" in text


def test_side_padding_never_exceeds_the_narrowest_column():
    widths = analysis_column_widths([f"SYNTHETIC {i}" for i in range(400)], styles.A3_FRAME_WIDTH)
    side = side_padding_for(widths)
    assert side >= 0 and min(widths) - 2 * side > 0
    assert side_padding_for(analysis_column_widths(ANALYSIS_COLUMNS, styles.A3_FRAME_WIDTH)) == 2.5


def test_extra_columns_keep_short_columns_readable():
    columns = ANALYSIS_COLUMNS + [f"SYNTHETIC Extra {i}" for i in range(8)]
    widths = dict(zip(columns, analysis_column_widths(columns, styles.A3_FRAME_WIDTH)))
    assert sum(widths.values()) == pytest.approx(styles.A3_FRAME_WIDTH)
    assert widths["No."] == pytest.approx(24.0)   # already below the floor: never squeezed further
    assert widths["New Task"] >= MIN_FLEXIBLE_WIDTH
    assert widths["Task"] > widths["Failure Mode"] > widths["Trade"]


def test_long_unbroken_station_name_wraps_inside_the_cover():
    station = "SYNTHETIC" + "Z" * 400
    doc = _open(normal_report().model_copy(update={"station": station, "uoirs": []}))
    cover = doc[0]
    cards_top = cover.rect.height - max(y + h for _, y, _, h in signature_box_rects())
    words = cover.get_text("words")
    station_words = [w for w in words if "ZZZ" in w[4]]
    assert station_words
    for x0, y0, x1, y1, word, *_ in station_words:
        assert x1 <= cover.rect.width - 44 + 1, f"{word[:12]}… runs off the page"
        assert y1 < cards_top
    assert compact(station) in compact(cover.get_text())


# --------------------------------------------------------------------------- #
# Pie colours
# --------------------------------------------------------------------------- #
def _filled_shapes(page) -> list[tuple[str, float, float]]:
    shapes = []
    for drawing in page.get_drawings():
        if drawing.get("fill") is not None:
            colour = "#%02x%02x%02x" % tuple(round(v * 255) for v in drawing["fill"])
            shapes.append((colour, drawing["rect"].width, drawing["rect"].height))
    return shapes


@pytest.mark.parametrize("slice_count", [1, 6])
def test_each_slice_colour_is_one_wedge_and_one_legend_swatch(slice_count):
    base = normal_report()
    summary = base.uoirs[0].summary
    pie = summary.pie[:slice_count]
    if slice_count == 1:
        pie = [pie[0].model_copy(update={"percent": 100.0})]
    summary = summary.model_copy(update={"pie": pie, "pie_total": sum(s.count for s in pie)})
    doc = _open(_normal_with(summary=summary))
    page = next(page for page, s in zip(doc, page_sections(doc)) if s == "summary")
    shapes = _filled_shapes(page)
    slice_colours = {s.color.lower() for s in pie}
    assert len(slice_colours) == len(pie)
    for colour in slice_colours:
        mine = [(w, h) for c, w, h in shapes if c == colour]
        swatches = [shape for shape in mine if round(shape[0]) == 9 and round(shape[1]) == 9]
        wedges = [shape for shape in mine if max(shape) > 20]
        assert len(swatches) == 1 and len(wedges) == 1, (colour, mine)
    palette = {"#1a5a9a", "#1e6fbf", "#f4f8fc", "#ffffff"}   # accent bars, table header, zebra/cards
    assert {c for c, _, _ in shapes} <= slice_colours | palette


# --------------------------------------------------------------------------- #
# Text fidelity
# --------------------------------------------------------------------------- #
def test_tick_marks_use_the_symbol_font():
    assert escape("OK ✓ & ✗") == f'OK <font name="{SYMBOL_FONT}">✓</font> &amp; <font name="{SYMBOL_FONT}">✗</font>'
    assert escape("90°C ±5% µm Ω – “x” • →") == "90°C ±5% µm Ω – “x” • →"   # Liberation Sans has these
    base = normal_report()
    table = base.uoirs[0].analysis.model_copy(deep=True)
    table.rows[0].cells[COL["H"]] = "✓"
    doc = _open(_normal_with(analysis=table))
    first = next(page for page, s in zip(doc, page_sections(doc)) if s == "analysis")
    assert SYMBOL_FONT in [font[3] for font in first.get_fonts()]
    for page in doc:   # everything else is still the embedded Liberation Sans
        for _, ext, _, basefont, *_ in page.get_fonts(full=True):
            assert "LiberationSans" in basefont or basefont == SYMBOL_FONT


def test_markup_like_text_is_shown_literally():
    base = normal_report()
    table = base.uoirs[0].analysis.model_copy(deep=True)
    literal = 'SYNTHETIC <b>bold</b> <br/> &amp; &#169; <font size="40">big</font> ]]>'
    table.rows[0].cells[COL["Task"]] = literal
    doc = _open(_normal_with(analysis=table))
    assert compact(literal) in compact(_section_text(doc, page_sections(doc), "analysis"))


def test_slightly_too_wide_word_is_shrunk_in_that_cell_only():
    width = 30.0
    size = font_size_to_fit_words("Frequency", "Sans", 7.5, width, min_size=6.0)
    assert 6.0 <= size < 7.5
    assert font_size_to_fit_words("short", "Sans", 7.5, width, min_size=6.0) == 7.5
    assert font_size_to_fit_words(WIDE_FLAG_TEXT, "Sans", 7.5, width, min_size=6.0) == 7.5   # breaks instead
    layout = TableLayout([36.0, 36.0], [styles.A3_CELL, styles.A3_CELL], padding=(3.0, 3.0, 2.0, 2.0))
    assert layout.cell("Frequency", 0).style.fontSize == size
    assert layout.cell("6M", 1).style.fontSize == styles.A3_TABLE_FONT_SIZE


def test_one_row_merge_is_not_repeated_when_its_row_splits():
    """Found by randomised layouts: a horizontal merge that fitted above a page break
    was drawn again, in full, under the break."""
    from backend.tests.test_pdf_flowtable import FRAME_H, FRAME_W, build

    layout = TableLayout([80.0, 120.0, FRAME_W - 200.0], [styles.A4_CELL] * 3, header_style=styles.A4_HEADER,
                         frame_height=FRAME_H, repeat_columns=(0,))
    layout.set_header([["Group", "Item", "Detail"]])
    tall = "\n".join(f"SYNTALL{i:03d}" for i in range(60))
    merged = "\n".join(f"SYNMERGED{i}" for i in range(3))
    rows = [layout.row(["SYNFIRST", "a", "b"], band=0),
            layout.row([tall, merged, ""], band=1, merge_last_cols={1: 2}),
            layout.row(["SYNLAST", "c", "d"], band=2)]
    doc = build([FlowTable(layout, rows, [Span(1, 1, 1, 2, text=merged)])])
    assert len(doc) >= 3
    text = "".join(page.get_text() for page in doc)
    for i in range(3):
        assert text.count(f"SYNMERGED{i}") == 1
    for i in range(60):
        assert text.count(f"SYNTALL{i:03d}") == 1


@pytest.mark.parametrize("seed", range(8))
def test_randomised_tables_place_every_line_exactly_once(seed):
    """Random SYNTHETIC tables on small pages: vertical and one-row merges, cells from
    one to ninety lines, merged text taller than a page, any starting height.
    (Seed 7 reproduces the duplicated one-row merge.)"""
    import random

    from reportlab.platypus import Spacer

    from backend.tests.test_pdf_flowtable import MARGIN, build

    rng = random.Random(seed)
    page_size = rng.choice([(420.0, 300.0), (420.0, 500.0), (595.0, 842.0)])
    frame_w, frame_h = page_size[0] - 2 * MARGIN, page_size[1] - 2 * MARGIN
    n = rng.randint(1, 60)
    layout = TableLayout([70.0, 70.0, frame_w - 200.0, 60.0], [styles.A4_CELL] * 4, header_style=styles.A4_HEADER,
                         frame_height=frame_h, group_rules=True, repeat_columns=(0, 1))
    layout.set_header([["Group", "Item", "Detail", "Extra"]])
    texts = [["", f"R{i:03d}", "\n".join(f"L{i:03d}x{k:02d}" for k in range(rng.choice([1, 1, 2, 3, 8, 40, 90]))), ""]
             for i in range(n)]
    spans, bands, i, group = [], [0] * n, 0, 0
    while i < n:
        size = min(rng.choice([1, 1, 2, 3, 5, 20]), n - i)
        if size > 1 or rng.random() < 0.3:
            texts[i][0] = "\n".join(f"G{group:03d}y{k:03d}" for k in range(rng.choice([1, 2, 10, 60, 120])))
            if size > 1:
                spans.append(Span(i, 0, i + size - 1, 0, text=texts[i][0]))
        for r in range(i, i + size):
            bands[r] = group
        if size == 1 and rng.random() < 0.2:
            texts[i][2] = texts[i][2] or f"L{i:03d}x00"
            spans.append(Span(i, 2, i, 3, text=texts[i][2]))
        i += size
        group += 1
    merge_last = {}
    for span in spans:
        merge_last.setdefault(span.first_row, {})[span.first_col] = span.last_col
    rows = [layout.row(texts[r], bands[r], merge_last.get(r)) for r in range(n)]
    table = FlowTable(layout, rows, spans, keep_with_previous=rng.random() < 0.5)
    story = [Spacer(1, rng.uniform(0, frame_h * 0.95)),
             Paragraph("SYNTHETIC heading", styles.HEADING_2), table]
    doc = build(story, page_size=page_size)

    full = "\n".join(page.get_text() for page in doc)
    flat = " ".join(full.split())
    for r in range(n):
        assert len(re.findall(rf"R{r:03d}(?! \(cont\.\))", flat)) == 1, f"row R{r:03d}"
        for k in range(len(texts[r][2].split("\n"))):
            assert full.count(f"L{r:03d}x{k:02d}") == 1, f"L{r:03d}x{k:02d}"
    for line in "\n".join(t[0] for t in texts).split("\n"):
        assert not line or line in full, line
    for page in doc:
        assert words_outside_body(page, MARGIN, MARGIN, MARGIN) == [], f"page {page.number + 1}"


def test_empty_merged_cell_is_not_marked_continued():
    layout = TableLayout([80.0, 200.0], [styles.A4_CELL] * 2, header_style=styles.A4_HEADER, frame_height=200)
    layout.set_header([["Group", "Item"]])
    rows = [layout.row(["", f"SYNITEM{i:02d}"], band=0) for i in range(40)]
    table = FlowTable(layout, rows, [Span(0, 0, 39, 0, text="")])
    head, tail = table.split(280.0, 200.0)
    assert tail._cell(0, 0) is None


# --------------------------------------------------------------------------- #
# Headings near the foot of a page
# --------------------------------------------------------------------------- #
def _recommendation_rows(start, count, tall_every=0):
    return [
        RecommendationRow(source_row=start + i, failure_mode="SYNTHETIC failure mode",
                          task=f"SYNREC{start + i:04d} SYNTHETIC task"
                          + ("\nSYNTHETIC second line\nSYNTHETIC third line" if tall_every and i % tall_every == 0 else ""),
                          frequency="1M", new_task="yes")
        for i in range(count)
    ]


@pytest.mark.parametrize("first_group_rows", range(30, 52))
def test_recommendation_headings_stay_with_their_first_rows(first_group_rows):
    base = normal_report()
    groups = [
        RecommendationGroup(equipment="SYN", kks="K0", heading="SYNHEAD G0", rows=_recommendation_rows(0, first_group_rows, 3)),
        RecommendationGroup(equipment="SYN", kks="K1", heading="SYNHEAD G1", rows=_recommendation_rows(1000, 3)),
    ]
    second = base.uoirs[1].model_copy(update={"analysis": None, "summary": None, "recommendations": [
        RecommendationGroup(equipment="SYN", kks="K2", heading="SYNHEAD G2", rows=_recommendation_rows(2000, 3))]})
    first = base.uoirs[0].model_copy(update={"analysis": None, "summary": None, "recommendations": groups})
    doc = _open(base.model_copy(update={"uoirs": [first, second], "failure_details": [], "team": []}))
    sections = page_sections(doc)
    pages = [page for page, s in zip(doc, sections) if s == "recommendation"]

    def page_of(text):
        found = [i for i, page in enumerate(pages) if text in page.get_text()]
        assert len(found) == 1, text
        return found[0]

    assert page_of("SYNHEAD G1") == page_of("SYNREC1000")
    assert page_of("SYNHEAD G2") == page_of("SYNREC2000")
    assert page_of("UOIR ID 9102") == page_of("SYNHEAD G2")
    for page in doc.pages(1):
        assert _body_lines(page), f"page {page.number + 1} is blank"
    for page in pages:
        assert _body_lines(page)[-1] not in {"SYNHEAD G1", "SYNHEAD G2", "Failure Mode", "Frequency"}


@pytest.mark.parametrize("extra_strategy_rows", range(0, 22, 2))
def test_summary_headings_stay_with_their_content(extra_strategy_rows):
    base = normal_report()
    summary = base.uoirs[0].summary
    rows = list(summary.strategy_rows) + [
        StrategyRow(code=f"R-S{i}", label=strategy_label(f"R-S{i}"), existing=0, new=1, total=1,
                    color=strategy_color(f"R-S{i}"), standard=False) for i in range(extra_strategy_rows)]
    uoir = base.uoirs[0].model_copy(update={"analysis": None, "recommendations": [],
                                            "summary": summary.model_copy(update={"strategy_rows": rows})})
    doc = _open(base.model_copy(update={"uoirs": [uoir], "failure_details": [], "team": []}))
    pages = [page for page, s in zip(doc, page_sections(doc)) if s == "summary"]
    for page in doc.pages(1):
        assert _body_lines(page), f"page {page.number + 1} is blank"
    for page in pages:
        lines = _body_lines(page)
        if "Work-Centre Execution" in lines:
            assert "SYNINCS" in lines[lines.index("Work-Centre Execution"):]
        if "Existing vs Revised" in lines:
            assert "Total" in lines[lines.index("Existing vs Revised"):]
        assert lines[-1] not in {"Work-Centre Execution", "Existing vs Revised", "Pending", "New"}
    if extra_strategy_rows == 0:
        assert len(pages) == 1, "a summary that fits stays on one page"


@pytest.mark.parametrize("note_count", range(30, 75, 4))
def test_analysis_table_header_is_never_left_without_rows(note_count):
    notes = [Note(cell=f"B{i}", text=f"SYNTHETIC note {i}") for i in range(note_count)]
    doc = _open(_normal_with(notes=notes, summary=None, recommendations=[]))
    for page, section in zip(doc, page_sections(doc)):
        if section == "analysis" and "RecommendedStrategy" in compact(page.get_text()):
            assert re.search(r"AR9101N\d{3}", page.get_text()), "table header shown with at least one row"


# --------------------------------------------------------------------------- #
# Parser output end to end (SYNTHETIC workbooks from tools/make_synthetic_workbook.py)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("workbook", ["edge_workbook_bytes", "clean_workbook_bytes"])
def test_synthetic_workbook_renders_completely(workbook, request):
    report = build_report(request.getfixturevalue(workbook), "SYNTHETIC_workbook.xlsx")
    doc = _open(report)
    assert section_starts(doc) == ["cover", "intro"] + ["analysis", "summary"] * len(report.uoirs) + ["recommendation"]
    sections = page_sections(doc)

    def section_pages(wanted):
        return [page.get_text() for page, s in zip(doc, sections) if s == wanted]

    for uoir, pages in zip(report.uoirs, pages_per_uoir(doc, "analysis")):
        texts = [page.get_text() for page in pages]
        cells = [cell for row in (uoir.analysis.rows if uoir.analysis else []) for cell in row.cells]
        for value in cells + list(uoir.analysis.columns if uoir.analysis else []) + [n.text for n in uoir.notes]:
            for line in value.split("\n"):
                assert shown_on_pages(line, texts), (uoir.uoir_id, line)
    intro = section_pages("intro")
    for detail in report.failure_details:
        for value in (detail.uoir_id, detail.title, detail.faulty_date_text, detail.uoir_date_text,
                      detail.corrective_action, detail.preventive_action, detail.equipment):
            for line in value.split("\n"):
                assert shown_on_pages(line, intro), line
    for member in report.team:
        assert all(shown_on_pages(v, intro) for v in (member.no, member.name, member.staff_no, member.section))
    recommendation = section_pages("recommendation")
    for uoir in report.uoirs:
        for group in uoir.recommendations:
            assert shown_on_pages(group.heading, recommendation)
            for row in group.rows:
                for line in (row.failure_mode + "\n" + row.task + "\n" + row.frequency).split("\n"):
                    assert shown_on_pages(line, recommendation), line
