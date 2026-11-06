"""Cell cleaning, opening from bytes, merged ranges, visibility and formula detection."""
from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, time

import pytest

from backend.excel.reader import (
    OPEN_ERROR_MESSAGE,
    CellRange,
    WorkbookOpenError,
    WorkbookSource,
    clean_text,
    value_key,
)
from backend.report import builder
from backend.report.builder import build_report


# --------------------------------------------------------------------------- #
# clean_text / value_key
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("value", "number_format", "expected"),
    [
        (None, None, ""),
        ("", None, ""),
        ("\xa0", None, ""),
        ("  \t \xa0 ", None, ""),
        ("  Pump  A\xa0 ", None, "Pump A"),
        ("a\t\tb", None, "a b"),
        ("line 1\r\nline 2\rline 3", None, "line 1\nline 2\nline 3"),
        ("\n\n  first \n\n second  \n \n", None, "first\n\nsecond"),   # inner empty line kept
        (True, None, "TRUE"),
        (False, None, "FALSE"),
        (917, None, "917"),
        (917.0, None, "917"),
        (0.1, None, "0.1"),
        (1234.5, None, "1234.5"),
        (0.0000001, None, "0.0000001"),
        (-2.25, None, "-2.25"),
        (1234, "00000000", "00001234"),
        (1234.0, "00000000", "00001234"),
        (900000000042, "0", "900000000042"),
        (1234, "General", "1234"),
        (date(2025, 12, 7), None, "7 December 2025"),
        (datetime(2025, 12, 7, 0, 0), "d-mmm-yy", "7 December 2025"),
        (datetime(2025, 12, 7, 8, 36), None, "7 December 2025 08:36"),
        (time(8, 5), None, "08:05"),
    ],
)
def test_clean_text(value, number_format, expected):
    assert clean_text(value, number_format) == expected


def test_value_key_collapses_all_whitespace_and_keeps_case():
    assert value_key("Pump\n  A\xa0\tB ") == "Pump A B"
    assert value_key("SYNINCS") != value_key("synincs")


# --------------------------------------------------------------------------- #
# Opening
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("data", [b"", b"not an excel file", b"PK\x03\x04broken zip"])
def test_unreadable_bytes_raise_workbook_open_error(data):
    with pytest.raises(WorkbookOpenError) as caught:
        build_report(data, "bad.xlsx")
    assert caught.value.message == OPEN_ERROR_MESSAGE
    assert str(caught.value) == OPEN_ERROR_MESSAGE


def test_zip_that_is_not_a_workbook_raises_open_error():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "SYNTHETIC")
    with pytest.raises(WorkbookOpenError):
        build_report(buffer.getvalue(), "bad.xlsx")


def test_builder_exposes_the_same_open_error_class():
    assert builder.WorkbookOpenError is WorkbookOpenError


# --------------------------------------------------------------------------- #
# Structure read from the xlsx XML
# --------------------------------------------------------------------------- #
def test_sheet_list_merges_and_formulas(edge_workbook_bytes):
    with WorkbookSource(edge_workbook_bytes) as source:
        assert [s.name for s in source.sheets] == [
            "Team Member", "UOIR", "UOIR ID 501 - Pump Trip due to", "UOIR ID 502 - Feed Valve Stuck",
            "UOIR ID 999 - Not in list", "Extra Notes", "Notifications", "Sheet3",
        ]
        assert [s.index for s in source.sheets] == list(range(8))
        assert all(s.state == "visible" and s.part for s in source.sheets)

        team = source.read_grid(source.find_sheet(" team member "))
        assert team.merged == [CellRange(4, 1, 4, 4)]

        tab = source.read_grid(source.find_sheet("UOIR ID 501 - Pump Trip due to"))
        by_position = sorted(tab.merged, key=lambda m: (m.min_row, m.min_col))
        assert by_position == [CellRange(3, 2, 5, 2), CellRange(3, 3, 5, 3), CellRange(4, 24, 6, 26)]
        assert by_position[2].ref == "X4:Z6"
        assert tab.anchor(5, 2) == (3, 2)
        assert tab.anchor(3, 2) is None
        assert tab.text(4, 2) == ""
        assert tab.effective_text(4, 2) == "Suction strainer blocked"
        assert tab.formula_cells_without_value == []

        tab502 = source.read_grid(source.find_sheet("UOIR ID 502 - Feed Valve Stuck"))
        assert tab502.formula_cells_without_value == ["L6"]


def test_hidden_state_comes_from_workbook_xml(clean_workbook_with):
    def hide(wb):
        wb["UOIR ID 601 - Clean Pump Trip"].sheet_state = "hidden"
        wb["Sheet3"].sheet_state = "veryHidden"

    with WorkbookSource(clean_workbook_with(hide)) as source:
        states = {s.name: (s.state, s.hidden) for s in source.sheets}
    assert states["UOIR ID 601 - Clean Pump Trip"] == ("hidden", True)
    assert states["Sheet3"] == ("veryHidden", True)
    assert states["UOIR"] == ("visible", False)


def test_ignored_sheets_are_never_read(clean_workbook_bytes, monkeypatch):
    opened: list[str] = []
    original = WorkbookSource.read_grid

    def spy(self, sheet):
        opened.append(sheet.name)
        return original(self, sheet)

    monkeypatch.setattr(WorkbookSource, "read_grid", spy)
    report = build_report(clean_workbook_bytes, "SYNTHETIC_clean.xlsx")
    assert opened == ["Team Member", "UOIR", "UOIR ID 601 - Clean Pump Trip", "UOIR ID 602 - Clean Valve Fault"]
    assert report.issues == []


def test_formula_without_saved_value_on_team_sheet(clean_workbook_with):
    def add_formula(wb):
        wb["Team Member"]["F1"] = "=1+2"

    report = build_report(clean_workbook_with(add_formula), "SYNTHETIC.xlsx")
    assert [(i.severity, i.code, i.sheet, i.row, i.cell) for i in report.issues] == [
        ("warning", "FORMULA_NO_VALUE", "Team Member", 1, "F1"),
    ]
    assert report.can_export is True


def test_wrong_sheet_dimension_does_not_truncate_data(clean_workbook_bytes):
    """Some writers record a too-small <dimension>; every row must still be read."""
    source = io.BytesIO(clean_workbook_bytes)
    target = io.BytesIO()
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet"):
                text = data.decode("utf-8")
                start = text.find("<dimension ref=\"")
                if start != -1:
                    end = text.find("\"", start + len("<dimension ref=\""))
                    text = text[:start] + "<dimension ref=\"A1:A1" + text[end:]
                data = text.encode("utf-8")
            zout.writestr(item, data)
    report = build_report(target.getvalue(), "SYNTHETIC.xlsx")
    assert report.issues == []
    assert len(report.team) == 2
    assert [len(s.analysis.rows) for s in report.analyses] == [4, 2]
