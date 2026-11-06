"""Build SYNTHETIC FMEA workbooks for tests and manual checks.

Everything in these workbooks is invented and labelled SYNTHETIC; none of it
comes from a real station, engineer or plant record.

Three variants:

* ``edge``  - exercises the awkward cases the parser must handle: merged
  Failure Mode cells over several rows, non-breaking-space "blanks", NSM rows
  with a blank New Task, a non-NSM blank New Task, an invalid New Task ("TBC"),
  a blank required value, an exact duplicate row, two KKS values in one UOIR,
  a UOIR listed on two rows with different Equipment, a tab-name title
  fragment from the middle of the title, a tab whose ID is not in the UOIR
  list, an unknown strategy code and an R- code that is not in the list,
  lower/upper-case trade spellings, notes outside the table, a text date,
  a zero-padded staff number format and very long multiline text.
* ``clean`` - a small, valid workbook that produces no issues at all.
* ``sample`` - a look-alike of a full engineer workbook: the same sheets,
  layout and quirks (trailing spaces in headers, numeric staff numbers and
  UOIR IDs, pre-filled No rows, tab names cut to 31 characters, a large
  ignored Notifications sheet, non-breaking-space blanks, notes beside and
  below a table, a failure mode repeated over several task rows) with entirely
  invented content. It produces no issues at all and stands in for a real
  workbook in the tests.

Usage::

    python tools/make_synthetic_workbook.py                      # edge variant, size only
    python tools/make_synthetic_workbook.py SYNTHETIC_edge.xlsx  # write the edge variant
    python tools/make_synthetic_workbook.py --variant clean SYNTHETIC_clean.xlsx
    python tools/make_synthetic_workbook.py --variant sample SYNTHETIC_sample.xlsx
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

NBSP = "\xa0"

# The analysis-tab layout used by the engineers (22 columns, A..V).
ANALYSIS_HEADERS = [
    "No.", "Failure Mode", "Failure Effect", "H", "S", "E", "O", 1, 2, 3, "H4", "H5", "S4",
    "RecommendedStrategy", "Task", "Frequency", "Trade", "KKS", "New Task", "Review task ",
    "Maintenance Plan No", "Remark",
]
# H, S, E, O, 1, 2, 3, H4, H5, S4
DEFAULT_FLAGS = ("Y", "N", "N", "Y", "N", "N", "N", None, None, None)

EDGE_TITLE_501 = "SYNTHETIC Pump Trip due to Low Suction Pressure"
EDGE_TITLE_502 = "SYNTHETIC Boiler Feed Valve Stuck Open Event"
EDGE_TAB_501 = "UOIR ID 501 - Pump Trip due to"
EDGE_TAB_502 = "UOIR ID 502 - Feed Valve Stuck"      # fragment from the middle of the title
EDGE_TAB_UNLISTED = "UOIR ID 999 - Not in list"

CLEAN_TITLE_601 = "SYNTHETIC Clean Pump Trip on Low Flow"
CLEAN_TITLE_602 = "SYNTHETIC Clean Valve Fault During Start-up"
CLEAN_TAB_601 = "UOIR ID 601 - Clean Pump Trip"
CLEAN_TAB_602 = "UOIR ID 602 - Clean Valve Fault"

LONG_CORRECTIVE_ACTION = "\n".join(
    f"{n}. SYNTHETIC corrective step {n}: inspect the suction strainer, record the differential "
    "pressure, compare it with the commissioning value and replace the mesh when the reading "
    "exceeds the alarm limit agreed with the operations team."
    for n in range(1, 7)
)
LONG_FAILURE_EFFECT = (
    "SYNTHETIC effect line one: the controller issues a false low-flow trip.\n"
    "Line two: the standby pump starts late and header pressure dips below the interlock limit, "
    "which cascades into a boiler feed alarm and an operator intervention that takes several "
    "minutes while the cause is traced through the distributed control system logs.\n\n"
    "Line four after an empty line: recorded for testing only."
)
LONG_REMARK = (
    "SYNTHETIC remark with a very long unbroken token "
    "LAB10AA101/LAB10AA102/LAB10AA103/LAB10AA104/LAB10AA105/LAB10AA106 "
    "followed by ordinary words to make the cell wrap over several lines in the report."
)


def analysis_row(
    no, failure_mode, failure_effect, strategy, task, frequency, trade, kks, new_task,
    flags=DEFAULT_FLAGS, review=None, plan=None, remark=None,
) -> list:
    """One row in the 22-column analysis layout."""
    return [no, failure_mode, failure_effect, *flags, strategy, task, frequency, trade, kks,
            new_task, review, plan, remark]


def _write_rows(ws: Worksheet, first_row: int, rows: list[list], first_col: int = 1) -> None:
    for r, values in enumerate(rows, start=first_row):
        for c, value in enumerate(values, start=first_col):
            if value is not None:
                ws.cell(row=r, column=c, value=value)


def to_bytes(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def add_uoir_row(wb: Workbook, uoir_id: int | str, title: str, equipment: str) -> int:
    """Write one more SYNTHETIC row under the last row of the UOIR sheet and return its row number."""
    ws = wb["UOIR"]
    header_row = next(r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=2).value == "UOIR ID")
    row = header_row + 1
    while ws.cell(row=row, column=2).value not in (None, ""):
        row += 1
    _write_rows(ws, row, [[
        row - header_row, uoir_id, title, date(2026, 5, 1), date(2026, 5, 20),
        "SYNTHETIC action.", "SYNTHETIC action.", equipment,
    ]])
    for col in ("D", "E"):
        ws[f"{col}{row}"].number_format = "d-mmm-yy"
    return row


# --------------------------------------------------------------------------- #
# Edge-case variant
# --------------------------------------------------------------------------- #
def make_edge_case_workbook() -> Workbook:
    wb = Workbook()

    # Team Member: text date, zero-padded staff number format, pre-filled No rows.
    team = wb.active
    team.title = "Team Member"
    team["A1"] = "SYNTHETIC TEST DATA - not real people or plant records"
    team["A2"] = "Station: "
    team["B2"] = "SYNTHETIC Station X1"
    team["A3"] = "Date of Analysis:"
    team["B3"] = "15/06/2026"                       # typed as text
    team["A4"] = "Team member "
    team.merge_cells("A4:D4")
    _write_rows(team, 5, [
        ["No ", "Name ", "Staff No ", "Section "],
        [1, "Synthetic Engineer One", 1234, "Mechanical"],
        [2, "Synthetic Engineer Two", 98765432, "Electrical"],
        [3, "Synthetic Engineer Three", "00012345", "Instrument"],
        [4],
        [5],
    ])
    team["C6"].number_format = "00000000"           # shows 00001234 in Excel

    # UOIR list: 501 on two rows with different Equipment; 502 has text dates.
    uoir = wb.create_sheet("UOIR")
    uoir["B2"] = "List of UOIR (SYNTHETIC)"
    _write_rows(uoir, 4, [
        ["No", "UOIR ID", "Title ", "Date of fault", "Date of UOIR", "CA", "PA", "Equipment"],
        [1, 501, EDGE_TITLE_501, date(2026, 1, 10), date(2026, 2, 1), LONG_CORRECTIVE_ACTION,
         "Clean the suction strainer every month (SYNTHETIC).", "Pump A "],
        [2, 501, EDGE_TITLE_501, date(2026, 1, 10), date(2026, 2, 1), "See row above (SYNTHETIC).",
         "See row above (SYNTHETIC).", "Pump B"],
        [3, "502", EDGE_TITLE_502, "03/05/2026", "sometime in May",
         "Replace actuator diaphragm.\r\nRecalibrate positioner.", "Stroke test before start-up.",
         "Feed Valve"],
    ])
    for ref in ("D5", "E5", "D6", "E6"):
        uoir[ref].number_format = "d-mmm-yy"

    # UOIR 501: merges, NBSP blanks, NSM, blank/invalid New Task, duplicate, notes.
    t501 = wb.create_sheet(EDGE_TAB_501)
    t501["B1"] = "SYNTHETIC  Pump Trip due to Low Suction Pressure"   # double space: same title
    t501["D1"] = "SYNTHETIC RCA note - suction strainer blocked by debris"
    _write_rows(t501, 2, [ANALYSIS_HEADERS])
    _write_rows(t501, 3, [
        analysis_row(1, "Suction strainer blocked", "Low suction pressure trips the pump", "OC",
                     "Differential pressure check", "1M", "SYNINCS", "KKS-PUMP-A", "No", plan=800000000001),
        analysis_row(NBSP, None, None, "SR", "Clean strainer", "6M", "synincs", "KKS-PUMP-A", "Yes"),
        analysis_row(NBSP, None, None, "NSM", "Run to failure accepted (SYNTHETIC)", NBSP, "SYNOPER",
                     "KKS-PUMP-A", NBSP),
        analysis_row(2, "Bearing worn", "Vibration high", "OC", "Vibration monitoring", "3M", "SYNMECH",
                     "KKS-PUMP-B", None),
        analysis_row(3, "Mechanical seal leak", "Water on the floor", "FF", "Leak check", "1W", "SYNMECH",
                     "KKS-PUMP-B", "TBC"),
        analysis_row(4, "Motor overheating", NBSP, "SD", "Replace motor cooling fan", "2Y", "SYNELEC",
                     "KKS-PUMP-A", "Yes"),
        analysis_row(5, "Coupling misaligned", "Vibration high", "XYZ", "Laser alignment", "1Y", "SYNMECH ",
                     "KKS-PUMP-B", "Y"),
        analysis_row(6, "Coupling misaligned", "Vibration high", "XYZ", "Laser alignment", "1Y", "SYNMECH",
                     "KKS-PUMP-B", "Y"),
        analysis_row(7, "Impeller eroded", "Flow reduced", "r-pump", "Upgrade impeller material", None,
                     "SYNMECH", "kks-pump-b", "YES"),
        analysis_row(8, "Controller logic fault", LONG_FAILURE_EFFECT, "R-hardware",
                     "Modify trip logic\nAdd 2oo3 voting", "Once", "SYNINCS", "KKS-PUMP-A", " no ",
                     remark=LONG_REMARK),
        # Only non-breaking spaces: counts as a blank row and ends the table.
        [NBSP, NBSP, NBSP] + [None] * 12 + [NBSP],
    ])
    t501["U3"].number_format = "0"
    t501.merge_cells("B3:B5")
    t501.merge_cells("C3:C5")
    t501["X4"] = "SYNTHETIC side note\nsecond line"
    t501.merge_cells("X4:Z6")
    t501["B20"] = "Root Cause (SYNTHETIC) - suction strainer "

    # UOIR 502: header on row 3, blank-header columns, NSM with New Task, formula, blank Trade.
    t502 = wb.create_sheet(EDGE_TAB_502)
    t502["B1"] = EDGE_TITLE_502.lower()               # case differs only: no warning
    t502["A2"] = "SYNTHETIC analysis sheet - header on row 3"
    _write_rows(t502, 3, [
        ["No.", "Failure Mode", "Failure Effect", "Recommended Strategy", None, "Task", "Frequency",
         "Trade", "KKS", "New Task", None, "Remark"],
        [1, "Positioner drift", "Valve does not close fully", "oc", "extra (SYNTHETIC)",
         "Calibrate positioner", "6M", "SYNINCS", "LAB10AA101", "Yes", None, LONG_REMARK],
        [2, "Actuator diaphragm torn", "Valve stuck open", "NSM", None, "Run to failure accepted", None,
         "SYNOPER", "LAB10AA101", "No"],
        [3, "Solenoid coil burnt", "Valve fails open", "N/A", None, "Not analysed yet", None,
         "SYNELEC", "LAB10AA101", "no", None, "=1+1"],
        [4, "Stem packing leak", "Steam leak at the gland", "R-Spare", None, "Keep spare packing in store",
         None, None, "LAB10AA101", "Yes"],
    ])

    # A tab for a UOIR that is not on the UOIR sheet.
    t999 = wb.create_sheet(EDGE_TAB_UNLISTED)
    t999["B1"] = "SYNTHETIC tab for a UOIR that is not listed"
    _write_rows(t999, 2, [ANALYSIS_HEADERS, analysis_row(1, "Unlisted mode", "Unlisted effect", "OC",
                                                          "Unlisted task", "1M", "SYNMECH", "KKS-X", "Yes")])

    extra = wb.create_sheet("Extra Notes")
    extra["A1"] = "SYNTHETIC scratch notes that are not part of the report"

    _add_ignored_sheets(wb)
    return wb


# --------------------------------------------------------------------------- #
# Clean variant
# --------------------------------------------------------------------------- #
def make_clean_workbook() -> Workbook:
    wb = Workbook()
    team = wb.active
    team.title = "Team Member"
    team["A1"] = "SYNTHETIC TEST DATA"
    team["A2"] = "Station:"
    team["B2"] = "SYNTHETIC Clean Station"
    team["A3"] = "Date of Analysis:"
    team["B3"] = date(2026, 6, 15)
    team["B3"].number_format = "d-mmm-yy"
    _write_rows(team, 5, [
        ["No", "Name", "Staff No", "Section"],
        [1, "Synthetic Person A", 11112222, "Mechanical"],
        [2, "Synthetic Person B", 33334444, "Electrical"],
    ])

    uoir = wb.create_sheet("UOIR")
    _write_rows(uoir, 4, [
        ["No", "UOIR ID", "Title", "Date of fault", "Date of UOIR", "CA", "PA", "Equipment"],
        [1, 601, CLEAN_TITLE_601, date(2026, 3, 1), date(2026, 3, 20), "Replace impeller (SYNTHETIC).",
         "Monthly flow check (SYNTHETIC).", "Clean Pump"],
        [2, 602, CLEAN_TITLE_602, date(2026, 4, 2), date(2026, 4, 20), "Replace positioner (SYNTHETIC).",
         "Stroke test each outage (SYNTHETIC).", "Clean Valve"],
    ])
    for ref in ("D5", "E5", "D6", "E6"):
        uoir[ref].number_format = "d-mmm-yy"

    t601 = wb.create_sheet(CLEAN_TAB_601)
    t601["B1"] = CLEAN_TITLE_601
    _write_rows(t601, 2, [
        ANALYSIS_HEADERS,
        analysis_row(1, "Impeller wear", "Reduced flow", "OC", "Flow check", "1M", "SYNMECH", "KKS-CLEAN-1", "No"),
        analysis_row(2, "Seal leak", "Loss of water", "SR", "Replace seal", "2Y", "SYNMECH", "KKS-CLEAN-1", "Yes"),
        analysis_row(3, "Bearing noise", "Pump trip", "NSM", "Run to failure accepted", None, "SYNOPER",
                     "KKS-CLEAN-1", None),
        analysis_row(4, "Motor winding fault", "Pump trip", "R-Spare", "Keep a spare motor", None, "SYNELEC",
                     "KKS-CLEAN-2", "No"),
    ])

    t602 = wb.create_sheet(CLEAN_TAB_602)
    t602["B1"] = CLEAN_TITLE_602
    _write_rows(t602, 2, [
        ANALYSIS_HEADERS,
        analysis_row(1, "Actuator air leak", "Valve fails to modulate", "OC", "Stroke test", "3M", "SYNINCS",
                     "KKS-CLEAN-3", "Yes"),
        analysis_row(2, "Diaphragm torn", "Valve stuck", "FF", "Function test", "6M", "SYNINCS",
                     "KKS-CLEAN-3", "No"),
    ])

    _add_ignored_sheets(wb)
    return wb


# --------------------------------------------------------------------------- #
# Sample-like variant: the layout of a full engineer workbook, invented content
# --------------------------------------------------------------------------- #
SAMPLE_STATION = "SYNTHETIC Station S9"
SAMPLE_ANALYSIS_DATE = date(2025, 10, 6)        # earlier than every fault date; taken as written

SAMPLE_TITLE_712 = "Turbine ESD (Emergency Shut Down) due to SYNTHETIC Lube Oil Pressure Switch Fault"
SAMPLE_TITLE_705 = "SYNTHETIC Unit Trip on Deaerator Level Transmitter Drift"
SAMPLE_TITLE_748 = "SYNTHETIC Condensate Recirculation Valve Hunting due to Worn Actuator Linkage"


def analysis_tab_name(uoir_id: int | str | list[int | str] | tuple[int | str, ...], fragment: str) -> str:
    """'UOIR ID <id> - <fragment>' cut to Excel's 31-character tab-name limit.

    Several IDs (a list or tuple) are joined with spaces: 'UOIR ID 901 902 - <fragment>'.
    """
    ids = " ".join(str(i) for i in uoir_id) if isinstance(uoir_id, (list, tuple)) else uoir_id
    return f"UOIR ID {ids} - {fragment}"[:31].rstrip()


SAMPLE_TAB_712 = analysis_tab_name(712, SAMPLE_TITLE_712)                       # "UOIR ID 712 - Turbine ESD (Emer"
SAMPLE_TAB_705 = analysis_tab_name(705, "Deaerator Level Transmitter Drift")    # fragment from the middle
SAMPLE_TAB_748 = analysis_tab_name(748, SAMPLE_TITLE_748)                       # "UOIR ID 748 - SYNTHETIC Condens"

SAMPLE_EQUIPMENT_712 = "SYNTHETIC Lube Oil Pressure Switch Rack"
SAMPLE_EQUIPMENT_705 = "SYNTHETIC Deaerator Level Transmitter"
SAMPLE_EQUIPMENT_748 = "SYNTHETIC Condensate Recirculation Valve"

SAMPLE_KKS_712_A = "SYN10/AB020-120"
SAMPLE_KKS_712_B = "SYN11/AC300-390 XS01-02"
SAMPLE_KKS_705 = "SYN30/CP101-102"
SAMPLE_KKS_748 = "SYN40AA310/320"

SAMPLE_NOTE_712 = "Root Cause (SYNTHETIC) - lube oil pressure switch diaphragm fatigue"
SAMPLE_NOTE_748 = "RCA (SYNTHETIC) - recirculation valve hunting at low load. Actuator linkage worn"

# (name, staff number, section); staff numbers are numeric cells, as in Excel.
SAMPLE_TEAM = [
    ("SYNTHETIC Member Alpha", 70001001, "Mechanical"),
    ("SYNTHETIC Member Bravo", 70001002, "Electrical"),
    ("SYNTHETIC Member Charlie", 70001003, "Instrument"),
    ("SYNTHETIC Member Delta", 70001004, "Operations"),
    ("SYNTHETIC Member Echo", 70001005.0, "Reliability"),     # stored as a float: must not show ".0"
    ("SYNTHETIC Member Foxtrot", 70001006, "Boiler"),
    ("SYNTHETIC Member Golf", 70001007, "Turbine"),
]

# H, S, E, O, 1, 2, 3, H4, H5, S4 with non-breaking spaces where nothing was entered.
NBSP_FLAGS = ("Y", "N", "N", "Y", "N", "N", "N", NBSP, NBSP, NBSP)


def _sample_rows_712() -> list[list]:
    """12 rows, two KKS values, one failure mode over three task rows (blank No. on the repeats)."""
    a, b = SAMPLE_KKS_712_A, SAMPLE_KKS_712_B
    spare_effect = "Long outage while a replacement switch is ordered (SYNTHETIC)"
    return [
        analysis_row(1, "Pressure switch diaphragm cracked",
                     "False low lube oil pressure signal trips the turbine (SYNTHETIC)", "OC",
                     "Compare the switch set point with a test gauge", "6M", "SYNINCS", a, "No",
                     review="Keep (SYNTHETIC)", plan=900000000101),
        analysis_row(2, "Switch contacts oxidised", "Switch does not change over; trip signal lost (SYNTHETIC)",
                     "OC", "Clean and test the switch contacts", "1Y", "SYNINCS", b, "Yes",
                     review="Add (SYNTHETIC)"),
        analysis_row(3, "Impulse line partly blocked", "Slow pressure response at the switch (SYNTHETIC)", "SD",
                     "Replace the impulse line snubber", "2Y", "SYNMECH", a, "No", plan=900000000102),
        analysis_row(4, "Trip logic votes one out of two", "A single faulty switch trips the unit (SYNTHETIC)",
                     "R-hardware", "Change the trip logic to two out of three voting", "Once", "SYNINCS", a,
                     "Yes ", remark="Design change request raised (SYNTHETIC)"),
        analysis_row(5, "No spare switch in store", spare_effect, "R-Spare", "Keep two spare switches in store",
                     None, "SYNOPER", a, "No"),
        analysis_row(None, "No spare switch in store", spare_effect, "R-Spare",
                     "Keep one spare switch element in store", None, "SYNOPER", a, "Yes"),
        analysis_row(None, "No spare switch in store", spare_effect, "R-Spare",
                     "Add the switch to the critical spares list", None, "SYNELEC", a, "No"),
        analysis_row(6, "Terminal screws loose", "Intermittent switch signal (SYNTHETIC)", "OC",
                     "Torque-check the terminal screws", "1Y", "SYNELEC", a, "Yes"),
        analysis_row(7, "Trip relay coil open circuit", "Trip command not passed on (SYNTHETIC)", "FF",
                     "Function test the trip relay", "6M", "SYNELEC", a, "Yes"),
        analysis_row(8, "Trip relay contacts welded", "Unit cannot be reset after a trip (SYNTHETIC)", "SD",
                     "Replace the trip relays", "4Y", "SYNELEC", a, "No", plan=900000000103),
        analysis_row(9, "Switch housing corroded", "Moisture reaches the switch element (SYNTHETIC)", "OC",
                     "Inspect the switch housing seals", "3M", "SYNMECH", a, "NO"),
        analysis_row(10, "Switch isolation valve left closed",
                     "Switch sees no pressure after maintenance (SYNTHETIC)", "OC",
                     "Confirm the switch isolation valve is open after work", "1M", "SYNOPER", a, "Yes"),
    ]


def _sample_rows_705() -> list[list]:
    """7 rows typed with non-breaking spaces for every blank (No., H4/H5/S4, NSM New Task, ...)."""
    k = SAMPLE_KKS_705

    def row(*values, **extra):
        return analysis_row(NBSP, *values, flags=NBSP_FLAGS, review=NBSP, remark=NBSP, **extra)

    return [
        row("Transmitter output drifts high", "Level control lowers the deaerator level (SYNTHETIC)", "OC",
            "Compare the transmitter with the gauge glass", "1M", "SYNINCS", k, "No"),
        row("Condensate pot empty", "Wrong level reading (SYNTHETIC)", "OC",
            "Refill the condensate pot and check for leaks", "3M", "SYNINCS", k, "Yes"),
        row("Transmitter electronics failed", "Level signal lost; unit trips on bad quality (SYNTHETIC)", "FF",
            "Test the bad-quality alarm and trip path", "6M", "SYNINCS", k, "Yes"),
        row("Gauge glass dirty", "Operator cannot confirm the level locally (SYNTHETIC)", "NSM",
            "No scheduled task; clean when found dirty (SYNTHETIC)", NBSP, "SYNOPER", k, NBSP),
        row("Trip logic uses one transmitter only", "A single transmitter fault trips the unit (SYNTHETIC)",
            NBSP + "R-software", "Add median select of three transmitters to the control logic", "Once",
            "SYNINCS", k, "Yes"),
        row("Manifold valve passing", "Level reading creeps (SYNTHETIC)", "SR",
            "Overhaul the transmitter manifold valves", "2Y", "SYNMECH", k, "Yes"),
        row("Transmitter cable gland loose", "Moisture enters the transmitter housing (SYNTHETIC)", "OC",
            "Inspect the transmitter cable glands", "6M", "SYNINCS", k, "No"),
    ]


def _sample_rows_748() -> list[list]:
    """9 rows, one KKS, no NSM."""
    k = SAMPLE_KKS_748
    return [
        analysis_row(1, "Linkage pins worn", "Valve position overshoots and flow hunts (SYNTHETIC)", "OC",
                     "Measure the linkage free play", "3M", "SYNINCS", k, "No", plan=900000000201),
        analysis_row(2, "Positioner feedback arm loose", "Valve does not follow the demand (SYNTHETIC)", "OC",
                     "Check the feedback arm fixing", "3M", "SYNINCS", k, "No", plan=900000000202),
        analysis_row(3, "Actuator spring fatigued", "Valve slow to close (SYNTHETIC)", "OC",
                     "Record the actuator stroke time", "6M", "SYNBOIL", k, "Yes"),
        analysis_row(4, "Valve stem bent", "Valve sticks part open (SYNTHETIC)", "SD", "Replace the valve stem",
                     "4Y", "SYNBOIL", k, "No", plan=900000000203),
        analysis_row(5, "Air supply filter blocked", "Actuator starved of air (SYNTHETIC)", "OC",
                     "Drain and inspect the air filter", "1M", "SYNINCS", k, "NO"),
        analysis_row(6, "No written stroke check procedure", "Faults are found late (SYNTHETIC)", "R-Pro",
                     "Write a stroke check procedure (SYNTHETIC)", "Once", "SYNOPER", k, "Yes"),
        analysis_row(7, "No spare linkage kit", "Long repair time (SYNTHETIC)", "R-Spare",
                     "Keep a spare linkage kit in store", None, "SYNINCS", k, "Yes"),
        analysis_row(8, "Valve seat eroded", "Recirculation flow passes when closed (SYNTHETIC)", "SR",
                     "Lap the valve seat", "4Y", "SYNINCS", k, "Yes"),
        analysis_row(9, "Limit switch out of adjustment",
                     "Wrong valve position shown in the control room (SYNTHETIC)", "FF",
                     "Check the limit switch change-over", "1Y", "SYNOPER", k, "Yes"),
    ]


def make_sample_like_workbook(notification_rows: int = 300) -> Workbook:
    """A full-size look-alike of an engineer workbook with invented content and no issues at all."""
    wb = Workbook()

    # Team Member: labels with trailing spaces, header on row 5 with trailing spaces,
    # numeric staff numbers and two pre-numbered rows with nothing else filled in.
    team = wb.active
    team.title = "Team Member"
    team["A1"] = "SYNTHETIC TEST DATA - not real people or plant records"
    team["A2"] = "Station: "
    team["B2"] = SAMPLE_STATION
    team["A3"] = "Date of Analysis:"
    team["B3"] = SAMPLE_ANALYSIS_DATE
    team["B3"].number_format = "d-mmm-yy"
    team["A4"] = "Team member "
    team.merge_cells("A4:D4")
    members = [[n, name, staff_no, section] for n, (name, staff_no, section) in enumerate(SAMPLE_TEAM, start=1)]
    pre_numbered = [[n] for n in range(len(SAMPLE_TEAM) + 1, len(SAMPLE_TEAM) + 3)]
    _write_rows(team, 5, [["No ", "Name ", "Staff No ", "Section "], *members, *pre_numbered])

    # UOIR list: header on row 4, numeric IDs listed out of order, multi-line CA/PA,
    # an Equipment value with a trailing space.
    uoir = wb.create_sheet("UOIR")
    uoir["B2"] = "List of UOIR (SYNTHETIC)"
    _write_rows(uoir, 4, [
        ["No", "UOIR ID", "Title ", "Date of fault", "Date of UOIR", "CA", "PA", "Equipment"],
        [1, 712, SAMPLE_TITLE_712, date(2026, 2, 14), date(2026, 2, 20),
         "1. Replaced both lube oil pressure switches (SYNTHETIC).\n2. Checked the trip settings against a "
         "test gauge.\n3. Returned the unit to service under observation.",
         "1. Add the switches to the six-monthly calibration list (SYNTHETIC).\n2. Review the trip voting logic.",
         SAMPLE_EQUIPMENT_712 + " "],
        [2, 705, SAMPLE_TITLE_705, date(2026, 3, 21), date(2026, 3, 30),
         "Recalibrated the deaerator level transmitter (SYNTHETIC).\nRefilled the condensate pot.",
         "Monthly comparison with the gauge glass (SYNTHETIC).", SAMPLE_EQUIPMENT_705],
        [3, 748, SAMPLE_TITLE_748, date(2026, 4, 27), date(2026, 5, 8),
         "1. Replaced the actuator linkage pins (SYNTHETIC).\n2. Retuned the positioner.",
         "Quarterly linkage free-play check (SYNTHETIC).", SAMPLE_EQUIPMENT_748],
    ])
    for row in range(5, 8):
        for col in ("D", "E"):
            uoir[f"{col}{row}"].number_format = "d-mmm-yy"

    # Analysis tabs: B1 = full title, the 22-column header on row 2.
    t712 = wb.create_sheet(SAMPLE_TAB_712)
    t712["B1"] = SAMPLE_TITLE_712
    _write_rows(t712, 2, [ANALYSIS_HEADERS, *_sample_rows_712()])
    t712["B18"] = SAMPLE_NOTE_712                    # below the table, after empty rows

    t705 = wb.create_sheet(SAMPLE_TAB_705)
    t705["B1"] = SAMPLE_TITLE_705
    _write_rows(t705, 2, [ANALYSIS_HEADERS, *_sample_rows_705()])

    t748 = wb.create_sheet(SAMPLE_TAB_748)
    t748["B1"] = SAMPLE_TITLE_748
    t748["C1"] = SAMPLE_NOTE_748                     # next to the title, above the table
    _write_rows(t748, 2, [ANALYSIS_HEADERS, *_sample_rows_748()])

    # Ignored sheets: a long notification export and a scratch sheet.
    notifications = wb.create_sheet("Notifications")
    notifications.append(["Notification", "Type", "Description", "Functional Location", "Created On"])
    for n in range(1, notification_rows + 1):
        notifications.append([
            90000000 + n, "M2", f"SYNTHETIC notification {n:03d} (never read by the report)",
            f"SYN-FL-{n % 40:02d}", date(2026, 1, 1) + timedelta(days=n % 300),
        ])
    sheet3 = wb.create_sheet("Sheet3")
    sheet3["A1"] = "SYNTHETIC scratch sheet (never read by the report)"
    return wb


def _add_ignored_sheets(wb: Workbook) -> None:
    notifications = wb.create_sheet("Notifications")
    _write_rows(notifications, 1, [
        ["SYNTHETIC notification export (never read by the report)"],
        ["Notification", "Description"],
        [90000001, "SYNTHETIC notification"],
    ])
    sheet3 = wb.create_sheet("Sheet3")
    sheet3["A1"] = "SYNTHETIC scratch sheet (never read by the report)"


def build_edge_case_workbook() -> bytes:
    return to_bytes(make_edge_case_workbook())


def build_clean_workbook() -> bytes:
    return to_bytes(make_clean_workbook())


def build_sample_like_workbook() -> bytes:
    return to_bytes(make_sample_like_workbook())


VARIANTS = {"edge": build_edge_case_workbook, "clean": build_clean_workbook, "sample": build_sample_like_workbook}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a SYNTHETIC FMEA workbook.")
    parser.add_argument("output", nargs="?", help="where to write the .xlsx (omit to only build it)")
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="edge")
    args = parser.parse_args(argv)

    data = VARIANTS[args.variant]()
    if args.output:
        path = Path(args.output)
        path.write_bytes(data)
        print(f"Wrote SYNTHETIC {args.variant} workbook ({len(data):,} bytes) to {path}")
    else:
        print(f"Built SYNTHETIC {args.variant} workbook ({len(data):,} bytes); pass a path to save it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
