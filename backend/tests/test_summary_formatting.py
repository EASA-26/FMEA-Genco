"""Formatting helpers: dates, PDF file names and text helpers."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.report.formatting import (
    format_date,
    make_pdf_filename,
    normalise_title,
    parse_date_text,
    plain_list,
    quote_list,
    shorten,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (date(2025, 12, 7), "7 December 2025"),
        (date(2024, 3, 5), "5 March 2024"),
        (datetime(2025, 12, 7, 0, 0), "7 December 2025"),
        (datetime(2025, 12, 7, 8, 36), "7 December 2025 08:36"),
        (datetime(2026, 1, 31, 23, 5, 59), "31 January 2026 23:05"),
    ],
)
def test_format_date(value, expected):
    assert format_date(value) == expected


@pytest.mark.parametrize(
    ("station", "day", "expected"),
    [
        ("SYNTHETIC S9", date(2024, 3, 5), "FMEA_Report_SYNTHETIC_S9_2024-03-05.pdf"),
        ("  SYNTHETIC   S9 ", date(2024, 3, 5), "FMEA_Report_SYNTHETIC_S9_2024-03-05.pdf"),
        ("SYNTHETIC Station (Unit 2/3)", date(2026, 6, 15), "FMEA_Report_SYNTHETIC_Station_Unit_23_2026-06-15.pdf"),
        ("Stesen Jana-Kuasa_1", None, "FMEA_Report_Stesen_Jana-Kuasa_1_undated.pdf"),
        ("", date(2026, 6, 15), "FMEA_Report_Station_2026-06-15.pdf"),
        ("\xa0 ", None, "FMEA_Report_Station_undated.pdf"),
        ("***", None, "FMEA_Report_Station_undated.pdf"),
        ("A _ B", None, "FMEA_Report_A_B_undated.pdf"),
        ("Stn", datetime(2026, 6, 15, 9, 30), "FMEA_Report_Stn_2026-06-15.pdf"),
    ],
)
def test_make_pdf_filename(station, day, expected):
    assert make_pdf_filename(station, day) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15/06/2026", date(2026, 6, 15)),
        ("5/6/2026", date(2026, 6, 5)),
        ("15-06-2026", date(2026, 6, 15)),
        ("15.06.2026", date(2026, 6, 15)),
        ("15-Jun-26", date(2026, 6, 15)),
        ("15-jun-2026", date(2026, 6, 15)),
        ("15 June 2026", date(2026, 6, 15)),
        ("15 Jun 2026", date(2026, 6, 15)),
        ("2026-06-15", date(2026, 6, 15)),
        ("\xa015  June   2026 ", date(2026, 6, 15)),
        ("", None),
        ("next week", None),
        ("06/15/2026", None),          # month/day order is not accepted
        ("2026/06/15", None),
    ],
)
def test_parse_date_text(text, expected):
    assert parse_date_text(text) == expected


def test_normalise_title():
    assert normalise_title("  Valve A/B:\xa0Stuck [Open]?  ") == "valve ab stuck open"


def test_message_helpers():
    assert quote_list(["A"]) == "'A'"
    assert quote_list(["A", "B", "C"]) == "'A', 'B' and 'C'"
    assert plain_list([]) == ""
    assert plain_list(["A", "B"]) == "A and B"
    assert shorten("short") == "short"
    assert shorten("word " * 30, limit=20) == "word word word word…"
