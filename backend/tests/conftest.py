"""Shared test fixtures: SYNTHETIC workbooks built by tools/make_synthetic_workbook.py.

Every workbook used by the tests is generated in memory and holds only invented
values, so no engineer workbook is needed (or kept) in the repository:

* ``sample_workbook_bytes`` - the sample-like workbook: the layout and quirks
  of a full engineer workbook with invented content (no issues at all);
* ``edge_workbook_bytes``   - the edge-case workbook (blocking errors);
* ``clean_workbook_bytes``  - a small valid workbook, also available through
  ``clean_workbook_with`` with one change applied.

A real workbook can still be checked on your own machine with the opt-in
smoke test in test_local_workbook_smoke.py (set FMEA_SAMPLE_WORKBOOK).
"""
from __future__ import annotations

import importlib.util
import io
from typing import Callable

import pytest
from openpyxl import Workbook

from backend.settings import PROJECT_ROOT


def _load_synthetic_module():
    """Import tools/make_synthetic_workbook.py by path (tools/ is not a package)."""
    path = PROJECT_ROOT / "tools" / "make_synthetic_workbook.py"
    spec = importlib.util.spec_from_file_location("synthetic_workbook_tool", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def synthetic_tool():
    """The SYNTHETIC workbook generator module."""
    return _load_synthetic_module()


@pytest.fixture(scope="session")
def sample_workbook_bytes(synthetic_tool) -> bytes:
    """The SYNTHETIC sample-like workbook (full engineer layout, invented values, no issues)."""
    return synthetic_tool.build_sample_like_workbook()


@pytest.fixture(scope="session")
def edge_workbook_bytes(synthetic_tool) -> bytes:
    return synthetic_tool.build_edge_case_workbook()


@pytest.fixture(scope="session")
def clean_workbook_bytes(synthetic_tool) -> bytes:
    return synthetic_tool.build_clean_workbook()


@pytest.fixture
def clean_workbook_with(synthetic_tool) -> Callable[[Callable[[Workbook], None]], bytes]:
    """Build the clean SYNTHETIC workbook, apply `change(workbook)`, and return the bytes."""

    def build(change: Callable[[Workbook], None]) -> bytes:
        wb = synthetic_tool.make_clean_workbook()
        change(wb)
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    return build
