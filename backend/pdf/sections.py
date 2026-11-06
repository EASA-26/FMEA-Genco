"""The report story: Introduction, one Analysis + Summary page pair per analysis tab, Recommendation.

One analysis tab can cover several UOIRs; its pages are headed with all of them
("UOIR ID : 901, 902"). Failure Details in the Introduction keeps one row per
UOIR sheet row.
"""
from __future__ import annotations

from typing import Sequence

from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    Paragraph,
    Spacer,
)
from reportlab.platypus.flowables import HRFlowable

from backend.pdf import styles
from backend.pdf.charts import StatCards, StrategyPie, strategy_pie
from backend.pdf.document import A3, A4
from backend.pdf.flowtable import FlowTable
from backend.pdf.tables import (
    analysis_table,
    failure_details_table,
    key_value_table,
    recommendation_table,
    strategy_table,
    team_table,
    work_centre_table,
)
from backend.pdf.text import plain_markup
from backend.report.models import AnalysisSection, NotCountedRow, Report

# A heading is kept with its table's header and this many first rows.
ROWS_KEPT_WITH_HEADING = 2
# Never ask for more than this share of a page, so an unusually tall first row
# cannot push a heading onto a page of its own.
MAX_KEEP_FRACTION = 0.8


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #
def section_title(text: str) -> list[Flowable]:
    return [
        Paragraph(plain_markup(text), styles.SECTION_TITLE),
        HRFlowable(width="100%", thickness=1.2, color=styles.PRIMARY, spaceBefore=5, spaceAfter=10),
    ]


def _height(flowables: Sequence[Flowable], width: float) -> float:
    total = 0.0
    for f in flowables:
        total += f.wrap(width, styles.FRAME_HEIGHT)[1] + f.getSpaceBefore() + f.getSpaceAfter()
    return total


def keep_with_table(headings: Sequence[Flowable], table: FlowTable, width: float) -> list[Flowable]:
    """Headings followed by a table, never leaving the headings alone at the foot of a page."""
    need = _height(headings, width) + table.leading_height(ROWS_KEPT_WITH_HEADING)
    need = min(need, MAX_KEEP_FRACTION * styles.FRAME_HEIGHT)
    return [CondPageBreak(need), *headings, table]


def keep_with_note(heading: Flowable, note: Flowable, width: float) -> list[Flowable]:
    return [CondPageBreak(_height([heading, note], width)), heading, note]


def empty_note(text: str) -> Paragraph:
    return Paragraph(plain_markup(text), styles.EMPTY_NOTE)


def uoir_ids_text(section: AnalysisSection) -> str:
    """Every UOIR ID the tab covers, as printed: "901, 902"."""
    return ", ".join(section.uoir_ids)


def heading_pairs(section: AnalysisSection) -> list[tuple[str, str]]:
    """The "UOIR ID" and "Title" rows at the top of a section's pages."""
    return [("UOIR ID", uoir_ids_text(section)), ("Title", section.title)]


# --------------------------------------------------------------------------- #
# Introduction (A4)
# --------------------------------------------------------------------------- #
def introduction(report: Report) -> list[Flowable]:
    width = styles.A4_FRAME_WIDTH
    story = section_title("Introduction")

    heading = Paragraph("Failure Details", styles.HEADING_2)
    if report.failure_details:
        story += keep_with_table([heading], failure_details_table(report.failure_details, width), width)
    else:
        story += keep_with_note(heading, empty_note("No failure details were found in the workbook."), width)

    heading = Paragraph("Team Members", styles.HEADING_2)
    if report.team:
        story += keep_with_table([heading], team_table(report.team, width), width)
    else:
        story += keep_with_note(heading, empty_note("No team members were found in the workbook."), width)
    return story


# --------------------------------------------------------------------------- #
# FMEA Analysis (A3 landscape)
# --------------------------------------------------------------------------- #
def analysis_page(section: AnalysisSection) -> list[Flowable]:
    width = styles.A3_FRAME_WIDTH
    story = section_title("Analysis: FMEA Analysis")
    pairs = heading_pairs(section) + [("Note", note.text) for note in section.notes]
    story += [key_value_table(pairs, width), Spacer(1, 10)]

    if section.analysis is None:
        story.append(empty_note("No analysis table was read from this tab."))
    elif not section.analysis.columns:
        story.append(empty_note("The analysis worksheet has no table columns."))
    else:
        story.append(analysis_table(section.analysis, width))
        if not section.analysis.rows:
            story.append(empty_note("The analysis worksheet has no data rows."))
    return story


# --------------------------------------------------------------------------- #
# FMEA Summary (A4 portrait)
# --------------------------------------------------------------------------- #
def not_counted_line(row: NotCountedRow) -> str:
    details = ", ".join(part for part in (row.strategy, row.trade) if part)
    where = f"row {row.source_row}" + (f" ({details})" if details else "")
    reason = row.reason.rstrip(".")
    return f"Not counted: {where} — {reason}."


def duplicate_line(source_row: int) -> str:
    return f"Row {source_row} is identical to an earlier row and was counted once."


def summary_page(section: AnalysisSection) -> list[Flowable]:
    width = styles.A4_FRAME_WIDTH
    story = section_title("Analysis: FMEA Summary")
    story += [key_value_table(heading_pairs(section), width), Spacer(1, 12)]

    summary = section.summary
    if summary is None:
        story.append(empty_note("No summary is available for this tab."))
        return story

    story.append(StatCards([
        ("Failure Mode", summary.failure_mode_count),
        ("Maintenance Task", summary.maintenance_task_count),
        ("Task Executed", summary.task_executed_count),
    ], width))

    headings = [Paragraph("Existing vs Revised", styles.HEADING_2),
                Paragraph("Recommended Strategy", styles.HEADING_3)]
    pie = strategy_pie(summary.pie, summary.pie_total, width)
    pie_block = [*headings, pie, Spacer(1, 10)]
    if not isinstance(pie, StrategyPie) or _height(pie_block, width) <= MAX_KEEP_FRACTION * styles.FRAME_HEIGHT:
        story.append(KeepTogether(pie_block))
    else:
        # A legend with dozens of strategies: keep the headings with the pie and
        # the start of the legend, and let the rest of the legend flow on.
        story += [CondPageBreak(_height(headings, width) + pie.stacked_leading_height(width)), *pie_block]
    if summary.strategy_rows:
        story.append(strategy_table(summary.strategy_rows, width))

    heading = Paragraph("Work-Centre Execution", styles.HEADING_2)
    if summary.work_centre_rows:
        story += keep_with_table([heading], work_centre_table(summary.work_centre_rows, width), width)
    else:
        story += keep_with_note(heading, empty_note("No rows with New Task set to Yes or No."), width)

    lines = [not_counted_line(r) for r in summary.not_counted]
    lines += [duplicate_line(r) for r in summary.duplicate_rows]
    if lines:
        story.append(Spacer(1, 6))
        story += [Paragraph(plain_markup(line), styles.NOTE) for line in lines]
    return story


# --------------------------------------------------------------------------- #
# Recommendation (A4 portrait, continuous)
# --------------------------------------------------------------------------- #
def recommendation_section(report: Report) -> list[Flowable]:
    width = styles.A4_FRAME_WIDTH
    story = section_title("Recommendation")
    if not report.analyses:
        story.append(empty_note("No analysis tabs were found in the workbook."))
    for section in report.analyses:
        heading = Paragraph(plain_markup(f"UOIR ID {uoir_ids_text(section)}: {section.title}"), styles.HEADING_2)
        if not section.recommendations:
            story += keep_with_note(heading, empty_note("No recommendations for this tab."), width)
            continue
        for index, group in enumerate(section.recommendations):
            sub_heading = Paragraph(plain_markup(group.heading or "KKS not specified"), styles.HEADING_3)
            headings = [heading, sub_heading] if index == 0 else [sub_heading]
            story += keep_with_table(headings, recommendation_table(group, width), width)
    return story


# --------------------------------------------------------------------------- #
# Whole document
# --------------------------------------------------------------------------- #
def build_story(report: Report) -> list[Flowable]:
    # Page 1 is the cover, drawn entirely by the cover page template.
    story: list[Flowable] = [NextPageTemplate(A4), PageBreak()]
    story += introduction(report)
    for section in report.analyses:
        story += [NextPageTemplate(A3), PageBreak()]
        story += analysis_page(section)
        story += [NextPageTemplate(A4), PageBreak()]
        story += summary_page(section)
    story += [NextPageTemplate(A4), PageBreak()]
    story += recommendation_section(report)
    return story
