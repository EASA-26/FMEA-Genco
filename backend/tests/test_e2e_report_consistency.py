"""End-to-end consistency: the review screens and the exported PDF show the same report.

The review screens render the report JSON returned by the API, so these tests
sign in to the real FastAPI app (real parser, real PDF renderer, no fakes),
upload a workbook and check that every value the screens show is printed in
the right place of the PDF served by ``/api/report/pdf``:

* cover: Station, Date of Analysis and the blank PREPARED BY / APPROVED BY boxes;
* introduction: every Failure Details and Team Members field, row by row;
* per UOIR, the A3 analysis page(s): UOIR ID, Title, every note and every table
  cell in its own column and in workbook order;
* per UOIR, the A4 summary page: the three cards, the pie legend, the Existing vs
  Revised table, the Work-Centre table and the not-counted / duplicate notes;
* recommendation: UOIR headings, group headings and rows in order, nothing
  missing or repeated (a row cut by a page break is joined back together);
* page size of every section and "Page X of Y".

How the PDF is read (PyMuPDF): the section of a page comes from its section
title; each table part is found from its blue header fill and outline, its
columns and rows from the drawn grid lines, and every word goes to the cell that
contains its centre. Text is compared ignoring whitespace, because the PDF wraps
long values and adds break points inside long codes.

Workbooks (all SYNTHETIC, from tools/make_synthetic_workbook.py): the clean
workbook, an extension of it (warnings only: notes, a merged cell, a duplicate row,
a blank New Task, "&" and "<", a row taller than a page, tables over several pages),
the edge-case workbook (blocking errors) and the sample-like workbook, which has the
layout and quirks of a full engineer workbook with invented content. Sign-in uses a
SYNTHETIC password hashed for the test app only.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, replace
from datetime import date
from typing import Iterable, Optional, Sequence

import fitz  # PyMuPDF (test-only)
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.api.services import ReportServices
from backend.auth.passwords import hash_password
from backend.auth.service import MSG_NOT_SIGNED_IN
from backend.config.mapping import STANDARD_STRATEGY_CODES, normalise_header
from backend.main import create_app
from backend.pdf import styles as pdf_styles
from backend.tests.test_api_support import MISSING_DIST, TEST_CLIENT_HOSTS, make_settings

# --------------------------------------------------------------------------- #
# Sign-in (SYNTHETIC account for this test app only)
# --------------------------------------------------------------------------- #
E2E_USERNAME = "admin"
E2E_PASSWORD = "SYNTHETIC-e2e-consistency-password"
E2E_PASSWORD_HASH = hash_password(E2E_PASSWORD)

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Plain messages from CONTRACT.md section 4.
MSG_WRONG_TYPE = "Please upload an Excel workbook (.xlsx or .xlsm)."
MSG_NOT_A_WORKBOOK = (
    "This file could not be opened as an Excel workbook. Save it as .xlsx in Excel and try again."
)
MSG_EXPORT_BLOCKED = "Fix the errors listed before previewing or exporting."
MSG_NO_REPORT = "No workbook uploaded yet."
MSG_LOGIN_FAILED = "Incorrect username or password."

# --------------------------------------------------------------------------- #
# What the PDF looks like (CONTRACT.md section 5)
# --------------------------------------------------------------------------- #
REPORT_TITLE = "Failure Mode Effect Analysis (FMEA) Report"
A4_PORTRAIT = (595.3, 841.9)
A3_LANDSCAPE = (1190.6, 841.9)
EXPECTED_PAGE_KIND = {"cover": "A4 portrait", "intro": "A4 portrait", "analysis": "A3 landscape",
                      "summary": "A4 portrait", "recommendation": "A4 portrait"}
SECTION_KEYS = {
    "Introduction": "intro",
    "Analysis: FMEA Analysis": "analysis",
    "Analysis: FMEA Summary": "summary",
    "Recommendation": "recommendation",
}
PAGE_NUMBER = re.compile(r"Page \d+ of \d+")
CONT = "(cont.)"                       # marks a value repeated after a page break
SIGNING_LABELS = ("PREPARED BY:", "APPROVED BY:")
CARD_LABELS = ("Failure Mode", "Maintenance Task", "Task Executed")
CARD_LABEL_SIZE = 9.0
CARD_NUMBER_SIZE = 24.0
EMPTY_PIE_TEXT = "No strategy values to chart."
EMPTY_WORK_CENTRE_TEXT = "No rows with New Task set to Yes or No."
EMPTY_CODE = "—"

FAILURE_DETAILS_HEADERS = ("UOIR ID", "Title", "Faulty Date", "UOIR ID Date", "Corrective Action (CA)",
                           "Preventive Action (PA)", "Equipment")
TEAM_HEADERS = ("No", "Name", "Staff No", "Section")
STRATEGY_HEADERS = ("Code", "Strategy", "Existing", "New")
WORK_CENTRE_HEADERS = ("Work Centre", "Total", "Executed", "Pending")
RECOMMENDATION_HEADER_TEXT = "Failure Mode Recommendations Task Frequency"

HEADER_FILL = "#" + pdf_styles.TABLE_HEADER_FILL.hexval()[2:].lower()
BODY_TOP = pdf_styles.TOP_MARGIN - 3
BODY_BOTTOM_MARGIN = pdf_styles.BOTTOM_MARGIN - 3
SECTION_TITLE_SIZE = pdf_styles.SECTION_TITLE.fontSize
LINE_KINDS = (
    (pdf_styles.HEADING_2.fontSize, "h2"),
    (pdf_styles.HEADING_3.fontSize, "h3"),
    (pdf_styles.EMPTY_NOTE.fontSize, "note"),
)
NOTE_SIZE = pdf_styles.NOTE.fontSize
NOTE_COLOR = "#" + pdf_styles.NOTE.textColor.hexval()[2:].lower()

LINE_TOLERANCE = 2.5    # words whose tops differ by less than this are on one line
EDGE_TOLERANCE = 0.75   # grid lines closer than this are the same line


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def norm(text: Optional[str]) -> str:
    """Whitespace-normalised text (line breaks and runs of spaces become one space)."""
    return " ".join((text or "").split())


def compact(text: Optional[str]) -> str:
    """Text with all whitespace removed: wrapped text and break points inside long codes join back."""
    return "".join((text or "").split())


def same_text(shown: str, expected: str) -> bool:
    return compact(shown) == compact(expected)


def page_kind(page) -> str:
    size = (page.rect.width, page.rect.height)
    if all(abs(a - b) < 1 for a, b in zip(size, A4_PORTRAIT)):
        return "A4 portrait"
    if all(abs(a - b) < 1 for a, b in zip(size, A3_LANDSCAPE)):
        return "A3 landscape"
    return f"unexpected size {size[0]:.1f} x {size[1]:.1f}"


def _hex(color) -> Optional[str]:
    if color is None:
        return None
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in color[:3])


# --------------------------------------------------------------------------- #
# PDF geometry: words, styled lines, grid lines, table parts
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class Line:
    """One printed line with its type size, weight and colour."""

    text: str
    size: float
    bold: bool
    color: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class Segment:
    horizontal: bool
    x0: float
    y0: float
    x1: float
    y1: float


def reading_order(words: Iterable[Word]) -> str:
    """Words as read: lines top to bottom, each line left to right."""
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.y0, w.x0)):
        if lines and abs(word.y0 - lines[-1][0].y0) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return " ".join(w.text for line in lines for w in sorted(line, key=lambda w: w.x0))


def styled_lines(page) -> list[Line]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", ()):
            spans = [span for span in line["spans"] if span["text"].strip()]
            if not spans:
                continue
            x0, y0, x1, y1 = line["bbox"]
            lines.append(Line(
                text=norm("".join(span["text"] for span in line["spans"])),
                size=round(max(span["size"] for span in spans), 2),
                bold=any("bold" in span["font"].lower() for span in spans),
                color=f"#{spans[0]['color']:06x}",
                x0=x0, y0=y0, x1=x1, y1=y1,
            ))
    return sorted(lines, key=lambda line: (line.y0, line.x0))


def segments_of(drawings) -> list[Segment]:
    """Straight horizontal and vertical stroked lines (table grids, rules)."""
    found = []
    for drawing in drawings:
        if drawing.get("color") is None:
            continue
        for item in drawing["items"]:
            if item[0] != "l":
                continue
            a, b = item[1], item[2]
            if abs(a.y - b.y) < 0.05:
                found.append(Segment(True, min(a.x, b.x), a.y, max(a.x, b.x), a.y))
            elif abs(a.x - b.x) < 0.05:
                found.append(Segment(False, a.x, min(a.y, b.y), a.x, max(a.y, b.y)))
    return found


def _edges(values: Iterable[float], first: float, last: float) -> list[float]:
    edges = [first]
    for value in sorted(values):
        if value - edges[-1] > EDGE_TOLERANCE and last - value > EDGE_TOLERANCE:
            edges.append(value)
    edges.append(last)
    return edges


@dataclass
class TablePart:
    """The part of a report table drawn on one page (header repeated on every part)."""

    page: int                       # 1-based page number
    x0: float
    x1: float
    top: float
    header_bottom: float
    bottom: float
    columns: list[tuple[float, float]]
    header_words: list[Word]
    body_words: list[Word]
    rules: list[Segment]            # horizontal grid lines inside the body

    def contains(self, x: float, y: float) -> bool:
        return self.x0 - 1 <= x <= self.x1 + 1 and self.top - 1 <= y <= self.bottom + 1

    @property
    def header_text(self) -> str:
        return norm(" ".join(sorted(w.text for w in self.header_words)))

    def header_cells(self) -> list[str]:
        return [reading_order(w for w in self.header_words if left <= w.cx < right) for left, right in self.columns]

    def bands(self, column: int) -> list[tuple[float, float]]:
        """Top and bottom of each cell in a column (merged cells have no line inside)."""
        left, right = self.columns[column]
        centre = (left + right) / 2
        ys = [rule.y0 for rule in self.rules if rule.x0 - 0.5 <= centre <= rule.x1 + 0.5]
        edges = _edges(ys, self.header_bottom, self.bottom)
        return list(zip(edges, edges[1:]))

    def column_cells(self, column: int) -> list[tuple[float, str]]:
        left, right = self.columns[column]
        return [
            (top, reading_order(w for w in self.body_words if left <= w.cx < right and top <= w.cy < bottom))
            for top, bottom in self.bands(column)
        ]

    def rows(self) -> list[tuple[float, tuple[str, ...]]]:
        bands = [self.bands(c) for c in range(len(self.columns))]
        for c, other in enumerate(bands):
            same = len(other) == len(bands[0]) and all(
                abs(a[0] - b[0]) < EDGE_TOLERANCE for a, b in zip(bands[0], other))
            assert same, f"page {self.page}: table '{self.header_text}' has merged cells in column {c + 1}"
        cells = [[text for _, text in self.column_cells(c)] for c in range(len(self.columns))]
        return [(bands[0][r][0], tuple(column[r] for column in cells)) for r in range(len(bands[0]))]


def find_table_parts(page_number: int, drawings, words: list[Word], segments: list[Segment]) -> list[TablePart]:
    parts = []
    for drawing in drawings:
        if _hex(drawing.get("fill")) != HEADER_FILL or drawing.get("color") is not None:
            continue
        rect = drawing["rect"]
        if rect.width < 50 or rect.height < 8:
            continue
        outline = [s for s in segments
                   if not s.horizontal and abs(s.x0 - rect.x0) < 1 and abs(s.y0 - rect.y0) < 1]
        assert outline, f"page {page_number}: a table header without a table outline"
        bottom = max(s.y1 for s in outline)
        verticals = [s.x0 for s in segments
                     if not s.horizontal and rect.x0 + 1 < s.x0 < rect.x1 - 1
                     and s.y0 >= rect.y0 - 1 and s.y1 <= bottom + 1]
        xs = _edges(verticals, rect.x0, rect.x1)
        parts.append(TablePart(
            page=page_number,
            x0=rect.x0, x1=rect.x1, top=rect.y0, header_bottom=rect.y1, bottom=bottom,
            columns=list(zip(xs, xs[1:])),
            header_words=[w for w in words if rect.x0 <= w.cx <= rect.x1 and rect.y0 <= w.cy <= rect.y1],
            body_words=[w for w in words if rect.x0 <= w.cx <= rect.x1 and rect.y1 < w.cy < bottom],
            rules=[s for s in segments if s.horizontal and s.x0 >= rect.x0 - 1 and s.x1 <= rect.x1 + 1
                   and rect.y1 + 0.5 < s.y0 < bottom - 0.5],
        ))
    return sorted(parts, key=lambda part: part.top)


class PdfView:
    """Everything the tests read from the PDF, computed once per document."""

    def __init__(self, pdf: bytes):
        self.doc = fitz.open(stream=pdf, filetype="pdf")
        self.pages = [self.doc[i] for i in range(self.doc.page_count)]
        self.drawings = [page.get_drawings() for page in self.pages]
        self.words = [[Word(*w[:5]) for w in page.get_text("words")] for page in self.pages]
        self.lines = [styled_lines(page) for page in self.pages]
        self.segments = [segments_of(drawings) for drawings in self.drawings]
        self.parts = [
            find_table_parts(i + 1, self.drawings[i], self.words[i], self.segments[i])
            for i in range(len(self.pages))
        ]
        self.sections, self.titled = self._sections()

    def close(self) -> None:
        self.doc.close()

    def _sections(self) -> tuple[list[str], list[bool]]:
        sections, titled, current = [], [], "cover"
        for index, lines in enumerate(self.lines):
            titles = [line.text for line in lines if abs(line.size - SECTION_TITLE_SIZE) < 0.05]
            assert all(t in SECTION_KEYS for t in titles), f"page {index + 1}: unexpected title {titles}"
            assert len(titles) <= 1, f"page {index + 1}: several sections start on one page: {titles}"
            if index == 0:
                assert not titles, f"page 1 must be the cover, found {titles}"
            elif titles:
                current = SECTION_KEYS[titles[0]]
            sections.append(current)
            titled.append(bool(titles))
        return sections, titled

    def groups(self, section: str) -> list[list[int]]:
        """Page indexes of a section, one list per start of that section (one per UOIR)."""
        groups: list[list[int]] = []
        for index, (current, titled) in enumerate(zip(self.sections, self.titled)):
            if current != section:
                continue
            if titled:
                groups.append([])
            groups[-1].append(index)
        return groups

    def body_bottom(self, index: int) -> float:
        return self.pages[index].rect.height - BODY_BOTTOM_MARGIN

    def body_words(self, index: int) -> list[Word]:
        return [w for w in self.words[index] if w.y0 >= BODY_TOP and w.y1 <= self.body_bottom(index)]

    def body_lines(self, index: int) -> list[Line]:
        return [line for line in self.lines[index] if line.y0 >= BODY_TOP and line.y1 <= self.body_bottom(index)]

    def outside_tables(self, index: int) -> list[Line]:
        return [line for line in self.body_lines(index)
                if not any(part.contains(line.cx, line.cy) for part in self.parts[index])]


def key_value_pairs(words: Sequence[Word], top: float, bottom: float) -> list[tuple[str, str]]:
    """"Label : value" lines (aligned colons, values wrapping under the value) inside [top, bottom)."""
    region = [w for w in words if top <= w.cy < bottom]
    colons = sorted((w for w in region if w.text == ":"), key=lambda w: w.y0)
    if not colons:
        return []
    colons = [c for c in colons if abs(c.x0 - colons[0].x0) < 1.0]
    pairs = []
    for n, colon in enumerate(colons):
        row_top = colon.y0 - LINE_TOLERANCE
        row_bottom = colons[n + 1].y0 - LINE_TOLERANCE if n + 1 < len(colons) else bottom
        label = [w for w in region if w.x1 <= colon.x0 + 0.1 and abs(w.y0 - colon.y0) <= LINE_TOLERANCE]
        value = [w for w in region if w.x0 >= colon.x1 and row_top <= w.y0 < row_bottom]
        pairs.append((reading_order(label), reading_order(value)))
    return pairs


def assert_pairs(shown: list[tuple[str, str]], wanted: list[tuple[str, str]], where: str) -> None:
    assert [norm(label) for label, _ in shown] == [label for label, _ in wanted], (
        f"{where}: label lines differ. The PDF shows {shown!r}; the report has {wanted!r}")
    for (label, value), (_, expected) in zip(shown, wanted):
        assert same_text(value, expected), (
            f"{where}: '{label}' should be {expected!r}, the PDF shows {value!r}")


def stat_cards(lines: Sequence[Line]) -> list[tuple[Line, Line]]:
    """(label, big number) of each summary card, left to right."""
    cards = []
    numbers = sorted((line for line in lines if abs(line.size - CARD_NUMBER_SIZE) < 0.05), key=lambda l: l.x0)
    for number in numbers:
        labels = [line for line in lines if abs(line.size - CARD_LABEL_SIZE) < 0.05
                  and abs(line.x0 - number.x0) < 0.6 and 0 < number.y0 - line.y0 < 40]
        assert len(labels) == 1, f"card number {number.text!r} has labels {[l.text for l in labels]}"
        cards.append((labels[0], number))
    return cards


def read_legend(words: Sequence[Word], segments: Sequence[Segment]):
    """Rows (label, count, percent) of the pie legend and its total, or None when there is no legend."""
    heads = [(count, percent) for count in words if count.text == "Count"
             for percent in words if percent.text == "%" and abs(percent.y0 - count.y0) < 1
             and percent.x0 > count.x1]
    if not heads:
        return None
    assert len(heads) == 1, "more than one pie legend on the page"
    count_head, percent_head = heads[0]
    label_heads = [w for w in words if w.text == "Strategy" and abs(w.y0 - count_head.y0) < 1
                   and w.x1 < count_head.x0]
    assert len(label_heads) == 1, "pie legend header without 'Strategy'"
    label_head = label_heads[0]
    below = sorted((s for s in segments if s.horizontal and s.y0 > count_head.y1
                    and s.x0 < label_head.x0 and s.x1 > percent_head.x1 - 1), key=lambda s: s.y0)
    assert below, "pie legend without a rule under its header"
    head_rule = below[0]
    totals = sorted((w for w in words if w.text == "Total" and abs(w.x0 - label_head.x0) < 1
                     and w.y0 > head_rule.y0), key=lambda w: w.y0)
    assert totals, "pie legend without a Total row"
    total_word = totals[0]
    ys = [s.y0 for s in below if abs(s.x0 - head_rule.x0) < 0.5 and abs(s.x1 - head_rule.x1) < 0.5
          and s.y0 <= total_word.y0]
    edges = _edges(ys, ys[0], ys[-1]) if len(ys) > 1 else ys

    def in_legend(w: Word) -> bool:
        return head_rule.x0 <= w.cx <= head_rule.x1

    rows = []
    for top, bottom in zip(edges, edges[1:]):
        cell_words = [w for w in words if in_legend(w) and top <= w.cy < bottom]
        count = [w for w in cell_words if abs(w.x1 - count_head.x1) < 1.5]
        percent = [w for w in cell_words if abs(w.x1 - percent_head.x1) < 1.5]
        label = [w for w in cell_words if w not in count and w not in percent]
        rows.append((reading_order(label), reading_order(count), reading_order(percent)))
    total = [w for w in words if in_legend(w) and abs(w.cy - total_word.cy) < LINE_TOLERANCE
             and abs(w.x1 - count_head.x1) < 1.5]
    return rows, reading_order(total)


# --------------------------------------------------------------------------- #
# Ordered content of a section: headings, notes and table rows
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Item:
    kind: str                           # "h2" | "h3" | "note" | "text" | "row"
    text: str = ""
    cells: tuple[str, ...] = ()
    table: str = ""                     # header text of the row's table (sorted words)
    first_in_part: bool = False
    last_in_part: bool = False
    page: int = 0

    def describe(self) -> str:
        where = f" (page {self.page})" if self.page else ""
        if self.kind == "row":
            return f"row {list(self.cells)!r}{where}"
        return f"{self.kind} {self.text!r}{where}"


def header_key(labels: Iterable[str]) -> str:
    return norm(" ".join(sorted(" ".join(labels).split())))


def row_item(cells: Sequence[str], headers: Iterable[str]) -> Item:
    return Item("row", cells=tuple(cells), table=header_key(headers))


def part_items(part: TablePart) -> list[tuple[float, float, Item]]:
    rows = part.rows()
    return [
        (top, part.x0, Item("row", cells=cells, table=part.header_text, first_in_part=n == 0,
                            last_in_part=n == len(rows) - 1, page=part.page))
        for n, (top, cells) in enumerate(rows)
    ]


def section_items(view: PdfView, page_indexes: Sequence[int]) -> list[Item]:
    """Headings, notes and table rows of the given pages, in reading order.
    A heading that wraps over two lines is one item."""
    items: list[Item] = []
    for index in page_indexes:
        placed: list[tuple[float, float, Item]] = []
        for line in view.outside_tables(index):
            if abs(line.size - SECTION_TITLE_SIZE) < 0.05 and line.text in SECTION_KEYS:
                continue
            kind = next((k for size, k in LINE_KINDS if abs(line.size - size) < 0.05), "text")
            placed.append((line.y0, line.x0, Item(kind, text=line.text, page=index + 1)))
        for part in view.parts[index]:
            placed += part_items(part)
        for _, _, item in sorted(placed, key=lambda p: (p[0], p[1])):
            previous = items[-1] if items else None
            if (previous is not None and item.kind != "row" and previous.kind == item.kind
                    and previous.page == item.page):
                items[-1] = replace(previous, text=f"{previous.text} {item.text}")
            else:
                items.append(item)
    return items


def table_items(view: PdfView, page_indexes: Sequence[int], headers: Sequence[str]) -> list[Item]:
    key = header_key(headers)
    placed = []
    for index in page_indexes:
        for part in view.parts[index]:
            if part.header_text == key:
                assert len(part.columns) == len(headers), (
                    f"page {index + 1}: table '{key}' has {len(part.columns)} columns")
                assert [compact(c) for c in part.header_cells()] == [compact(h) for h in headers], (
                    f"page {index + 1}: header cells {part.header_cells()} should be {list(headers)}")
                placed += part_items(part)
    return [item for _, _, item in placed]


def same_item(shown: Item, wanted: Item) -> bool:
    if shown.kind != wanted.kind:
        return False
    if wanted.kind == "row":
        return (shown.table == wanted.table and len(shown.cells) == len(wanted.cells)
                and all(same_text(a, b) for a, b in zip(shown.cells, wanted.cells)))
    return norm(shown.text) == norm(wanted.text)


def join_split_row(head: Item, tail: Item) -> Item:
    """A row cut by a page break: the tail repeats identifying values followed by "(cont.)"."""
    cells = []
    for first, rest in zip(head.cells, tail.cells):
        if rest.endswith(CONT) and same_text(rest[: -len(CONT)], first):
            cells.append(first)
        else:
            cells.append(norm(f"{first} {rest}"))
    return replace(head, cells=tuple(cells), last_in_part=tail.last_in_part)


def assert_items(shown: list[Item], wanted: list[Item], where: str) -> None:
    """The PDF shows exactly the wanted items, in order: nothing missing, repeated or extra."""
    i = 0
    for n, want in enumerate(wanted):
        if i >= len(shown):
            pytest.fail(f"{where}: the PDF ends before item {n + 1} of {len(wanted)}: {want.describe()}")
        got = shown[i]
        if same_item(got, want):
            i += 1
            continue
        merged, j = got, i
        while (want.kind == "row" and merged.kind == "row" and shown[j].last_in_part and j + 1 < len(shown)
               and shown[j + 1].kind == "row" and shown[j + 1].first_in_part
               and shown[j + 1].table == got.table and shown[j + 1].page > shown[j].page):
            merged = join_split_row(merged, shown[j + 1])
            j += 1
            if same_item(merged, want):
                break
        if merged is not got and same_item(merged, want):
            i = j + 1
            continue
        pytest.fail(f"{where}: item {n + 1} of {len(wanted)} should be {want.describe()}, "
                    f"but the PDF shows {got.describe()}")
    if i < len(shown):
        pytest.fail(f"{where}: the PDF shows more than the report: {shown[i].describe()} "
                    f"(and {len(shown) - i - 1} more)")


def first_difference(shown: Sequence[str], wanted: Sequence[tuple[int, str]]) -> str:
    stream = compact("".join(shown))
    position = 0
    for source_row, text in wanted:
        key = compact(text)
        if stream.startswith(key, position):
            position += len(key)
            continue
        return (f"the value of Excel row {source_row} {text!r} is not next; "
                f"the PDF continues with {stream[position:position + 80]!r}")
    return f"the PDF has extra text {stream[position:position + 80]!r}"


# --------------------------------------------------------------------------- #
# SYNTHETIC workbook: the clean workbook extended with warnings and long tables
# --------------------------------------------------------------------------- #
EXTENDED_ROWS = 48
TALL_TASK_ROW = 20          # index of the generated row whose Task is taller than a page
EXTENDED_STRATEGIES = ("OC", "SR", "SD", "FF", "R-Spare", "NSM")


def build_extended_clean_workbook(tool) -> bytes:
    """The SYNTHETIC clean workbook plus everything that changes the layout but not
    exportability (warnings and info only)."""
    wb = tool.make_clean_workbook()

    team = wb["Team Member"]
    for column, value in enumerate([3, "Synthetic Person C & <D>", "00012345", "I&C"], start=1):
        team.cell(row=8, column=column, value=value)

    uoir = wb["UOIR"]
    second_row = [3, 602, tool.CLEAN_TITLE_602, date(2026, 4, 2), date(2026, 4, 20),
                  "SYNTHETIC second action line 1\nSYNTHETIC second action & <line 2>",
                  "SYNTHETIC stroke test & record travel", "Clean Valve Actuator"]
    for column, value in enumerate(second_row, start=1):
        uoir.cell(row=7, column=column, value=value)
    for ref in ("D7", "E7"):
        uoir[ref].number_format = "d-mmm-yy"

    t601 = wb[tool.CLEAN_TAB_601]
    extra_601 = [
        # Exact duplicate of row 3 (only No. differs): warning, counted once.
        tool.analysis_row(5, "Impeller wear", "Reduced flow", "OC", "Flow check", "1M", "SYNMECH",
                          "KKS-CLEAN-1", "No"),
        # Not NSM and New Task blank: warning, left out of the Existing/New counts.
        tool.analysis_row(6, "Gland packing leak & <drip>", "Water spray on the motor", "SD",
                          "Replace packing\nCheck the gland follower", "1Y", "SYNMECH", "KKS-CLEAN-2", None),
    ]
    for row, values in enumerate(extra_601, start=7):
        for column, value in enumerate(values, start=1):
            if value is not None:
                t601.cell(row=row, column=column, value=value)
    t601["D1"] = "SYNTHETIC RCA note & <check>\nsecond line of the note"
    t601["B12"] = "SYNTHETIC root cause - impeller wear"

    t602 = wb[tool.CLEAN_TAB_602]
    t602.merge_cells("B3:B4")       # Failure Mode merged over two rows: info, value carried down
    for i in range(EXTENDED_ROWS):
        strategy = EXTENDED_STRATEGIES[i % len(EXTENDED_STRATEGIES)]
        task = f"SYNTHETIC task {i + 1:02d}: inspect & record <value>"
        if i == TALL_TASK_ROW:
            task += "\n" + "\n".join(f"SYNTHETIC step {k:02d} of a very long procedure" for k in range(1, 91))
        values = tool.analysis_row(
            i + 3, f"SYNTHETIC failure mode {i + 1:02d}", f"SYNTHETIC failure effect {i + 1:02d}", strategy,
            task, "3M" if i % 2 else "6M", "SYNINCS" if i % 4 else "SYNMECH",
            "KKS-CLEAN-3" if i % 3 else "KKS-CLEAN-4/ZZ020-120",
            None if strategy == "NSM" else ("Yes" if i % 2 else "No"),
            remark=("SYNTHETIC remark LAB10AA101/LAB10AA102/LAB10AA103/LAB10AA104/LAB10AA105"
                    if i % 5 == 0 else None),
        )
        for column, value in enumerate(values, start=1):
            if value is not None:
                t602.cell(row=i + 5, column=column, value=value)
    return tool.to_bytes(wb)


# --------------------------------------------------------------------------- #
# The real app, signed in
# --------------------------------------------------------------------------- #
def make_app():
    app = create_app(
        settings=make_settings(admin_password_hash=E2E_PASSWORD_HASH),
        frontend_dist=MISSING_DIST,
        extra_local_hosts=TEST_CLIENT_HOSTS,
    )
    assert isinstance(app.state.services, ReportServices), "the real parser and PDF renderer must be used"
    return app


def sign_in(client: TestClient):
    return client.post("/api/auth/login", json={"username": E2E_USERNAME, "password": E2E_PASSWORD})


def upload(client: TestClient, data: bytes, filename: str, content_type: str = XLSX_CONTENT_TYPE):
    return client.post("/api/workbook", files={"file": (filename, data, content_type)})


@dataclass
class Exported:
    """One workbook taken through the API: what the screens get and what the PDF prints."""

    filename: str
    expected_pdf_filename: str
    report: dict
    report_again: dict
    inline: object
    attachment: object
    view: PdfView


def export_through_api(data: bytes, filename: str, expected_pdf_filename: str) -> Exported:
    with TestClient(make_app()) as client:
        signed_in = sign_in(client)
        assert signed_in.status_code == 200, signed_in.text
        uploaded = upload(client, data, filename)
        assert uploaded.status_code == 200, uploaded.text
        again = client.get("/api/report")
        assert again.status_code == 200, again.text
        inline = client.get("/api/report/pdf?download=0")
        attachment = client.get("/api/report/pdf?download=1")
    assert inline.status_code == 200, inline.text
    return Exported(
        filename=filename,
        expected_pdf_filename=expected_pdf_filename,
        report=uploaded.json(),
        report_again=again.json(),
        inline=inline,
        attachment=attachment,
        view=PdfView(inline.content),
    )


@pytest.fixture(scope="module")
def clean_export(clean_workbook_bytes):
    exported = export_through_api(clean_workbook_bytes, "SYNTHETIC_clean.xlsx",
                                  "FMEA_Report_SYNTHETIC_Clean_Station_2026-06-15.pdf")
    yield exported
    exported.view.close()


@pytest.fixture(scope="module")
def extended_export(synthetic_tool):
    exported = export_through_api(build_extended_clean_workbook(synthetic_tool), "SYNTHETIC_clean_extended.xlsx",
                                  "FMEA_Report_SYNTHETIC_Clean_Station_2026-06-15.pdf")
    yield exported
    exported.view.close()


@pytest.fixture(scope="module")
def sample_export(sample_workbook_bytes):
    exported = export_through_api(sample_workbook_bytes, "SYNTHETIC_sample_like.xlsx",
                                  "FMEA_Report_SYNTHETIC_Station_S9_2025-10-06.pdf")
    yield exported
    exported.view.close()


EXPORTS = {
    "SYNTHETIC-clean": "clean_export",
    "SYNTHETIC-clean-extended": "extended_export",
    "SYNTHETIC-sample-like": "sample_export",
}


@pytest.fixture(scope="module", params=list(EXPORTS))
def exported(request) -> Exported:
    return request.getfixturevalue(EXPORTS[request.param])


# --------------------------------------------------------------------------- #
# Scenarios 1 and 3: exportable workbooks, screens == PDF
# --------------------------------------------------------------------------- #
def test_extended_synthetic_workbook_is_exportable_with_warnings(extended_export):
    report = extended_export.report
    assert report["can_export"] is True
    codes = {issue["code"] for issue in report["issues"]}
    assert {"DUPLICATE_ROW", "NEW_TASK_BLANK", "MERGED_CELLS_CARRIED"} <= codes
    uoir_601, uoir_602 = report["uoirs"]
    assert uoir_601["summary"]["duplicate_rows"] == [7]
    assert [row["source_row"] for row in uoir_601["summary"]["not_counted"]] == [8]
    assert [note["cell"] for note in uoir_601["notes"]] == ["D1", "B12"]
    assert uoir_602["equipment"] == ["Clean Valve", "Clean Valve Actuator"]
    assert len(uoir_602["analysis"]["rows"]) == 2 + EXTENDED_ROWS
    assert uoir_602["analysis"]["merged"], "the merged Failure Mode must reach the report"


def test_report_json_and_pdf_download_round_trip(exported):
    report = exported.report
    assert exported.report_again == report, "GET /api/report must return the uploaded report unchanged"
    assert report["source_filename"] == exported.filename
    assert report["can_export"] is True
    assert [i for i in report["issues"] if i["severity"] == "error"] == []
    assert report["pdf_filename"] == exported.expected_pdf_filename

    for response, disposition in ((exported.inline, "inline"), (exported.attachment, "attachment")):
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["cache-control"] == "no-store"
        header = response.headers["content-disposition"]
        match = re.fullmatch(r'(inline|attachment); filename="([^"]+)"', header)
        assert match, header
        assert match.group(1) == disposition
        assert match.group(2) == report["pdf_filename"]
    assert exported.inline.content == exported.attachment.content, "preview and download must be the same file"
    assert exported.inline.content.startswith(b"%PDF")

    metadata = exported.view.doc.metadata
    assert metadata["title"] == REPORT_TITLE
    assert metadata["subject"] == norm(report["station"])


def test_page_sizes_sections_and_page_numbers(exported):
    view, report = exported.view, exported.report
    starts = ["cover"] + [section for section, titled in zip(view.sections, view.titled) if titled]
    assert starts == ["cover", "intro"] + ["analysis", "summary"] * len(report["uoirs"]) + ["recommendation"]
    assert view.titled[1], "the introduction starts on page 2"

    total = len(view.pages)
    header = norm(f"FMEA Report · {report['station']}")
    for number, (page, section) in enumerate(zip(view.pages, view.sections), start=1):
        assert page_kind(page) == EXPECTED_PAGE_KIND[section], f"page {number} ({section})"
        lines = view.lines[number - 1]
        numbers = [line for line in lines if PAGE_NUMBER.search(line.text)]
        running = [line for line in lines if line.text.startswith("FMEA Report")]
        if number == 1:
            assert numbers == [] and running == [], "the cover has no header or page number"
            continue
        assert [line.text for line in numbers] == [f"Page {number} of {total}"], f"page {number}"
        assert numbers[0].y0 > view.body_bottom(number - 1), f"page {number}: page number is in the footer"
        assert page.rect.width - numbers[0].x1 < 50, f"page {number}: page number is right-aligned"
        assert [line.text for line in running] == [header], f"page {number}: running header"
        assert running[0].y1 < BODY_TOP, f"page {number}: running header is above the body"


def test_cover_shows_station_date_and_blank_signing_boxes(exported):
    view, report = exported.view, exported.report
    cover = view.pages[0]
    boxes = sorted(
        (d["rect"] for d in view.drawings[0]
         if _hex(d.get("fill")) == "#ffffff" and d["rect"].width > 200 and d["rect"].height > 80),
        key=lambda rect: rect.x0,
    )
    assert len(boxes) == len(SIGNING_LABELS), f"signing boxes found: {boxes}"

    pairs = key_value_pairs(view.words[0], 0, min(box.y0 for box in boxes))
    assert_pairs(pairs, [("Station", report["station"]), ("Date of Analysis", report["analysis_date_text"])],
                 "cover")

    for box, label in zip(boxes, SIGNING_LABELS):
        inside = [w for w in view.words[0] if box.x0 <= w.cx <= box.x1 and box.y0 <= w.cy <= box.y1]
        assert reading_order(inside) == label, f"the {label} box must hold only its label"
        # The full-page background gradient is an image behind everything; nothing else may sit on a box.
        images = [info for info in cover.get_image_info()
                  if fitz.Rect(info["bbox"]).intersects(box)
                  and abs(fitz.Rect(info["bbox"]).get_area()) < 0.5 * abs(cover.rect.get_area())]
        assert images == [], f"the {label} box must be blank"


def test_introduction_shows_every_failure_detail_and_team_member(exported):
    view, report = exported.view, exported.report
    groups = view.groups("intro")
    assert len(groups) == 1
    assert report["failure_details"] and report["team"], "precondition: both tables have rows"

    wanted = [Item("h2", text="Failure Details")]
    wanted += [
        row_item([d["uoir_id"], d["title"], d["faulty_date_text"], d["uoir_date_text"], d["corrective_action"],
                  d["preventive_action"], d["equipment"]], FAILURE_DETAILS_HEADERS)
        for d in report["failure_details"]
    ]
    wanted.append(Item("h2", text="Team Members"))
    wanted += [row_item([m["no"], m["name"], m["staff_no"], m["section"]], TEAM_HEADERS) for m in report["team"]]

    shown = section_items(view, groups[0])
    assert_items(shown, wanted, "Introduction")
    # Column by column headers on every part of both tables.
    table_items(view, groups[0], FAILURE_DETAILS_HEADERS)
    table_items(view, groups[0], TEAM_HEADERS)


def test_analysis_pages_show_every_note_and_cell_in_its_column(exported):
    view, report = exported.view, exported.report
    groups = view.groups("analysis")
    assert len(groups) == len(report["uoirs"])
    for uoir, pages in zip(report["uoirs"], groups):
        where = f"UOIR {uoir['uoir_id']} analysis (pages {pages[0] + 1}-{pages[-1] + 1})"
        table = uoir["analysis"]
        assert table is not None and table["rows"], f"precondition: {where} has a table"

        first = pages[0]
        parts = [part for index in pages for part in view.parts[index]]
        assert parts, f"{where}: no table printed"
        assert len(view.parts[first]) <= 1 and all(len(view.parts[i]) == 1 for i in pages[1:]), (
            f"{where}: one table part per page expected")
        kv_bottom = min((part.top for part in view.parts[first]), default=view.body_bottom(first))
        wanted_pairs = [("UOIR ID", uoir["uoir_id"]), ("Title", uoir["title"])]
        wanted_pairs += [("Note", note["text"]) for note in uoir["notes"]]
        assert_pairs(key_value_pairs(view.body_words(first), BODY_TOP, kv_bottom), wanted_pairs, where)

        columns = table["columns"]
        for part in parts:
            assert len(part.columns) == len(columns), f"{where}, page {part.page}: column count"
            header = part.header_cells()
            assert [compact(h) for h in header] == [compact(c) for c in columns], (
                f"{where}, page {part.page}: header {header} should be {columns}")

        spread = {c for m in table["merged"] if m["last_col"] > m["first_col"]
                  for c in range(m["first_col"], m["last_col"] + 1)}
        everything = compact(" ".join(reading_order(part.body_words) for part in parts))
        for c, name in enumerate(columns):
            wanted = [(row["source_row"], row["cells"][c]) for row in table["rows"]
                      if c < len(row["cells"]) and compact(row["cells"][c])]
            if c in spread:
                # Text merged across columns is printed over several columns: check it is there.
                for source_row, text in wanted:
                    assert compact(text) in everything, f"{where}: {name} of row {source_row} {text!r} missing"
                continue
            shown: list[str] = []
            for part in parts:
                for _, text in part.column_cells(c):
                    if not compact(text):
                        continue
                    if text.endswith(CONT):
                        repeated = text[: -len(CONT)]
                        assert shown and same_text(repeated, shown[-1]), (
                            f"{where}, page {part.page}, column {name!r}: {text!r} repeats a value "
                            f"that is not the previous one ({shown[-1] if shown else None!r})")
                        continue
                    shown.append(text)
            assert compact("".join(shown)) == compact("".join(text for _, text in wanted)), (
                f"{where}, column {name!r}: {first_difference(shown, wanted)}")


def test_summary_pages_show_cards_pie_tables_and_notes(exported):
    view, report = exported.view, exported.report
    groups = view.groups("summary")
    assert len(groups) == len(report["uoirs"])
    for uoir, pages in zip(report["uoirs"], groups):
        where = f"UOIR {uoir['uoir_id']} summary (pages {pages[0] + 1}-{pages[-1] + 1})"
        summary = uoir["summary"]
        assert summary is not None, f"precondition: {where} has a summary"
        first = pages[0]
        lines = view.body_lines(first)

        cards = stat_cards(lines)
        assert [(label.text, number.text) for label, number in cards] == list(zip(CARD_LABELS, [
            str(summary["failure_mode_count"]), str(summary["maintenance_task_count"]),
            str(summary["task_executed_count"])])), f"{where}: cards"

        kv_bottom = min(label.y0 for label, _ in cards)
        assert_pairs(key_value_pairs(view.body_words(first), BODY_TOP, kv_bottom),
                     [("UOIR ID", uoir["uoir_id"]), ("Title", uoir["title"])], where)

        texts = [line.text for index in pages for line in view.body_lines(index)]
        for heading in ("Existing vs Revised", "Recommended Strategy", "Work-Centre Execution"):
            assert heading in texts, f"{where}: heading {heading!r} missing"

        legend = read_legend(view.words[first], view.segments[first])
        if summary["pie"]:
            assert legend is not None, f"{where}: pie legend missing"
            rows, total = legend
            wanted = [(s["label"] or s["code"], str(s["count"]), f"{s['percent']:.1f}%") for s in summary["pie"]]
            assert len(rows) == len(wanted), f"{where}: legend rows {rows} should be {wanted}"
            for shown_row, wanted_row in zip(rows, wanted):
                assert all(same_text(a, b) for a, b in zip(shown_row, wanted_row)), (
                    f"{where}: legend row {shown_row} should be {wanted_row}")
            assert total == str(summary["pie_total"]), f"{where}: legend total"
        else:
            assert legend is None and EMPTY_PIE_TEXT in texts, f"{where}: empty pie message"

        strategy_rows = [row_item([row["code"] or EMPTY_CODE, row["label"], str(row["existing"]), str(row["new"])],
                                  STRATEGY_HEADERS) for row in summary["strategy_rows"]]
        assert_items(table_items(view, pages, STRATEGY_HEADERS), strategy_rows, f"{where}, Existing vs Revised")

        centre_rows = [row_item([row["work_centre"], str(row["total"]), str(row["executed"]), str(row["pending"])],
                                WORK_CENTRE_HEADERS) for row in summary["work_centre_rows"]]
        assert_items(table_items(view, pages, WORK_CENTRE_HEADERS), centre_rows, f"{where}, Work-Centre Execution")
        if not centre_rows:
            assert EMPTY_WORK_CENTRE_TEXT in texts, f"{where}: empty work-centre message"

        known = {header_key(STRATEGY_HEADERS), header_key(WORK_CENTRE_HEADERS)}
        others = [part.header_text for index in pages for part in view.parts[index] if part.header_text not in known]
        assert others == [], f"{where}: unexpected tables {others}"

        wanted_notes = []
        for row in summary["not_counted"]:
            details = ", ".join(part for part in (row["strategy"], row["trade"]) if part)
            place = f"row {row['source_row']}" + (f" ({details})" if details else "")
            wanted_notes.append(f"Not counted: {place} — {row['reason'].rstrip('.')}.")
        wanted_notes += [f"Row {r} is identical to an earlier row and was counted once."
                         for r in summary["duplicate_rows"]]
        shown_notes = [line.text for index in pages for line in view.outside_tables(index)
                       if abs(line.size - NOTE_SIZE) < 0.05 and not line.bold and line.color == NOTE_COLOR]
        assert norm(" ".join(shown_notes)) == norm(" ".join(wanted_notes)), f"{where}: notes under the tables"


def test_recommendation_section_shows_every_group_and_row_once_in_order(exported):
    view, report = exported.view, exported.report
    groups = view.groups("recommendation")
    assert len(groups) == 1

    wanted: list[Item] = []
    for uoir in report["uoirs"]:
        wanted.append(Item("h2", text=f"UOIR ID {uoir['uoir_id']}: {uoir['title']}"))
        assert uoir["recommendations"], f"precondition: UOIR {uoir['uoir_id']} has recommendations"
        for group in uoir["recommendations"]:
            assert group["heading"], "precondition: every group has a heading"
            wanted.append(Item("h3", text=group["heading"]))
            wanted += [Item("row", cells=(row["failure_mode"], row["task"], row["frequency"]),
                            table=header_key([RECOMMENDATION_HEADER_TEXT])) for row in group["rows"]]
    assert_items(section_items(view, groups[0]), wanted, "Recommendation")


# --------------------------------------------------------------------------- #
# Scenario 3: expected results of the SYNTHETIC sample-like workbook, through the API JSON
# --------------------------------------------------------------------------- #
def _uoir(report: dict, uoir_id: str) -> dict:
    return next(u for u in report["uoirs"] if u["uoir_id"] == uoir_id)


def _strategies(uoir: dict) -> list[tuple[str, int, int, int]]:
    return [(r["code"], r["existing"], r["new"], r["total"]) for r in uoir["summary"]["strategy_rows"]]


def _full_strategy_table(listed: dict, extra: Sequence[str]) -> list[tuple[str, int, int, int]]:
    codes = list(STANDARD_STRATEGY_CODES) + list(extra)
    return [(code, *listed.get(code, (0, 0, 0))) for code in codes]


def _work_centres(uoir: dict) -> list[tuple[str, int, int, int]]:
    return [(w["work_centre"], w["total"], w["executed"], w["pending"]) for w in uoir["summary"]["work_centre_rows"]]


def _counts(uoir: dict) -> tuple[int, int, int, int]:
    s = uoir["summary"]
    return s["failure_mode_count"], s["maintenance_task_count"], s["task_executed_count"], s["pie_total"]


def _groups(uoir: dict) -> list[tuple[str, int]]:
    return [(g["heading"], len(g["rows"])) for g in uoir["recommendations"]]


def test_sample_workbook_matches_expected_results_through_api(sample_export):
    report = sample_export.report
    assert report["station"] == "SYNTHETIC Station S9"
    assert report["analysis_date"] == "2025-10-06"
    assert report["analysis_date_text"] == "6 October 2025"
    assert report["can_export"] is True
    # Date of Analysis is taken from B3 as written; it is never compared with the fault dates.
    assert report["issues"] == []
    assert report["pdf_filename"] == "FMEA_Report_SYNTHETIC_Station_S9_2025-10-06.pdf"

    assert [m["source_row"] for m in report["team"]] == list(range(6, 13))
    # Staff numbers stay whole-number text (no ".0", one of them is stored as a float).
    assert all(re.fullmatch(r"\d{8}", m["staff_no"]) for m in report["team"])
    assert [m["staff_no"] for m in report["team"]] == [str(70001001 + n) for n in range(7)]

    assert [(d["uoir_id"], d["source_row"]) for d in report["failure_details"]] == [
        ("712", 5), ("705", 6), ("748", 7)]
    assert report["failure_details"][0]["equipment"] == "SYNTHETIC Lube Oil Pressure Switch Rack"
    assert report["failure_details"][2]["faulty_date"] == "2026-04-27"
    assert [u["uoir_id"] for u in report["uoirs"]] == ["712", "705", "748"]

    u712 = _uoir(report, "712")
    assert u712["sheet_name"] == "UOIR ID 712 - Turbine ESD (Emer"
    assert u712["analysis"]["header_row"] == 2
    assert len(u712["analysis"]["columns"]) == 22
    assert [r["source_row"] for r in u712["analysis"]["rows"]] == list(range(3, 15))
    assert u712["analysis"]["merged"] == []
    assert _counts(u712) == (12, 12, 6, 12)
    assert _strategies(u712) == _full_strategy_table(
        {"OC": (2, 3, 5), "SD": (2, 0, 2), "FF": (0, 1, 1), "R-SPARE": (2, 1, 3), "R-HARDWARE": (0, 1, 1)},
        ["R-HARDWARE"])
    assert _work_centres(u712) == [("SYNELEC", 4, 2, 2), ("SYNINCS", 3, 1, 2), ("SYNOPER", 3, 1, 2),
                                   ("SYNMECH", 2, 2, 0)]
    assert _groups(u712) == [("SYNTHETIC Lube Oil Pressure Switch Rack, SYN10/AB020-120", 11),
                             ("SYNTHETIC Lube Oil Pressure Switch Rack, SYN11/AC300-390 XS01-02", 1)]
    assert [r["source_row"] for r in u712["recommendations"][1]["rows"]] == [4]
    assert [(n["cell"], n["text"]) for n in u712["notes"]] == [
        ("B18", "Root Cause (SYNTHETIC) - lube oil pressure switch diaphragm fatigue")]
    assert u712["summary"]["not_counted"] == [] and u712["summary"]["duplicate_rows"] == []

    u705 = _uoir(report, "705")
    assert u705["sheet_name"] == "UOIR ID 705 - Deaerator Level T"
    assert [r["source_row"] for r in u705["analysis"]["rows"]] == list(range(3, 10))
    assert [r["cells"][0] for r in u705["analysis"]["rows"]] == [""] * 7, "No. column blank (non-breaking spaces)"
    assert _counts(u705) == (7, 6, 2, 7)
    assert _strategies(u705) == _full_strategy_table(
        {"OC": (2, 1, 3), "SR": (0, 1, 1), "FF": (0, 1, 1), "NSM": (0, 0, 1), "R-SOFTWARE": (0, 1, 1)},
        ["R-SOFTWARE"])
    assert [t["strategy_raw"] for t in u705["tasks"] if t["strategy_code"] == "R-SOFTWARE"] == ["R-software"]
    assert _work_centres(u705) == [("SYNINCS", 5, 2, 3), ("SYNMECH", 1, 0, 1)]
    assert u705["summary"]["not_counted"] == []
    assert not [i for i in report["issues"] if i["code"] == "NEW_TASK_BLANK" and i["uoir_id"] == "705"]
    assert u705["notes"] == []
    assert _groups(u705) == [("SYNTHETIC Deaerator Level Transmitter, SYN30/CP101-102", 7)]

    u748 = _uoir(report, "748")
    assert u748["sheet_name"] == "UOIR ID 748 - SYNTHETIC Condens"
    assert [r["source_row"] for r in u748["analysis"]["rows"]] == list(range(3, 12))
    assert _counts(u748) == (9, 9, 4, 9)
    assert _strategies(u748) == _full_strategy_table(
        {"OC": (3, 1, 4), "SR": (0, 1, 1), "SD": (1, 0, 1), "FF": (0, 1, 1), "R-SPARE": (0, 1, 1),
         "R-PRO": (0, 1, 1)}, ["R-PRO"])
    assert _work_centres(u748) == [("SYNINCS", 5, 3, 2), ("SYNBOIL", 2, 1, 1), ("SYNOPER", 2, 0, 2)]
    assert [(n["cell"], n["text"]) for n in u748["notes"]] == [
        ("C1", "RCA (SYNTHETIC) - recirculation valve hunting at low load. Actuator linkage worn")]
    assert _groups(u748) == [("SYNTHETIC Condensate Recirculation Valve, SYN40AA310/320", 9)]

    for uoir in report["uoirs"]:
        assert round(sum(s["percent"] for s in uoir["summary"]["pie"]), 1) == 100.0


# --------------------------------------------------------------------------- #
# Scenario 2: blocking errors -> located issues and no PDF
# --------------------------------------------------------------------------- #
def test_edge_workbook_lists_located_errors_and_refuses_the_pdf(edge_workbook_bytes, synthetic_tool):
    with TestClient(make_app()) as client:
        assert sign_in(client).status_code == 200
        uploaded = upload(client, edge_workbook_bytes, "SYNTHETIC_edge_cases.xlsx")
        assert uploaded.status_code == 200, uploaded.text
        report = uploaded.json()
        assert client.get("/api/report").json() == report
        pdf_responses = [client.get(f"/api/report/pdf?download={flag}") for flag in ("0", "1")]

    assert report["can_export"] is False
    issues = report["issues"]
    order = ["error", "warning", "info"]
    assert [i["severity"] for i in issues] == sorted((i["severity"] for i in issues), key=order.index)
    errors = [i for i in issues if i["severity"] == "error"]
    assert errors

    workbook = load_workbook(io.BytesIO(edge_workbook_bytes))
    for issue in errors:
        assert issue["message"].strip() and "Traceback" not in issue["message"], issue
        assert issue["sheet"] in workbook.sheetnames, issue
        assert isinstance(issue["row"], int) and issue["row"] >= 1, issue
        assert issue["column"], issue
        cell = re.fullmatch(r"([A-Z]{1,3})(\d+)", issue["cell"] or "")
        assert cell and int(cell.group(2)) == issue["row"], issue
        sheet = workbook[issue["sheet"]]
        headers_above = [sheet[f"{cell.group(1)}{r}"].value for r in range(1, issue["row"])]
        assert normalise_header(issue["column"]) in [normalise_header(h) for h in headers_above], (
            f"column {issue['column']!r} is not the header of {issue['cell']} on {issue['sheet']!r}")

    assert {(i["code"], i["sheet"], i["row"], i["column"], i["cell"]) for i in errors} == {
        ("NEW_TASK_INVALID", synthetic_tool.EDGE_TAB_501, 7, "New Task", "S7"),
        ("REQUIRED_VALUE_BLANK", synthetic_tool.EDGE_TAB_501, 8, "Failure Effect", "C8"),
        ("REQUIRED_VALUE_BLANK", synthetic_tool.EDGE_TAB_502, 7, "Trade", "H7"),
    }

    for response in pdf_responses:
        assert response.status_code == 409
        assert response.headers["content-type"].startswith("application/json")
        assert "content-disposition" not in response.headers
        assert response.json() == {"detail": MSG_EXPORT_BLOCKED, "error_count": len(errors)}


# --------------------------------------------------------------------------- #
# Scenario 4: wrong files and no sign-in
# --------------------------------------------------------------------------- #
def _synthetic_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SYNTHETIC.txt", "SYNTHETIC zip archive that is not a workbook")
    return buffer.getvalue()


def test_non_excel_upload_is_refused_with_a_plain_message(clean_workbook_bytes):
    refused = [
        ("SYNTHETIC_notes.txt", b"SYNTHETIC plain text, not a workbook", "text/plain", MSG_WRONG_TYPE),
        ("SYNTHETIC_table.csv", b"UOIR ID,Title\n1,SYNTHETIC\n", "text/csv", MSG_WRONG_TYPE),
        ("SYNTHETIC_report.pdf", b"%PDF-1.4\n% SYNTHETIC\n", "application/pdf", MSG_WRONG_TYPE),
        ("SYNTHETIC_old_format.xls", b"\xd0\xcf\x11\xe0SYNTHETIC", "application/vnd.ms-excel", MSG_WRONG_TYPE),
        ("SYNTHETIC_renamed_text.xlsx", b"SYNTHETIC plain text renamed to .xlsx", XLSX_CONTENT_TYPE,
         MSG_NOT_A_WORKBOOK),
        ("SYNTHETIC_renamed_zip.xlsm", _synthetic_zip(), XLSX_CONTENT_TYPE, MSG_NOT_A_WORKBOOK),
    ]
    with TestClient(make_app()) as client:
        assert sign_in(client).status_code == 200
        assert client.get("/api/report").json() == {"detail": MSG_NO_REPORT}
        for filename, data, content_type, message in refused:
            response = upload(client, data, filename, content_type)
            assert response.status_code == 400, filename
            assert response.json() == {"detail": message}, filename
        assert client.get("/api/report").status_code == 404, "a refused upload creates no report"

        good = upload(client, clean_workbook_bytes, "SYNTHETIC_clean.xlsx")
        assert good.status_code == 200
        for filename, data, content_type, message in refused:
            response = upload(client, data, filename, content_type)
            assert response.status_code == 400 and response.json() == {"detail": message}, filename
        assert client.get("/api/report").json() == good.json(), "a refused upload keeps the previous report"
        assert client.get("/api/report/pdf?download=0").status_code == 200


def test_requests_without_sign_in_are_refused(clean_workbook_bytes):
    protected = [
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/report"),
        ("DELETE", "/api/workbook"),
        ("GET", "/api/report/pdf?download=0"),
        ("GET", "/api/report/pdf?download=1"),
    ]

    def assert_refused(client: TestClient) -> None:
        for method, path in protected:
            response = client.request(method, path)
            assert response.status_code == 401, (method, path)
            assert response.json() == {"detail": MSG_NOT_SIGNED_IN}, (method, path)
        response = upload(client, clean_workbook_bytes, "SYNTHETIC_clean.xlsx")
        assert response.status_code == 401
        assert response.json() == {"detail": MSG_NOT_SIGNED_IN}

    with TestClient(make_app()) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert_refused(client)

        wrong = client.post("/api/auth/login", json={"username": E2E_USERNAME, "password": "SYNTHETIC-wrong"})
        assert wrong.status_code == 401
        assert wrong.json() == {"detail": MSG_LOGIN_FAILED}
        assert_refused(client)

        # Signed in, a report exists; after signing out it is no longer reachable.
        assert sign_in(client).status_code == 200
        assert upload(client, clean_workbook_bytes, "SYNTHETIC_clean.xlsx").status_code == 200
        assert client.get("/api/report/pdf?download=1").status_code == 200
        assert client.post("/api/auth/logout").status_code == 204
        assert_refused(client)
