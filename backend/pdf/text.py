"""Turning workbook text into safe ReportLab Paragraph markup."""
from __future__ import annotations

import re
from functools import lru_cache

from reportlab.pdfbase import pdfmetrics

from backend.pdf.fonts import SANS, register_fonts, text_width

# Break opportunities inside a long token: after these separators ...
_AFTER_SEPARATOR = re.compile(r"(?<=[/\\\-_.,;:+|])(?=.)")
# ... and, if a piece is still too wide, between lower->upper case and letters<->digits.
_CASE_OR_DIGIT_CHANGE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])")

# Standard PDF font used for tick marks and similar symbols that Liberation Sans
# lacks (e.g. "✓" in a flag column), so they print instead of an empty box.
SYMBOL_FONT = "ZapfDingbats"


@lru_cache(maxsize=1)
def _sans_code_points() -> frozenset[int]:
    register_fonts()
    return frozenset(pdfmetrics.getFont(SANS).face.charToGlyph)


@lru_cache(maxsize=512)
def _symbol_font_has(char: str) -> bool:
    try:
        return len(char.encode("zapfdingbats")) == 1
    except (UnicodeError, LookupError):
        return False


def _needs_symbol_font(char: str) -> bool:
    return ord(char) > 127 and ord(char) not in _sans_code_points() and _symbol_font_has(char)


def _with_symbol_fallback(markup: str) -> str:
    """Wrap runs of symbols missing from Liberation Sans in the ZapfDingbats font."""
    if markup.isascii() or not any(_needs_symbol_font(ch) for ch in markup):
        return markup
    out, run = [], []
    for ch in markup:
        if _needs_symbol_font(ch):
            run.append(ch)
            continue
        if run:
            out.append(f'<font name="{SYMBOL_FONT}">{"".join(run)}</font>')
            run = []
        out.append(ch)
    if run:
        out.append(f'<font name="{SYMBOL_FONT}">{"".join(run)}</font>')
    return "".join(out)


def escape(text: str) -> str:
    """Escape the characters that Paragraph markup would otherwise interpret
    (and route symbols Liberation Sans lacks to the symbol font)."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _with_symbol_fallback(escaped)


def plain_markup(text: str) -> str:
    """Escaped text with workbook line breaks kept."""
    return "<br/>".join(escape(line) for line in (text or "").split("\n"))


def cell_markup(text: str, font_name: str, font_size: float, max_width: float) -> str:
    """Markup for a table cell: escaped, line breaks kept, and break points added
    inside any word wider than the cell so long codes wrap instead of overflowing.

    Words that still cannot be broken at a natural point are left to ReportLab,
    which splits over-long words by character rather than letting them overflow.
    """
    lines = []
    for line in (text or "").split("\n"):
        if max_width <= 0 or text_width(line, font_name, font_size) <= max_width:
            lines.append(escape(line))   # the whole line fits, so no word can be too wide
            continue
        words = []
        for word in line.split(" "):
            if max_width > 0 and word and text_width(word, font_name, font_size) > max_width:
                words.append(_break_long_word(word, font_name, font_size, max_width))
            else:
                words.append(escape(word))
        lines.append(" ".join(words))
    return "<br/>".join(lines)


def _unbreakable_pieces(text: str):
    """The parts of `text` that `cell_markup` can never break inside."""
    for line in (text or "").split("\n"):
        for word in line.split(" "):
            for piece in _AFTER_SEPARATOR.split(word):
                yield from _CASE_OR_DIGIT_CHANGE.split(piece)


def font_size_to_fit_words(text: str, font_name: str, font_size: float, max_width: float,
                           min_size: float) -> float:
    """Type size for a cell whose longest unbreakable word is slightly too wide.

    Shrinking that one cell (down to `min_size`) keeps a word such as "Frequency"
    whole in a narrow column; a word that would need an even smaller size keeps
    `font_size` and is broken between characters instead."""
    if max_width <= 0 or not text:
        return font_size
    lines = [line for line in text.split("\n") if text_width(line, font_name, font_size) > max_width]
    if not lines:   # every line fits, so no word can be too wide
        return font_size
    widest = max((text_width(piece, font_name, font_size) for piece in _unbreakable_pieces("\n".join(lines))),
                 default=0.0)
    if widest <= max_width:
        return font_size
    size = int(font_size * max_width / widest * 4) / 4   # quarter-point steps, rounded down
    return size if size >= min_size else font_size


def _break_long_word(word: str, font_name: str, font_size: float, max_width: float) -> str:
    pieces = []
    for piece in _AFTER_SEPARATOR.split(word):
        if text_width(piece, font_name, font_size) > max_width:
            pieces.extend(_CASE_OR_DIGIT_CHANGE.split(piece))
        else:
            pieces.append(piece)

    # Greedily pack pieces into segments that fit the cell width.
    segments: list[str] = []
    current = ""
    for piece in pieces:
        candidate = current + piece
        if current and text_width(candidate, font_name, font_size) > max_width:
            segments.append(current)
            current = piece
        else:
            current = candidate
    if current:
        segments.append(current)
    return "<br/>".join(escape(segment) for segment in segments)


def truncate_to_width(text: str, font_name: str, font_size: float, max_width: float) -> str:
    """Shorten single-line text with an ellipsis so it fits `max_width`."""
    if text_width(text, font_name, font_size) <= max_width:
        return text
    ellipsis = "…"
    low, high = 0, len(text)
    while low < high:  # longest prefix that fits together with the ellipsis
        mid = (low + high + 1) // 2
        if text_width(text[:mid].rstrip() + ellipsis, font_name, font_size) <= max_width:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + ellipsis
