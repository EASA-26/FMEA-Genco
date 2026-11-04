"""Match analysis tabs ("UOIR ID 901 - SYNTHETIC Trip (M") to the UOIRs listed on the UOIR sheet.

Excel limits tab names to 31 characters, so a tab name carries the UOIR ID and
only a piece of the title (sometimes from the middle). The ID decides the link;
the title piece only settles a tie between tabs with the same ID and raises a
warning when it does not fit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from openpyxl.utils.cell import coordinate_from_string

from backend.config.mapping import ANALYSIS_SHEET_PATTERN, ANALYSIS_TITLE_CELL
from backend.excel.reader import SheetInfo, text_key
from backend.report.formatting import normalise_title, quote_list, shorten
from backend.report.models import Issue

EXCEL_TAB_NAME_LIMIT = 31
_LEADING_SEPARATORS = "-: \t\xa0"


@dataclass(frozen=True)
class AnalysisTab:
    """A tab whose name looks like an analysis tab."""

    sheet: SheetInfo
    uoir_id: str      # digits as written in the tab name
    id_key: str       # the same without leading zeros
    fragment: str     # title part of the tab name


@dataclass(frozen=True)
class UoirRef:
    """What linking needs to know about one UOIR (first row it appears on)."""

    uoir_id: str
    title: str
    sheet: str        # UOIR sheet name, for issue locations
    row: int
    cell: str | None = None
    column: str | None = None


@dataclass
class LinkOutcome:
    tabs: dict[str, AnalysisTab] = field(default_factory=dict)   # UOIR id_key -> linked tab
    issues: list[Issue] = field(default_factory=list)


def parse_analysis_tab_name(name: str) -> tuple[str, str] | None:
    """(ID digits, title fragment) for an analysis tab name, or None."""
    match = ANALYSIS_SHEET_PATTERN.match(name or "")
    if not match:
        return None
    return match.group(1), match.group(2).lstrip(_LEADING_SEPARATORS)


def uoir_id_key(uoir_id: str) -> str:
    """IDs compare exactly after leading zeros are removed ("0901" == "901")."""
    text = (uoir_id or "").strip()
    if re.fullmatch(r"\d+", text):
        return text.lstrip("0") or "0"
    return text


def fragment_matches_title(fragment: str, title: str) -> bool:
    """True when the tab-name fragment appears anywhere in the title (an empty fragment matches)."""
    return normalise_title(fragment) in normalise_title(title)


def expected_tab_name(uoir_id: str, title: str) -> str:
    """Suggested tab name for messages, cut to Excel's 31-character limit."""
    prefix = f"UOIR ID {uoir_id} - "
    room = max(EXCEL_TAB_NAME_LIMIT - len(prefix), 0)
    clean_title = " ".join(re.sub(r"[\[\]:*?/\\]", "", title or "").split())
    if len(clean_title) > room:
        return prefix + clean_title[:room].rstrip() + "…"
    return prefix + clean_title


def find_analysis_tabs(sheets: list[SheetInfo]) -> list[AnalysisTab]:
    tabs: list[AnalysisTab] = []
    for sheet in sheets:
        parsed = parse_analysis_tab_name(sheet.name)
        if parsed:
            digits, fragment = parsed
            tabs.append(AnalysisTab(sheet, digits, uoir_id_key(digits), fragment))
    return tabs


def link_analysis_tabs(uoirs: list[UoirRef], tabs: list[AnalysisTab]) -> LinkOutcome:
    """Link each UOIR to exactly one tab, reporting missing, ambiguous and unlisted tabs."""
    outcome = LinkOutcome()
    by_id: dict[str, list[AnalysisTab]] = {}
    for tab in tabs:
        by_id.setdefault(tab.id_key, []).append(tab)

    listed_keys: set[str] = set()
    for uoir in uoirs:
        key = uoir_id_key(uoir.uoir_id)
        listed_keys.add(key)
        candidates = by_id.get(key, [])

        if not candidates:
            outcome.issues.append(Issue(
                severity="error",
                code="ANALYSIS_SHEET_MISSING",
                message=(
                    f"No worksheet found for UOIR ID {uoir.uoir_id}. Expected a tab named like "
                    f"'{expected_tab_name(uoir.uoir_id, uoir.title)}'."
                ),
                sheet=uoir.sheet, row=uoir.row, column=uoir.column, cell=uoir.cell,
                uoir_id=uoir.uoir_id,
            ))
            continue

        chosen: AnalysisTab | None = None
        if len(candidates) == 1:
            chosen = candidates[0]
            # A blank Title is already an error on the UOIR sheet; comparing the tab name with "" says nothing.
            if uoir.title and not fragment_matches_title(chosen.fragment, uoir.title):
                outcome.issues.append(Issue(
                    severity="warning",
                    code="ANALYSIS_SHEET_TITLE_MISMATCH",
                    message=(
                        f"The name of tab '{chosen.sheet.name}' does not match the title of UOIR ID "
                        f"{uoir.uoir_id} ('{shorten(uoir.title)}'). It was linked by its ID; check that "
                        "it is the right tab."
                    ),
                    sheet=chosen.sheet.name, uoir_id=uoir.uoir_id,
                ))
        else:
            matching = [t for t in candidates if fragment_matches_title(t.fragment, uoir.title)]
            if len(matching) == 1:
                chosen = matching[0]
                for other in candidates:
                    if other is not chosen:
                        outcome.issues.append(Issue(
                            severity="info",
                            code="SHEET_NOT_USED",
                            message=(
                                f"Sheet '{other.sheet.name}' is not used in the report. Tab "
                                f"'{chosen.sheet.name}' matches the title of UOIR ID {uoir.uoir_id} "
                                "and was used instead."
                            ),
                            sheet=other.sheet.name, uoir_id=uoir.uoir_id,
                        ))
            else:
                names = [t.sheet.name for t in candidates]
                outcome.issues.append(Issue(
                    severity="error",
                    code="ANALYSIS_SHEET_AMBIGUOUS",
                    message=(
                        f"More than one worksheet was found for UOIR ID {uoir.uoir_id}: {quote_list(names)}. "
                        "Keep one tab for this UOIR, or make each tab name match its title, and upload again."
                    ),
                    sheet=uoir.sheet, row=uoir.row, column=uoir.column, cell=uoir.cell,
                    uoir_id=uoir.uoir_id,
                ))

        if chosen is not None:
            outcome.tabs[key] = chosen
            if chosen.sheet.hidden:
                outcome.issues.append(Issue(
                    severity="warning",
                    code="ANALYSIS_SHEET_HIDDEN",
                    message=(
                        f"Tab '{chosen.sheet.name}' for UOIR ID {uoir.uoir_id} is hidden in Excel. "
                        "It is included in the report."
                    ),
                    sheet=chosen.sheet.name, uoir_id=uoir.uoir_id,
                ))

    for tab in tabs:
        if tab.id_key not in listed_keys:
            outcome.issues.append(Issue(
                severity="warning",
                code="ANALYSIS_SHEET_UNLISTED",
                message=(
                    f"Sheet '{tab.sheet.name}' is for UOIR ID {tab.uoir_id}, which is not in the UOIR list "
                    "and was left out of the report."
                ),
                sheet=tab.sheet.name, uoir_id=tab.uoir_id,
            ))
    return outcome


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
