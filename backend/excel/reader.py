"""Open an uploaded workbook in memory and read its cells as clean text.

openpyxl's read-only mode is used because the engineers' workbooks carry a very
large `Notifications` sheet that the report never needs. Read-only mode does not
expose merged cells or sheet visibility, so those come straight from the xlsx
XML parts instead (an xlsx file is a zip archive of XML documents).

Nothing here decides what is an error: this module only turns the file into
values. The rules live in `backend.report.builder`.
"""
from __future__ import annotations

import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

import openpyxl
from openpyxl.utils.cell import get_column_letter, range_boundaries

from backend.report.formatting import format_date

OPEN_ERROR_MESSAGE = (
    "This file could not be opened as an Excel workbook. Save it as .xlsx in Excel and try again."
)


class WorkbookOpenError(Exception):
    """The upload is not a readable Excel workbook (the message is shown to the user)."""

    def __init__(self, message: str = OPEN_ERROR_MESSAGE) -> None:
        super().__init__(message)
        self.message = message


# --------------------------------------------------------------------------- #
# Cell text
# --------------------------------------------------------------------------- #
_ZERO_PAD_FORMAT = re.compile(r"^0+$")
_SPACES_AND_TABS = re.compile(r"[ \t]+")


def clean_text(value: object, number_format: str | None = None) -> str:
    """Display text of a cell value, as the engineer would read it.

    Non-breaking spaces count as spaces, line breaks are kept, runs of spaces
    inside a line collapse, and whitespace-only cells become "". Whole numbers
    lose the ".0" Excel stores, and a zero-padding number format such as
    "00000000" keeps its leading zeros (staff numbers).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (datetime, date)):
        return format_date(value)
    if isinstance(value, time):
        return f"{value.hour:02d}:{value.minute:02d}"
    if isinstance(value, int):
        return _zero_pad(str(value), number_format)
    if isinstance(value, float):
        if value.is_integer():
            return _zero_pad(str(int(value)), number_format)
        return _plain_decimal(value)
    return _clean_string(str(value))


def value_key(value: object, number_format: str | None = None) -> str:
    """Comparison key: clean text with all whitespace collapsed; case is kept."""
    return text_key(clean_text(value, number_format))


def text_key(text: str) -> str:
    """`value_key` for text that is already clean."""
    return " ".join(text.split())


def _clean_string(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACES_AND_TABS.sub(" ", line).strip() for line in text.split("\n")]
    start, end = 0, len(lines)
    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1
    return "\n".join(lines[start:end])


def _zero_pad(digits: str, number_format: str | None) -> str:
    fmt = (number_format or "").strip()
    if not _ZERO_PAD_FORMAT.match(fmt):
        return digits
    # Excel pads the digits and keeps the sign in front: -5 with "0000" shows "-0005".
    sign, number = ("-", digits[1:]) if digits.startswith("-") else ("", digits)
    return sign + number.zfill(len(fmt))


def _plain_decimal(value: float) -> str:
    """Fixed-point text without an exponent or trailing zeros (0.000125, not 1.25e-04)."""
    try:
        text = format(Decimal(repr(value)), "f")
    except (InvalidOperation, ValueError):
        return repr(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


# --------------------------------------------------------------------------- #
# Sheet contents
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CellRange:
    """A merged block in Excel coordinates (1-based, inclusive)."""

    min_row: int
    min_col: int
    max_row: int
    max_col: int

    @property
    def ref(self) -> str:
        return (
            f"{get_column_letter(self.min_col)}{self.min_row}:"
            f"{get_column_letter(self.max_col)}{self.max_row}"
        )


@dataclass
class SheetInfo:
    """A tab of the workbook, in tab order."""

    name: str
    index: int
    state: str = "visible"            # "visible", "hidden" or "veryHidden"
    part: str | None = None           # zip path of the worksheet XML
    is_worksheet: bool = True         # False for chart sheets

    @property
    def hidden(self) -> bool:
        return self.state in ("hidden", "veryHidden")


@dataclass
class SheetGrid:
    """Every non-empty cell of one worksheet, plus its merged blocks."""

    name: str
    cells: dict[tuple[int, int], tuple[object, str | None]] = field(default_factory=dict)
    merged: list[CellRange] = field(default_factory=list)
    formula_cells_without_value: list[str] = field(default_factory=list)
    max_row: int = 0
    max_col: int = 0
    # Merges indexed by blocks of rows, so a lookup checks only the few merges near that row
    # (expanding merges cell by cell would stall on a whole-column merge).
    _merge_buckets: dict[int, list[CellRange]] = field(default_factory=dict, repr=False)
    _text_cache: dict[tuple[int, int], str] = field(default_factory=dict, repr=False)

    _BUCKET_ROWS = 64

    def finish(self) -> None:
        """Compute the used extent and index the merged blocks."""
        if self.cells:
            self.max_row = max(r for r, _ in self.cells)
            self.max_col = max(c for _, c in self.cells)
        self._merge_buckets.clear()
        for rng in self.merged:
            last_row = min(rng.max_row, self.max_row)     # nothing below the used extent is read
            for bucket in range(rng.min_row // self._BUCKET_ROWS, last_row // self._BUCKET_ROWS + 1):
                self._merge_buckets.setdefault(bucket, []).append(rng)

    def raw(self, row: int, col: int) -> object:
        entry = self.cells.get((row, col))
        return entry[0] if entry else None

    def text(self, row: int, col: int) -> str:
        """Clean text of the cell itself (a cell covered by a merge is usually "")."""
        key = (row, col)
        cached = self._text_cache.get(key)
        if cached is None:
            entry = self.cells.get(key)
            if entry is None:
                return ""          # empty cells are not cached, so wide scans cannot bloat the cache
            cached = self._text_cache[key] = clean_text(entry[0], entry[1])
        return cached

    def rows_with_text(self, cols: list[int], first_row: int) -> list[int]:
        """Rows at or below `first_row` where any of `cols` holds non-blank text, in order.

        Walks the stored cells rather than every row number, so a stray value far
        down the sheet does not make the scan slow.
        """
        wanted = set(cols)
        return sorted({r for (r, c) in self.cells if r >= first_row and c in wanted and self.text(r, c)})

    def anchor(self, row: int, col: int) -> tuple[int, int] | None:
        """Top-left cell of the merge covering (row, col), when it is not the top-left itself."""
        for rng in self._merge_buckets.get(row // self._BUCKET_ROWS, ()):
            if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
                top_left = (rng.min_row, rng.min_col)
                return None if (row, col) == top_left else top_left
        return None

    def effective_raw(self, row: int, col: int) -> object:
        anchor = self.anchor(row, col)
        return self.raw(*anchor) if anchor else self.raw(row, col)

    def effective_text(self, row: int, col: int) -> str:
        """Text as Excel shows it: a covered cell shows its merge's top-left value."""
        anchor = self.anchor(row, col)
        return self.text(*anchor) if anchor else self.text(row, col)

    def _carry_source(self, row: int, col: int, first_data_row: int) -> tuple[int, int] | None:
        """Cell whose value a data cell uses, or None when the cell counts as blank.

        A merged value is carried *down its own column* only, and only when the
        merge starts on a data row. A header merged into the rows below it, or a
        value merged sideways into the next column, would otherwise be copied
        into fields the engineer never filled in (for example KKS taking the
        Trade text); leaving those cells blank lets the normal checks report them.
        """
        anchor = self.anchor(row, col)
        if anchor is None:
            return row, col
        anchor_row, anchor_col = anchor
        if anchor_col != col or anchor_row < first_data_row:
            return None
        return anchor

    def carried_text(self, row: int, col: int, first_data_row: int) -> str:
        """Text of a data cell for derived values (see `_carry_source`)."""
        source = self._carry_source(row, col, first_data_row)
        return self.text(*source) if source else ""

    def carried_raw(self, row: int, col: int, first_data_row: int) -> object:
        """Raw value of a data cell for derived values (see `_carry_source`)."""
        source = self._carry_source(row, col, first_data_row)
        return self.raw(*source) if source else None


def cell_ref(row: int, col: int) -> str:
    return f"{get_column_letter(col)}{row}"


# --------------------------------------------------------------------------- #
# Workbook
# --------------------------------------------------------------------------- #
_REL_OFFICE_DOCUMENT = "/officeDocument"
_REL_WORKSHEET = "/worksheet"


class WorkbookSource:
    """An uploaded workbook opened from bytes. Use as a context manager."""

    def __init__(self, data: bytes) -> None:
        self._zip: zipfile.ZipFile | None = None
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(data))
            self.sheets: list[SheetInfo] = _read_sheet_list(self._zip)
            self._wb = openpyxl.load_workbook(
                io.BytesIO(data), read_only=True, data_only=True, keep_links=False
            )
        except Exception as exc:  # any failure here means "not a usable workbook"
            if self._zip is not None:
                self._zip.close()
            raise WorkbookOpenError() from exc
        # Keep only tabs openpyxl also knows about (they should always agree).
        known = set(self._wb.sheetnames)
        self.sheets = [s for s in self.sheets if s.name in known]
        for position, sheet in enumerate(self.sheets):
            sheet.index = position

    def __enter__(self) -> "WorkbookSource":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._wb.close()
        finally:
            self._zip.close()

    def find_sheet(self, wanted: str) -> SheetInfo | None:
        """First tab whose trimmed, case-insensitive name equals `wanted`."""
        key = wanted.strip().lower()
        for sheet in self.sheets:
            if sheet.name.strip().lower() == key:
                return sheet
        return None

    def read_grid(self, sheet: SheetInfo) -> SheetGrid:
        """Load every value of a worksheet, its merged blocks and formula cells without a value."""
        grid = SheetGrid(name=sheet.name)
        try:
            ws = self._wb[sheet.name]
            # Some writers record a wrong size; read what is actually there.
            ws.reset_dimensions()
            for row in ws.iter_rows():
                for cell in row:
                    value = getattr(cell, "value", None)
                    if value is None:
                        continue
                    fmt = cell.number_format if isinstance(value, (int, float)) else None
                    grid.cells[(cell.row, cell.column)] = (value, fmt)
            if sheet.part:
                grid.merged, grid.formula_cells_without_value = _scan_sheet_xml(self._zip, sheet.part)
        except WorkbookOpenError:
            raise
        except Exception as exc:
            raise WorkbookOpenError() from exc
        grid.finish()
        return grid


def _local(tag: str) -> str:
    """XML tag or attribute name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _attr(elem: ET.Element, local_name: str) -> str | None:
    for key, value in elem.attrib.items():
        if _local(key) == local_name:
            return value
    return None


def _read_relationships(archive: zipfile.ZipFile, part: str) -> dict[str, tuple[str, str]]:
    """Relationship id -> (type, resolved zip path) for a part."""
    rels_path = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if rels_path not in set(archive.namelist()):
        return {}
    root = ET.fromstring(archive.read(rels_path))
    base = posixpath.dirname(part)
    result: dict[str, tuple[str, str]] = {}
    for rel in root:
        if _local(rel.tag) != "Relationship" or rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target") or ""
        if target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join(base, target))
        result[rel.get("Id") or ""] = (rel.get("Type") or "", resolved)
    return result


def _read_sheet_list(archive: zipfile.ZipFile) -> list[SheetInfo]:
    """Tabs in order with visibility and XML part, from the workbook part."""
    workbook_part = "xl/workbook.xml"
    for _rel_type, target in (
        v for v in _read_relationships(archive, "").values() if v[0].endswith(_REL_OFFICE_DOCUMENT)
    ):
        workbook_part = target
        break
    rels = _read_relationships(archive, workbook_part)
    root = ET.fromstring(archive.read(workbook_part))
    names_in_zip = set(archive.namelist())
    sheets: list[SheetInfo] = []
    for elem in root.iter():
        if _local(elem.tag) != "sheet":
            continue
        rel_type, part = rels.get(_attr(elem, "id") or "", ("", None))
        sheets.append(
            SheetInfo(
                name=elem.get("name") or "",
                index=len(sheets),
                state=elem.get("state") or "visible",
                part=part if part in names_in_zip else None,
                is_worksheet=rel_type.endswith(_REL_WORKSHEET),
            )
        )
    return sheets


def _scan_sheet_xml(archive: zipfile.ZipFile, part: str) -> tuple[list[CellRange], list[str]]:
    """Merged ranges, and formula cells that have no saved (cached) value.

    A formula cell with no `<v>` has never been calculated (for example a file
    written by a script), so its value would silently read as empty.
    """
    merged: list[CellRange] = []
    no_value: list[str] = []
    row_number = 0
    col_number = 0
    with archive.open(part) as source:
        for event, elem in ET.iterparse(source, events=("start", "end")):
            tag = _local(elem.tag)
            if event == "start":
                if tag == "row":
                    r = elem.get("r")
                    row_number = int(r) if r and r.isdigit() else row_number + 1
                    col_number = 0
                continue
            if tag == "c":
                ref = elem.get("r")
                if ref:
                    min_col, min_row, _, _ = range_boundaries(ref)
                    row_number, col_number = min_row, min_col
                else:
                    col_number += 1
                formula = value = None
                for child in elem:
                    child_tag = _local(child.tag)
                    if child_tag == "f":
                        formula = child
                    elif child_tag == "v":
                        value = child
                has_cached = value is not None and (bool(value.text) or elem.get("t") == "str")
                if formula is not None and not has_cached:
                    no_value.append(cell_ref(row_number, col_number))
                elem.clear()
            elif tag == "mergeCell":
                try:
                    min_col, min_row, max_col, max_row = range_boundaries(elem.get("ref") or "")
                except (TypeError, ValueError):
                    continue
                if None in (min_col, min_row, max_col, max_row):
                    continue
                if (min_row, min_col) != (max_row, max_col):
                    merged.append(CellRange(min_row, min_col, max_row, max_col))
            elif tag == "row":
                elem.clear()
    return merged, no_value
