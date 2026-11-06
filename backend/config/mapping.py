"""Central workbook mapping and business rules.

Every worksheet name, cell, header and code the application relies on lives in
this module, so a change to the engineers' workbook layout is a change here
rather than a hunt through the parser, the calculations and the PDF.

Header names are matched with `normalise_header` (case, spaces and punctuation
ignored), so "Review task " and "RecommendedStrategy" / "Recommended Strategy"
both resolve. Displayed headers always keep the workbook's own text.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
ACCEPTED_EXTENSIONS = (".xlsx", ".xlsm")

# --------------------------------------------------------------------------- #
# Worksheets
# --------------------------------------------------------------------------- #
TEAM_SHEET = "Team Member"
UOIR_SHEET = "UOIR"

# Sheets that are never read (matched case-insensitively, trimmed).
IGNORED_SHEETS = ("Notifications", "Sheet3")

# Analysis tabs are named "UOIR ID <id> - <part of the title>". Excel limits tab
# names to 31 characters, so the title part may be cut or taken from the middle.
ANALYSIS_SHEET_PATTERN = re.compile(r"^\s*UOIR\s*ID\s*[:#-]?\s*(\d+)\s*(.*)$", re.IGNORECASE)
ANALYSIS_EXTRA_ID_PATTERN = re.compile(r"[\s,&]+(\d+)(?=$|[\s,&:\-])")   # more IDs after the first; used with .match

# Rows searched when looking for a header row.
HEADER_SEARCH_ROWS = 15

# --------------------------------------------------------------------------- #
# Team Member sheet
# --------------------------------------------------------------------------- #
STATION_CELL = "B2"
STATION_LABEL_CELL = "A2"          # expected to contain "Station"
ANALYSIS_DATE_CELL = "B3"
ANALYSIS_DATE_LABEL_CELL = "A3"    # expected to contain "Date of Analysis"

# field key -> workbook header
TEAM_COLUMNS = {
    "no": "No",
    "name": "Name",
    "staff_no": "Staff No",
    "section": "Section",
}
# A team row ends the list when all of these are blank ("No" may be pre-filled).
TEAM_END_WHEN_BLANK = ("name", "staff_no", "section")

# --------------------------------------------------------------------------- #
# UOIR sheet ("List of UOIR") -> Failure Details
# --------------------------------------------------------------------------- #
UOIR_COLUMNS = {
    "no": "No",
    "uoir_id": "UOIR ID",
    "title": "Title",
    "faulty_date": "Date of fault",
    "uoir_date": "Date of UOIR",
    "corrective_action": "CA",
    "preventive_action": "PA",
    "equipment": "Equipment",
}
UOIR_REQUIRED_VALUES = ("uoir_id", "title")

# Report labels for the Failure Details table (keep "UOIR ID Date").
FAILURE_DETAILS_LABELS = {
    "uoir_id": "UOIR ID",
    "title": "Title",
    "faulty_date": "Faulty Date",
    "uoir_date": "UOIR ID Date",
    "corrective_action": "Corrective Action (CA)",
    "preventive_action": "Preventive Action (PA)",
    "equipment": "Equipment",
}

# --------------------------------------------------------------------------- #
# Analysis tabs
# --------------------------------------------------------------------------- #
ANALYSIS_TITLE_CELL = "B1"   # title cell: cross-check for one-UOIR tabs, the title for multi-UOIR tabs

# field key -> workbook header. Every column in the tab is displayed; these are
# the ones the calculations use.
ANALYSIS_COLUMNS = {
    "no": "No.",
    "failure_mode": "Failure Mode",
    "failure_effect": "Failure Effect",
    "strategy": "RecommendedStrategy",
    "task": "Task",
    "frequency": "Frequency",
    "trade": "Trade",
    "kks": "KKS",
    "new_task": "New Task",
}
# Headers that identify the header row of an analysis tab.
ANALYSIS_HEADER_MARKERS = ("failure_mode", "strategy")
# Columns that must exist in every analysis tab.
ANALYSIS_REQUIRED_HEADERS = (
    "failure_mode", "failure_effect", "strategy", "task", "frequency", "trade", "kks", "new_task",
)
# Values that must never be empty (blank -> export blocked).
ANALYSIS_REQUIRED_VALUES = ("failure_mode", "failure_effect", "strategy", "task", "trade", "kks")
# Columns ignored when deciding whether a row is blank or an exact duplicate.
ANALYSIS_ROW_NUMBER_FIELD = "no"

# --------------------------------------------------------------------------- #
# Yes / No
# --------------------------------------------------------------------------- #
YES_VALUES = frozenset({"yes", "y"})
NO_VALUES = frozenset({"no", "n"})

# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #
NSM_CODE = "NSM"
NOT_ANALYSED_CODE = "N/A"
REDESIGN_PREFIX = "R-"
REDESIGN_NAME_PREFIX = "Redesign "

# Always shown in the Existing vs Revised table, in this order (zeros included).
STANDARD_STRATEGY_CODES = ("OC", "SR", "SD", "FF", "NSM", "R-SPARE", "N/A")

# code -> name. Display in the table: "<CODE> - <name>", except N/A -> name only.
STRATEGY_NAMES = {
    "OC": "On Condition",
    "SR": "Schedule Restore",
    "SD": "Schedule Discard",
    "FF": "Failure Finding",
    "NSM": "No Schedule Maintenance",
    "R-SPARE": "Redesign Spare",
    "N/A": "Not Analysed",
    "R-HARDWARE": "Redesign Hardware",
    "R-SOFTWARE": "Redesign Software",
    "R-PRO": "Redesign Procedure",
}

# Fixed colour per strategy, shared by the app and the PDF. Categorical slots
# from the validated reference palette (adjacent CVD and normal-vision checks
# pass on white); identity is never colour-only because the legend and table
# always carry the name and count.
STRATEGY_COLORS = {
    "OC": "#2a78d6",
    "SR": "#eb6834",
    "SD": "#1baf7a",
    "FF": "#eda100",
    "NSM": "#e87ba4",
    "R-SPARE": "#008300",
    "R-HARDWARE": "#4a3aa7",
    "R-SOFTWARE": "#e34948",
    "R-PRO": "#9085e9",
    "N/A": "#898781",
}
UNKNOWN_STRATEGY_COLOR = "#c3c2b7"
NOT_SPECIFIED_LABEL = "Not specified"
TRADE_NOT_SPECIFIED_LABEL = "Trade not specified"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def normalise_header(text: object) -> str:
    """Key used to match headers: lowercase letters and digits only."""
    return re.sub(r"[^0-9a-z]", "", str(text or "").replace("\xa0", " ").lower())


def normalise_code(text: str) -> str:
    """Strategy code key: trimmed, inner spaces removed, uppercase."""
    return re.sub(r"\s+", "", (text or "").replace("\xa0", " ")).upper()


def strategy_name(code: str) -> str:
    """Name for a normalised code; unknown R- codes expand to "Redesign X"."""
    if code in STRATEGY_NAMES:
        return STRATEGY_NAMES[code]
    if code.startswith(REDESIGN_PREFIX) and len(code) > len(REDESIGN_PREFIX):
        return REDESIGN_NAME_PREFIX + code[len(REDESIGN_PREFIX):].title()
    return ""


def strategy_label(code: str) -> str:
    """Text for the Strategy column / legend, e.g. "OC - On Condition"."""
    if not code:
        return NOT_SPECIFIED_LABEL
    if code == NOT_ANALYSED_CODE:
        return STRATEGY_NAMES[NOT_ANALYSED_CODE]
    name = strategy_name(code)
    return f"{code} - {name}" if name else code


def strategy_color(code: str) -> str:
    return STRATEGY_COLORS.get(code, UNKNOWN_STRATEGY_COLOR)
