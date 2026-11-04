"""SYNTHETIC `Report` fixtures for the PDF tests.

Built directly from `backend.report.models` (no workbook, no parser). All names,
IDs, codes and text are invented and labelled SYNTHETIC. Every analysis row and
every recommendation row carries a unique marker so tests can prove that no row
was dropped from the PDF.

This module holds builders and PDF inspection helpers only (no tests).
"""
from __future__ import annotations

import random
from datetime import date, datetime

from backend.config.mapping import STANDARD_STRATEGY_CODES, strategy_color, strategy_label
from backend.report.models import (
    AnalysisRow,
    AnalysisTable,
    FailureDetail,
    MergedRange,
    Note,
    NotCountedRow,
    PieSlice,
    RecommendationGroup,
    RecommendationRow,
    Report,
    StrategyRow,
    Summary,
    TeamMember,
    UoirSection,
    WorkCentreRow,
)

ANALYSIS_COLUMNS = [
    "No.", "Failure Mode", "Failure Effect", "H", "S", "E", "O", "1", "2", "3", "H4", "H5", "S4",
    "RecommendedStrategy", "Task", "Frequency", "Trade", "KKS", "New Task", "Review task",
    "Maintenance Plan No", "Remark",
]
COL = {name: index for index, name in enumerate(ANALYSIS_COLUMNS)}
LONG_KKS = "SYN11/AB920-980XV03-04-LONGCODE123456"

FAILURE_MODES = [
    "SYNTHETIC damper actuator fails to stroke",
    "SYNTHETIC limit switch misaligned",
    "SYNTHETIC solenoid valve coil burnt",
    "SYNTHETIC positioner feedback arm loose",
    "SYNTHETIC air supply regulator drifting",
]
FAILURE_EFFECTS = [
    "SYNTHETIC unit trip on protection relay logic; unit offline until reset",
    "SYNTHETIC loss of indication in control room; operator cannot confirm position",
    "SYNTHETIC reduced outlet flow control; efficiency loss",
]
TASKS = [
    "SYNTHETIC stroke test and record opening time",
    "SYNTHETIC inspect and adjust limit switch cams",
    "SYNTHETIC replace solenoid coil & check wiring <terminal block>",
    "SYNTHETIC calibrate positioner against reference signal",
]
STRATEGIES = ["OC", "SD", "R-SPARE", "FF", "R-HARDWARE", "SR"]
TRADES = ["SYNINCS", "SYNELEC", "SYNCASH", "SYNOPER"]
FREQUENCIES = ["1M", "3M", "6M", "1Y", "2Y"]


def analysis_marker(uoir_id: str, index: int) -> str:
    return f"AR{uoir_id}N{index:03d}"


def recommendation_marker(uoir_id: str, index: int) -> str:
    return f"RR{uoir_id}N{index:03d}"


def column_letters(count: int) -> list[str]:
    letters = []
    for i in range(count):
        n, name = i + 1, ""
        while n:
            n, rem = divmod(n - 1, 26)
            name = chr(65 + rem) + name
        letters.append(name)
    return letters


# --------------------------------------------------------------------------- #
# Analysis tables
# --------------------------------------------------------------------------- #
def build_analysis(uoir_id: str, group_sizes: list[int], *, header_row: int = 2, rng: random.Random,
                   long_kks_every: int = 0, tall_remark_row: int | None = None,
                   tall_merged_group: int | None = None, horizontal_merge_row: int | None = None
                   ) -> tuple[AnalysisTable, list[dict]]:
    """Rows grouped by failure mode; No./Failure Mode/Failure Effect merged over each group.

    Returns the table and a plain description of each row (used to derive the
    summary and recommendations)."""
    rows: list[AnalysisRow] = []
    merged: list[MergedRange] = []
    described: list[dict] = []
    index = 0
    for group_number, size in enumerate(group_sizes):
        first = index
        failure_mode = f"{rng.choice(FAILURE_MODES)} (group {group_number + 1})"
        if tall_merged_group == group_number:
            failure_mode += "\n" + "\n".join(f"SYNTHETIC merged detail line {i + 1}" for i in range(120))
        failure_effect = rng.choice(FAILURE_EFFECTS)
        for k in range(size):
            cells = [""] * len(ANALYSIS_COLUMNS)
            if k == 0:
                cells[COL["No."]] = str(group_number + 1)
                cells[COL["Failure Mode"]] = failure_mode
                cells[COL["Failure Effect"]] = failure_effect
            for flag in ("H", "S", "E", "O", "1", "2", "3", "H4", "H5", "S4"):
                cells[COL[flag]] = rng.choice(["Y", "N", ""])
            strategy = STRATEGIES[index % len(STRATEGIES)]
            trade = TRADES[index % len(TRADES)]
            kks = LONG_KKS if long_kks_every and index % long_kks_every == 0 else f"SYN10/AA{index % 7:03d}"
            new_task = "Yes" if index % 3 == 0 else "No"
            task = f"{analysis_marker(uoir_id, index)} {rng.choice(TASKS)}"
            cells[COL["RecommendedStrategy"]] = strategy
            cells[COL["Task"]] = task
            cells[COL["Frequency"]] = rng.choice(FREQUENCIES)
            cells[COL["Trade"]] = trade
            cells[COL["KKS"]] = kks
            cells[COL["New Task"]] = new_task
            cells[COL["Maintenance Plan No"]] = f"SYN{400000 + index}"
            cells[COL["Remark"]] = rng.choice(["", "SYNTHETIC check OEM manual", "SYNTHETIC align with outage"])
            if tall_remark_row == index:
                cells[COL["Remark"]] = "\n".join(f"SYNTHETIC remark line {i + 1:03d}" for i in range(120))
            if horizontal_merge_row == index:
                cells[COL["Review task"]] = "SYNTHETIC review spans two columns"
                cells[COL["Maintenance Plan No"]] = ""
                merged.append(MergedRange(first_row=index, first_col=COL["Review task"],
                                          last_row=index, last_col=COL["Maintenance Plan No"]))
            rows.append(AnalysisRow(source_row=header_row + 1 + index, cells=cells))
            described.append(dict(index=index, source_row=header_row + 1 + index,
                                  failure_mode=failure_mode, task=task, strategy=strategy, trade=trade,
                                  kks=kks, new_task=new_task.lower(),
                                  frequency=cells[COL["Frequency"]]))
            index += 1
        if size > 1:
            for col in ("No.", "Failure Mode", "Failure Effect"):
                merged.append(MergedRange(first_row=first, first_col=COL[col],
                                          last_row=first + size - 1, last_col=COL[col]))
    table = AnalysisTable(
        sheet=f"UOIR ID {uoir_id} - SYNTHETIC",
        header_row=header_row,
        columns=list(ANALYSIS_COLUMNS),
        column_letters=column_letters(len(ANALYSIS_COLUMNS)),
        rows=rows,
        merged=merged,
    )
    return table, described


def largest_remainder_percent(counts: list[int]) -> list[float]:
    total = sum(counts)
    if total == 0:
        return [0.0 for _ in counts]
    raw = [c * 1000 / total for c in counts]
    floors = [int(r) for r in raw]
    remaining = 1000 - sum(floors)
    order = sorted(range(len(counts)), key=lambda i: -(raw[i] - floors[i]))
    for i in order[:remaining]:
        floors[i] += 1
    return [f / 10 for f in floors]


def build_summary(described: list[dict], *, codes: list[str] | None = None) -> Summary:
    codes_seen = []
    for d in described:
        if d["strategy"] not in codes_seen:
            codes_seen.append(d["strategy"])
    ordered = list(STANDARD_STRATEGY_CODES) + [c for c in (codes or codes_seen) if c not in STANDARD_STRATEGY_CODES]
    strategy_rows = []
    for code in ordered:
        mine = [d for d in described if d["strategy"] == code]
        strategy_rows.append(StrategyRow(
            code=code, label=strategy_label(code),
            existing=sum(1 for d in mine if d["new_task"] == "no"),
            new=sum(1 for d in mine if d["new_task"] == "yes"),
            total=len(mine), color=strategy_color(code), standard=code in STANDARD_STRATEGY_CODES,
        ))
    charted = [r for r in strategy_rows if r.total > 0]
    percents = largest_remainder_percent([r.total for r in charted])
    pie = [PieSlice(code=r.code, label=r.label, count=r.total, percent=p, color=r.color)
           for r, p in zip(charted, percents)]
    centres: dict[str, WorkCentreRow] = {}
    for d in described:
        row = centres.setdefault(d["trade"], WorkCentreRow(work_centre=d["trade"], total=0, executed=0, pending=0))
        row.total += 1
        if d["new_task"] == "no":
            row.executed += 1
        else:
            row.pending += 1
    return Summary(
        failure_mode_count=len(described),
        maintenance_task_count=sum(1 for d in described if d["strategy"] != "NSM"),
        task_executed_count=sum(1 for d in described if d["new_task"] == "no"),
        strategy_rows=strategy_rows,
        pie=pie,
        pie_total=sum(s.count for s in pie),
        work_centre_rows=sorted(centres.values(), key=lambda r: -r.total),
    )


def build_recommendations(uoir_id: str, equipment: list[str], described: list[dict],
                          kks_names: list[str], *, tall_task_row: int | None = None) -> list[RecommendationGroup]:
    groups: dict[str, RecommendationGroup] = {}
    joined = " / ".join(equipment)
    for position, d in enumerate(described):
        kks = kks_names[position % len(kks_names)]
        task = f"{recommendation_marker(uoir_id, position)} {d['task']}"
        if tall_task_row == position:
            task += "\n" + "\n".join(f"SYNTHETIC task step {i + 1:03d}" for i in range(120))
        group = groups.setdefault(kks, RecommendationGroup(
            equipment=joined, kks=kks, heading=f"{joined}, {kks}" if joined else kks, rows=[]))
        group.rows.append(RecommendationRow(source_row=d["source_row"], failure_mode=d["failure_mode"],
                                            task=task, frequency=d["frequency"], new_task=d["new_task"]))
    return list(groups.values())


def _failure_detail(no: int, uoir_id: str, title: str, equipment: str, *, tall: bool = False) -> FailureDetail:
    corrective = "SYNTHETIC replaced actuator\nSYNTHETIC tested interlocks\nSYNTHETIC returned to service"
    if tall:
        corrective = "\n".join(f"SYNTHETIC corrective step {i + 1:03d}" for i in range(120))
    return FailureDetail(
        no=str(no), uoir_id=uoir_id, title=title,
        faulty_date=date(2026, 5, no), faulty_date_text=f"{no} May 2026",
        uoir_date=date(2026, 5, no + 1), uoir_date_text=f"{no + 1} May 2026",
        corrective_action=corrective,
        preventive_action="SYNTHETIC add stroke test to PM plan\nSYNTHETIC review spares",
        equipment=equipment, source_row=4 + no,
    )


def _team(count: int) -> list[TeamMember]:
    sections = ["SYNTHETIC Instrument & Control", "SYNTHETIC Electrical", "SYNTHETIC Operations"]
    return [
        TeamMember(no=str(i + 1), name=f"SYNTHETIC Engineer {i + 1:02d}", staff_no=f"{9000000 + i:08d}",
                   section=sections[i % len(sections)], source_row=6 + i)
        for i in range(count)
    ]


def _report(station: str, team: list[TeamMember], details: list[FailureDetail],
            uoirs: list[UoirSection]) -> Report:
    return Report(
        source_filename="SYNTHETIC_fmea_workbook.xlsx",
        station=station,
        analysis_date=date(2026, 9, 14),
        analysis_date_text="14 September 2026",
        team=team,
        failure_details=details,
        uoirs=uoirs,
        issues=[],
        can_export=True,
        pdf_filename="FMEA_Report_SYNTHETIC_2026-09-14.pdf",
        generated_at=datetime(2026, 9, 17, 9, 30),
    )


# --------------------------------------------------------------------------- #
# Normal report: 3 UOIRs
# --------------------------------------------------------------------------- #
NORMAL_STATION = "SYNTHETIC Power Station"


def normal_report() -> Report:
    rng = random.Random(9101)
    specs = [
        ("9101", "SYNTHETIC Unit Trip (Main Relay) on inlet damper", ["SYNTHETIC Inlet Isolation Damper"],
         [3, 1, 2, 1, 4], ["SYN10/AB020-120", "SYN11/AB920-980 XV03-04"],
         [Note(cell="B19", text="SYNTHETIC root cause - inlet isolation damper")], 5),
        ("9102", "SYNTHETIC cooling water temperature sensor fault", ["SYNTHETIC Cooling Water Sensor"],
         [2, 1, 1, 2], ["SYN10/AB020-120"], [], None),
        ("9103", "SYNTHETIC outlet flow control & actuator <slow>", ["SYNTHETIC Flow Actuator",
                                                                        "SYNTHETIC Flow Valve"],
         [1, 3, 2, 1, 3], ["SYN7XYZ40AB120/140", "SYN7XYZ40AB150"],
         [Note(cell="C1", text="SYNTHETIC RCA - actuator air supply leak"),
          Note(cell="B20", text="SYNTHETIC second note\nwith a second line")], None),
    ]
    uoirs, details = [], []
    for no, (uoir_id, title, equipment, groups, kks_names, notes, hmerge) in enumerate(specs, start=1):
        table, described = build_analysis(uoir_id, groups, rng=rng, horizontal_merge_row=hmerge)
        summary = build_summary(described)
        summary.not_counted = [NotCountedRow(source_row=8, reason="New Task blank", strategy="OC", trade="SYNINCS")]
        summary.duplicate_rows = [9] if uoir_id == "9101" else []
        uoirs.append(UoirSection(
            uoir_id=uoir_id, title=title, equipment=equipment, sheet_name=table.sheet, notes=notes,
            analysis=table, summary=summary,
            recommendations=build_recommendations(uoir_id, equipment, described, kks_names),
        ))
        details.append(_failure_detail(no, uoir_id, title, equipment[0]))
    return _report(NORMAL_STATION, _team(7), details, uoirs)


# --------------------------------------------------------------------------- #
# Stress report
# --------------------------------------------------------------------------- #
STRESS_STATION = (
    "SYNTHETIC Stress Test Combined Cycle Power Station With An Exceptionally Long Official Name "
    "Used Only For Layout Testing Of Units One Two Three And Four"
)
STRESS_TITLE = (
    "SYNTHETIC very long UOIR title describing a repeated feed pump protection trip caused by the inlet "
    "isolation damper actuator failing to stroke during start-up, with loss of indication in the control "
    "room, delayed operator response and subsequent forced outage of the unit for several days while the "
    "root cause analysis team investigated the air supply, the solenoid valves and the limit switches"
)
TWELVE_CODES = ["OC", "SR", "SD", "FF", "NSM", "R-SPARE", "N/A", "R-HARDWARE", "R-SOFTWARE", "R-PRO",
                "R-CIVIL", "XYZ-UNKNOWN"]


def stress_report() -> Report:
    rng = random.Random(2026)

    # UOIR A: 400 rows, random merged groups, one merged group taller than a page,
    # one 120-line cell and many long unbreakable KKS tokens; 12 strategies.
    sizes, total = [], 0
    while total < 400:
        size = rng.choice([1, 1, 2, 3, 4]) if len(sizes) != 20 else 70
        size = min(size, 400 - total)
        sizes.append(size)
        total += size
    table_a, described_a = build_analysis("9001", sizes, rng=rng, long_kks_every=5, tall_remark_row=250)
    for i, d in enumerate(described_a):  # spread 12 strategy codes over the rows
        code = TWELVE_CODES[i % len(TWELVE_CODES)]
        d["strategy"] = code
        table_a.rows[i].cells[COL["RecommendedStrategy"]] = code
    summary_a = build_summary(described_a, codes=TWELVE_CODES)
    summary_a.not_counted = [NotCountedRow(source_row=10 + i, reason="New Task is not Yes or No",
                                           strategy="OC", trade="") for i in range(6)]
    summary_a.duplicate_rows = [30, 31, 32]

    # UOIR B: small table, empty pie, no work-centre rows.
    table_b, described_b = build_analysis("9002", [2, 2, 1, 3, 2, 5, 5], rng=rng)
    summary_b = Summary(
        failure_mode_count=0, maintenance_task_count=0, task_executed_count=0,
        strategy_rows=[StrategyRow(code=c, label=strategy_label(c), existing=0, new=0, total=0,
                                   color=strategy_color(c), standard=True) for c in STANDARD_STRATEGY_CODES]
        + [StrategyRow(code="", label="Not specified", existing=0, new=0, total=0, color="#c3c2b7", standard=False)],
        pie=[], pie_total=0, work_centre_rows=[],
    )

    # UOIR C: merged Failure Mode text taller than a page (120 lines over 3 rows).
    table_c, described_c = build_analysis("9003", [3, 3, 2, 4, 3, 2, 3, 2, 4, 4], rng=rng, tall_merged_group=1)
    summary_c = build_summary(described_c)

    long_equipment = ["SYNTHETIC Inlet Duct Isolation Gate Damper Assembly North Side",
                      "SYNTHETIC Inlet Duct Isolation Gate Damper Assembly South Side"]
    uoirs = [
        UoirSection(
            uoir_id="9001", title=STRESS_TITLE, equipment=long_equipment, sheet_name=table_a.sheet,
            notes=[Note(cell="B19", text="SYNTHETIC root cause note"),
                   Note(cell="B20", text="SYNTHETIC long note " + "with many words " * 40),
                   Note(cell="C1", text="SYNTHETIC note\nacross\nfour lines\nof text")],
            analysis=table_a, summary=summary_a,
            recommendations=build_recommendations("9001", long_equipment, described_a[:150],
                                                  [LONG_KKS, "SYN10/AB020-120", "SYN11/AC300-390", "SYN12/BB100",
                                                   "SYN13/CC200"], tall_task_row=40),
        ),
        UoirSection(
            uoir_id="9002", title="SYNTHETIC empty summary UOIR", equipment=["SYNTHETIC Equipment B"],
            sheet_name=table_b.sheet, analysis=table_b, summary=summary_b,
            recommendations=build_recommendations("9002", ["SYNTHETIC Equipment B"], described_b[:20],
                                                  ["SYN20/AA001", "SYN21/AA002", "SYN22/AA003"]),
        ),
        UoirSection(
            uoir_id="9003", title="SYNTHETIC tall merged failure mode", equipment=["SYNTHETIC Equipment C"],
            sheet_name=table_c.sheet, analysis=table_c, summary=summary_c,
            recommendations=build_recommendations("9003", ["SYNTHETIC Equipment C"], described_c,
                                                  ["SYN30/AA001", "SYN31/AA002"]),
        ),
    ]
    details = [
        _failure_detail(1, "9001", STRESS_TITLE, long_equipment[0], tall=True),
        _failure_detail(2, "9002", "SYNTHETIC empty summary UOIR", "SYNTHETIC Equipment B"),
        _failure_detail(3, "9003", "SYNTHETIC tall merged failure mode", "SYNTHETIC Equipment C"),
    ]
    return _report(STRESS_STATION, _team(25), details, uoirs)


# --------------------------------------------------------------------------- #
# Adversarial report (built to break layout, see test_pdf_adversarial.py)
# --------------------------------------------------------------------------- #
ADVERSARIAL_STATION = "SYNTHETIC Station & <Unit 5>"
WIDE_FLAG_TEXT = "SYNTHETICWIDEFLAGTEXTWITHOUTANYBREAKS"
LONG_STRATEGY_CODE = "R-" + "SYNTHETICVERYLONGSTRATEGYCODE" * 2
FLAG_HEADERS = ("H", "S", "E", "O", "1", "2", "3", "H4", "H5", "S4")


def adversarial_report() -> Report:
    """Wide text in narrow flag columns, 30 notes, a UOIR without analysis or
    summary, a very long strategy label, 40 work centres, '&' and '<' in the
    station, 40-line CA/PA cells and 500 recommendation rows in one group."""
    rng = random.Random(8001)

    table_a, described_a = build_analysis("8001", [2, 1, 3, 1, 1, 2, 2], rng=rng)
    for i, row in enumerate(table_a.rows):
        for flag in FLAG_HEADERS:
            row.cells[COL[flag]] = WIDE_FLAG_TEXT if i % 2 == 0 else "SYNTHETIC wide words in a flag column"
        if i < 4:
            row.cells[COL["RecommendedStrategy"]] = LONG_STRATEGY_CODE
            described_a[i]["strategy"] = LONG_STRATEGY_CODE
    summary_a = build_summary(described_a)
    summary_a.work_centre_rows = [
        WorkCentreRow(work_centre=f"SYNTRADE{i:02d}", total=80 - 2 * i, executed=40 - i, pending=40 - i)
        for i in range(40)
    ]
    summary_a.not_counted = [NotCountedRow(source_row=100 + i, reason="New Task blank", strategy="OC",
                                           trade=f"SYNTRADE{i:02d}") for i in range(10)]
    summary_a.duplicate_rows = list(range(200, 205))
    notes = [Note(cell=f"B{20 + i}", text=f"SYNTHETIC note {i + 1:02d} " + "about the damper " * (i % 6))
             for i in range(30)]
    equipment_a = ["SYNTHETIC Damper & <Actuator>"]
    uoir_a = UoirSection(
        uoir_id="8001", title="SYNTHETIC flags & notes <stress>", equipment=equipment_a,
        sheet_name=table_a.sheet, notes=notes, analysis=table_a, summary=summary_a,
        recommendations=build_recommendations("8001", equipment_a, described_a, ["SYN/A1", "SYN/A2"]),
    )

    uoir_b = UoirSection(uoir_id="8002", title="SYNTHETIC UOIR without a linked worksheet",
                         equipment=[], analysis=None, summary=None, recommendations=[])

    table_c, described_c = build_analysis("8003", [1] * 500, rng=rng)
    equipment_c = ["SYNTHETIC Feed Pump"]
    uoir_c = UoirSection(
        uoir_id="8003", title="SYNTHETIC 500 recommendations in one group", equipment=equipment_c,
        sheet_name=table_c.sheet, analysis=table_c, summary=build_summary(described_c),
        recommendations=build_recommendations("8003", equipment_c, described_c, ["SYN/ONE-GROUP"]),
    )

    details = []
    for no, uoir in enumerate((uoir_a, uoir_b, uoir_c), start=1):
        detail = _failure_detail(no, uoir.uoir_id, uoir.title, "SYNTHETIC equipment & <tag>")
        detail.corrective_action = "\n".join(f"SYNTHETIC CA {uoir.uoir_id} line {k:02d}" for k in range(1, 41))
        detail.preventive_action = "\n".join(f"SYNTHETIC PA {uoir.uoir_id} line {k:02d}" for k in range(1, 41))
        details.append(detail)
    return _report(ADVERSARIAL_STATION, _team(9), details, [uoir_a, uoir_b, uoir_c])


def analysis_markers(report: Report) -> list[str]:
    markers = []
    for uoir in report.uoirs:
        for index in range(len(uoir.analysis.rows) if uoir.analysis else 0):
            markers.append(analysis_marker(uoir.uoir_id, index))
    return markers


def recommendation_markers(report: Report) -> list[str]:
    return [row.task.split(" ", 1)[0]
            for uoir in report.uoirs for group in uoir.recommendations for row in group.rows]


# --------------------------------------------------------------------------- #
# PDF inspection helpers (PyMuPDF, test-only dependency)
# --------------------------------------------------------------------------- #
A4_PORTRAIT_SIZE = (595.3, 841.9)
A3_LANDSCAPE_SIZE = (1190.6, 841.9)
SECTION_TITLES = {
    "Introduction": "intro",
    "Analysis: FMEA Analysis": "analysis",
    "Analysis: FMEA Summary": "summary",
    "Recommendation": "recommendation",
}


def page_kind(page) -> str:
    """"A4P" or "A3L" (fails loudly for any other size)."""
    size = (round(page.rect.width, 1), round(page.rect.height, 1))
    if all(abs(a - b) < 1 for a, b in zip(size, A4_PORTRAIT_SIZE)):
        return "A4P"
    if all(abs(a - b) < 1 for a, b in zip(size, A3_LANDSCAPE_SIZE)):
        return "A3L"
    raise AssertionError(f"unexpected page size {size}")


def page_lines(page) -> list[str]:
    return [line.strip() for line in page.get_text().splitlines() if line.strip()]


def compact(text: str) -> str:
    """Text with all whitespace removed (wrapped cell text joins back together)."""
    return "".join(text.split())


def page_sections(doc) -> list[str]:
    """Section of every page: "cover" for page 1, then the latest section title seen."""
    sections, current = [], "cover"
    for number, page in enumerate(doc):
        if number > 0:
            for line in page_lines(page):
                if line in SECTION_TITLES:
                    current = SECTION_TITLES[line]
                    break
        sections.append(current)
    return sections


def section_starts(doc) -> list[str]:
    """Section titles in the order they appear ("cover" for page 1)."""
    starts = []
    for number, page in enumerate(doc):
        titles = [SECTION_TITLES[line] for line in page_lines(page) if line in SECTION_TITLES]
        if number == 0:
            starts.append("cover")
        starts.extend(titles)
    return starts


def pages_per_uoir(doc, section: str) -> list[list]:
    """Pages of an "analysis" or "summary" section, one list per UOIR (a new list
    starts on each page that carries the section title)."""
    title = next(t for t, s in SECTION_TITLES.items() if s == section)
    groups: list[list] = []
    for page, current in zip(doc, page_sections(doc)):
        if current != section:
            continue
        if title in page_lines(page):
            groups.append([])
        groups[-1].append(page)
    return groups


def shown_on_pages(text: str, page_texts: list[str]) -> bool:
    """True when `text` (whitespace ignored) is on one page, or starts at the foot of
    one page and continues at the top of the next (a cell split across pages)."""
    wanted = compact(text).replace(CONTINUED, "")
    pages = [compact(t).replace(CONTINUED, "") for t in page_texts]
    if not wanted or any(wanted in page for page in pages):
        return True
    return any(wanted[:k] in first and wanted[k:] in second
               for first, second in zip(pages, pages[1:]) for k in range(1, len(wanted)))


CONTINUED = "(cont.)"


def words_outside_body(page, side_margin: float, top_margin: float, bottom_margin: float) -> list[tuple]:
    """Words that leave the page body (running header and footer excepted)."""
    width, height = page.rect.width, page.rect.height
    bottom = height - bottom_margin
    outside = []
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        if y1 < top_margin - 10 or y0 > bottom:     # running header / footer
            continue
        if x0 < side_margin - 1 or x1 > width - side_margin + 1 or y0 < top_margin - 1 or y1 > bottom + 1:
            outside.append((word, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)))
    return outside
