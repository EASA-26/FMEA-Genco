"""Date and text formatting shared by the parser, the API and the PDF.

Dates are written out in full ("7 December 2025") without relying on the
server locale, so the report reads the same on a laptop and on Databricks.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# Text dates accepted where the workbook should hold an Excel date.
DATE_TEXT_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d-%b-%y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%Y-%m-%d",
)

# Excel refuses these characters in worksheet names.
EXCEL_TAB_FORBIDDEN_CHARS = "[]:*?/\\"


def format_date(d: date | datetime | None) -> str:
    """"7 December 2025"; a datetime with a time of day adds " 08:36"; None -> ""."""
    if d is None:
        return ""
    text = f"{d.day} {_MONTHS[d.month - 1]} {d.year}"
    if isinstance(d, datetime) and d.time() != time(0, 0):
        text += f" {d.hour:02d}:{d.minute:02d}"
    return text


def parse_date_text(text: str) -> date | None:
    """Read a date typed as text (e.g. "15/06/2026"); None when it is not a date."""
    cleaned = " ".join((text or "").replace("\xa0", " ").split())
    if not cleaned:
        return None
    for fmt in DATE_TEXT_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def make_pdf_filename(station: str, d: date | None) -> str:
    """FMEA_Report_<station>_<YYYY-MM-DD>.pdf with a file-system safe station name."""
    safe = re.sub(r"\s+", "_", (station or "").strip())
    safe = re.sub(r"[^A-Za-z0-9_-]", "", safe)
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        safe = "Station"
    if isinstance(d, datetime):
        d = d.date()
    date_part = d.isoformat() if d is not None else "undated"
    return f"FMEA_Report_{safe}_{date_part}.pdf"


def collapse_whitespace(text: str) -> str:
    """Every run of whitespace (including line breaks) becomes one space; ends trimmed."""
    return " ".join((text or "").split())


def normalise_title(text: str) -> str:
    """Title key used to compare a tab-name fragment with a UOIR title.

    Lower case, characters Excel forbids in tab names removed, whitespace collapsed.
    """
    lowered = (text or "").replace("\xa0", " ").lower()
    for ch in EXCEL_TAB_FORBIDDEN_CHARS:
        lowered = lowered.replace(ch, "")
    return collapse_whitespace(lowered)


def quote_list(values: list[str]) -> str:
    """'A', 'B' and 'C' — for plain-language messages."""
    quoted = [f"'{v}'" for v in values]
    if len(quoted) <= 1:
        return "".join(quoted)
    return ", ".join(quoted[:-1]) + " and " + quoted[-1]


def plain_list(values: list[str]) -> str:
    """A, B and C — for plain-language messages."""
    if len(values) <= 1:
        return "".join(values)
    return ", ".join(values[:-1]) + " and " + values[-1]


def shorten(text: str, limit: int = 60) -> str:
    """One-line preview of a cell value for messages."""
    flat = collapse_whitespace(text)
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"
