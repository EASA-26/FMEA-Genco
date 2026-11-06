"""Opt-in smoke test with a workbook on your own machine.

Skipped unless the environment variable FMEA_SAMPLE_WORKBOOK points at an
existing .xlsx/.xlsm file. The file is read in place (never copied or saved)
and only value-free invariants are checked, so no workbook content appears in
the repository::

    $env:FMEA_SAMPLE_WORKBOOK = "D:\\FMEA\\workbook.xlsx"      # PowerShell
    python -m pytest -q -p no:cacheprovider backend/tests/test_local_workbook_smoke.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.report.builder import build_report

ENV_VAR = "FMEA_SAMPLE_WORKBOOK"


def _local_workbook() -> Path | None:
    value = os.environ.get(ENV_VAR, "").strip()
    if not value:
        return None
    path = Path(value)
    return path if path.is_file() else None


pytestmark = pytest.mark.skipif(
    _local_workbook() is None, reason=f"set {ENV_VAR} to a workbook file on this machine to run this check",
)


@pytest.fixture(scope="module")
def local_report():
    path = _local_workbook()
    assert path is not None
    return build_report(path.read_bytes(), path.name)


def test_local_workbook_parses_into_a_report(local_report):
    assert local_report.station.strip(), "the report has a station"
    assert len(local_report.uoir_ids) >= 1, "the report has at least one UOIR"
    assert local_report.pdf_filename.startswith("FMEA_Report_") and local_report.pdf_filename.endswith(".pdf")
    errors = [issue for issue in local_report.issues if issue.severity == "error"]
    assert local_report.can_export is (not errors)


def test_local_workbook_renders_a_pdf(local_report):
    from backend.pdf.render import render_pdf      # imported here so a skipped module never loads the PDF code

    pdf = render_pdf(local_report)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
