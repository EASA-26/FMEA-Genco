"""Bundled fonts.

Liberation Sans (SIL OFL) has the same letter widths as Arial and ships with the
app, so the PDF lays out identically on Windows and on Linux (Databricks).
"""
from __future__ import annotations

import threading

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from backend.settings import ASSETS_DIR

FONT_DIR = ASSETS_DIR / "fonts"

SANS = "Sans"
SANS_BOLD = "Sans-Bold"
SANS_ITALIC = "Sans-Italic"
SANS_BOLD_ITALIC = "Sans-BoldItalic"

_FONT_FILES = {
    SANS: "LiberationSans-Regular.ttf",
    SANS_BOLD: "LiberationSans-Bold.ttf",
    SANS_ITALIC: "LiberationSans-Italic.ttf",
    SANS_BOLD_ITALIC: "LiberationSans-BoldItalic.ttf",
}

_lock = threading.Lock()
_registered = False


def register_fonts() -> None:
    """Register the Sans family with ReportLab once per process (idempotent)."""
    global _registered
    if _registered:
        return
    with _lock:
        if _registered:
            return
        known = set(pdfmetrics.getRegisteredFontNames())
        for name, filename in _FONT_FILES.items():
            if name not in known:
                pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))
        # Lets Paragraph markup such as <b> and <i> pick the right face.
        pdfmetrics.registerFontFamily(
            SANS, normal=SANS, bold=SANS_BOLD, italic=SANS_ITALIC, boldItalic=SANS_BOLD_ITALIC
        )
        _registered = True


def text_width(text: str, font_name: str, font_size: float) -> float:
    register_fonts()
    return pdfmetrics.stringWidth(text, font_name, font_size)
