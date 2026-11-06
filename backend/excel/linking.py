"""Read the UOIR IDs in analysis tab names ("UOIR ID 901 902 - SYNTHETIC Trip") and check the tabs.

Excel limits tab names to 31 characters, so a tab name carries one or more UOIR
IDs and only a piece of the title (sometimes from the middle). The IDs decide
which UOIRs a tab covers; the title piece only raises a warning when it fits
neither cell B1 nor the Title of any UOIR the tab covers. These are pure
helpers: the report builder reads the workbook and passes the sheets in.
"""
from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from openpyxl.utils.cell import coordinate_from_string

from backend.config.mapping import (
    ANALYSIS_EXTRA_ID_PATTERN,
    ANALYSIS_SHEET_PATTERN,
    ANALYSIS_TITLE_CELL,
)
from backend.excel.reader import SheetInfo, text_key
from backend.report.formatting import normalise_title, quote_list, shorten
from backend.report.models import Issue

_FRAGMENT_SEPARATORS = "-:,& \t\xa0"

# Raised by the report builder (ANALYSIS_SHEET_NAME_UNREADABLE); the copy lives here with the other tab messages.
UNREADABLE_MESSAGE = (
    "Sheet '{name}' looks like an analysis tab, but its name does not start with 'UOIR ID' and a "
    "number, so it is not in the report. Rename it like 'UOIR ID 123 - Title of the UOIR' and upload "
    "again."
)


@dataclass(frozen=True)
class UoirRef:
    """What linking needs to know about one UOIR (first row it appears on)."""

    uoir_id: str
    title: str
    sheet: str        # UOIR sheet name, for issue locations
    row: int
    cell: str | None = None
    column: str | None = None
    position: int = 0   # index in the distinct UOIR list


@dataclass(frozen=True)
class AnalysisTabRef:
    """An analysis tab and the UOIR IDs its name lists."""

    sheet: SheetInfo
    ids: tuple[str, ...]    # as written in the tab name, repeats removed by key
    keys: tuple[str, ...]   # uoir_id_key of each
    fragment: str           # title part of the tab name


def uoir_id_key(uoir_id: str) -> str:
    """IDs compare exactly after leading zeros are removed ("0901" == "901")."""
    text = (uoir_id or "").strip()
    if re.fullmatch(r"\d+", text):
        return text.lstrip("0") or "0"
    return text


def fragment_matches_title(fragment: str, title: str) -> bool:
    """True when the tab-name fragment appears anywhere in the title (an empty fragment matches)."""
    return normalise_title(fragment) in normalise_title(title)


def check_title_cell(b1_text: str, uoir: UoirRef, sheet_name: str) -> Issue | None:
    """Warn when the tab's B1 title is filled in and differs from the UOIR title.

    Nothing is compared when the UOIR title is blank (that is already an error on the UOIR sheet).
    """
    if not b1_text or not uoir.title:
        return None
    if text_key(b1_text).lower() == text_key(uoir.title).lower():
        return None
    return Issue(
        severity="warning",
        code="ANALYSIS_TITLE_CELL_MISMATCH",
        message=(
            f"Cell {ANALYSIS_TITLE_CELL} on '{sheet_name}' ('{shorten(b1_text)}') is different from the "
            f"Title of UOIR ID {uoir.uoir_id} on the UOIR sheet ('{shorten(uoir.title)}'). Check that this "
            "tab belongs to that UOIR."
        ),
        sheet=sheet_name, row=coordinate_from_string(ANALYSIS_TITLE_CELL)[1],
        cell=ANALYSIS_TITLE_CELL, uoir_id=uoir.uoir_id,
    )


# --------------------------------------------------------------------------- #
# Tab names that list several UOIR IDs
# --------------------------------------------------------------------------- #
def parse_tab_name(name: str, listed_keys: Collection[str] = frozenset()) -> tuple[list[str], str] | None:
    """(IDs as written, title fragment) for an analysis tab name, or None.

    The first number after "UOIR ID" is always an ID. Further numbers are IDs only when they are on the
    UOIR list, so a number that starts the title ("UOIR ID 905 2 fans trip") stays in the title.
    """
    match = ANALYSIS_SHEET_PATTERN.match(name or "")
    if not match:
        return None
    ids = [match.group(1)]
    seen = {uoir_id_key(match.group(1))}
    rest = name[match.end(1):]
    while True:
        extra = ANALYSIS_EXTRA_ID_PATTERN.match(rest)
        if not extra or uoir_id_key(extra.group(1)) not in listed_keys:
            break
        key = uoir_id_key(extra.group(1))
        if key not in seen:
            seen.add(key)
            ids.append(extra.group(1))
        rest = rest[extra.end(1):]
    return ids, rest.lstrip(_FRAGMENT_SEPARATORS)


def read_analysis_tabs(sheets: list[SheetInfo], listed_keys: Collection[str]) -> list[AnalysisTabRef]:
    tabs: list[AnalysisTabRef] = []
    for sheet in sheets:
        parsed = parse_tab_name(sheet.name, listed_keys)
        if parsed:
            ids, fragment = parsed
            tabs.append(AnalysisTabRef(sheet, tuple(ids), tuple(uoir_id_key(i) for i in ids), fragment))
    return tabs


def display_ids(tab: AnalysisTabRef, listed: Mapping[str, UoirRef]) -> list[str]:
    """IDs as spelled on the UOIR sheet when listed, otherwise as written in the tab name."""
    return [listed[key].uoir_id if key in listed else written for written, key in zip(tab.ids, tab.keys)]


def tab_label(tab: AnalysisTabRef, listed: Mapping[str, UoirRef]) -> str:
    return ", ".join(display_ids(tab, listed))


def is_single_uoir(tab: AnalysisTabRef, listed: Mapping[str, UoirRef]) -> bool:
    return len(tab.keys) == 1 and tab.keys[0] in listed


def _uoir_row_issue(severity: str, code: str, message: str, ref: UoirRef) -> Issue:
    return Issue(
        severity=severity, code=code, message=message,
        sheet=ref.sheet, row=ref.row, column=ref.column, cell=ref.cell, uoir_id=ref.uoir_id,
    )


def tab_issues(tabs: list[AnalysisTabRef], listed: Mapping[str, UoirRef], uoir_list_read: bool) -> list[Issue]:
    """Unlisted and hidden tabs, tab by tab."""
    issues: list[Issue] = []
    for tab in tabs:
        name = tab.sheet.name
        label = tab_label(tab, listed)
        if uoir_list_read and tab.keys[0] not in listed:
            first = tab.ids[0]
            issues.append(Issue(
                severity="warning",
                code="ANALYSIS_SHEET_UNLISTED",
                message=(
                    f"Tab '{name}' is for UOIR ID {first}, which is not in the UOIR list. It is included "
                    f"in the report. Add UOIR ID {first} to the UOIR sheet if it belongs there."
                ),
                sheet=name, uoir_id=label,
            ))
        if tab.sheet.hidden:
            issues.append(Issue(
                severity="warning",
                code="ANALYSIS_SHEET_HIDDEN",
                message=f"Tab '{name}' (UOIR ID {label}) is hidden in Excel. It is included in the report.",
                sheet=name, uoir_id=label,
            ))
    return issues


_SEPARATE_NUMBER = re.compile(r"(?<![0-9A-Za-z])\d+(?![0-9A-Za-z])")


def coverage_issues(
    tabs: list[AnalysisTabRef],
    listed: Mapping[str, UoirRef],
    unreadable_names: list[str],
    uoir_list_read: bool,
) -> list[Issue]:
    """No analysis tabs at all, and what each listed UOIR looks like from the tabs' side."""
    issues: list[Issue] = []
    none = uoir_list_read and not tabs
    if none:
        issues.append(Issue(
            severity="error",
            code="ANALYSIS_SHEET_NONE",
            message=(
                "The workbook has no analysis tabs, so the report would have no FMEA Analysis. Add a tab "
                "named like 'UOIR ID 123 - Title of the UOIR' and upload again."
            ),
        ))
    # Where to look for a number that was not read as an ID: tabs first, then unreadable names.
    searched = [(t.sheet.name, t.fragment) for t in tabs] + [(n, n) for n in unreadable_names]
    for key, ref in sorted(listed.items(), key=lambda item: item[1].position):
        named_in = [t.sheet.name for t in tabs if key in t.keys]
        if len(named_in) >= 2:
            both = "Both are" if len(named_in) == 2 else "All of them are"
            issues.append(_uoir_row_issue(
                "warning", "UOIR_IN_SEVERAL_TABS",
                f"UOIR ID {ref.uoir_id} is named in {len(named_in)} tabs: {quote_list(named_in)}. "
                f"{both} in the report. Check that this is intended.",
                ref,
            ))
            continue
        if named_in:
            continue
        unread_in = next(
            (name for name, text in searched
             if any(uoir_id_key(n) == key for n in _SEPARATE_NUMBER.findall(text))),
            None,
        )
        if unread_in is not None:
            issues.append(_uoir_row_issue(
                "warning", "UOIR_ID_NOT_READ",
                f"UOIR ID {ref.uoir_id} appears in the name of tab '{unread_in}', but it was not read as "
                "one of the tab's IDs. Write every ID right after 'UOIR ID', separated by spaces, commas "
                "or &, for example 'UOIR ID 123 124 - Title', and upload again.",
                ref,
            ))
        elif not none:
            issues.append(_uoir_row_issue(
                "info", "ANALYSIS_SHEET_MISSING",
                f"UOIR ID {ref.uoir_id} is not named in any analysis tab, so it is only shown in Failure "
                f"Details. If a tab covers it, add {ref.uoir_id} to that tab's name and upload again.",
                ref,
            ))
    return issues


def fragment_mismatch(tab: AnalysisTabRef, listed: Mapping[str, UoirRef], b1_title: str) -> Issue | None:
    """Warn when the tab-name fragment fits neither cell B1 nor the Title of any UOIR the tab covers."""
    if not tab.fragment:
        return None
    titles = [(listed[k].uoir_id, listed[k].title) for k in tab.keys if k in listed and listed[k].title]
    if not b1_title and not titles:
        return None
    if b1_title and fragment_matches_title(tab.fragment, b1_title):
        return None
    if any(fragment_matches_title(tab.fragment, title) for _, title in titles):
        return None
    parts: list[str] = []
    if b1_title:
        parts.append(f"cell {ANALYSIS_TITLE_CELL} ('{shorten(b1_title)}')")
    for n, (uoir_id, title) in enumerate(titles):
        lead = f"the Title of UOIR ID {uoir_id}" if n == 0 else uoir_id
        parts.append(f"{lead} ('{shorten(title)}')")
    return Issue(
        severity="warning",
        code="ANALYSIS_SHEET_TITLE_MISMATCH",
        message=(
            f"The name of tab '{tab.sheet.name}' does not match {' or '.join(parts)}. It is still used; "
            "check that it is the right tab."
        ),
        sheet=tab.sheet.name, uoir_id=tab_label(tab, listed),
    )
