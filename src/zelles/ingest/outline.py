"""Detect the CCTP outline: lots and numbered articles.

French CCTPs are organised by lot ("LOT 05 - MENUISERIES EXTÉRIEURES") and by
numbered articles ("3.2.1 Menuiseries PVC"). Following that outline is what lets
an answer say *where* a requirement applies, which is what an estimator needs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LOT = re.compile(
    r"^\s*lot\s*(?:n\s*[°ºo]\.?\s*)?(\d{1,3}[a-z]?|unique)\b\s*[-:.)]*\s*(.{0,120})$",
    re.IGNORECASE,
)
_LEADERS = re.compile(r"\.{3,}|…")
_NUMBERED = re.compile(
    r"^\s*(?:article|art\.?|chapitre|section)?\s*"
    r"(\d{1,2}(?:\.\d{1,3}){0,5})\.?\s*[-:)]?\s+"
    r"([A-Za-zÀ-ÿ\"'(].{1,140})$",
    re.IGNORECASE,
)
_LETTERED = re.compile(r"^\s*([A-H]|[IVX]{1,4})[.)]\s+([A-ZÀ-Ÿ].{2,100})$")
_UNIT_AFTER_NUMBER = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*(?:mm|cm|m|dB|W|%|kg|°|x|×)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class Heading:
    level: int
    number: str | None
    title: str
    is_lot: bool = False

    @property
    def label(self) -> str:
        if self.is_lot:
            return f"Lot {self.number} - {self.title}".strip(" -") if self.number else self.title
        return f"{self.number} {self.title}".strip() if self.number else self.title


def _is_mostly_upper(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 6:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= 0.8


def detect_heading(line: str, *, style_level: int | None = None) -> Heading | None:
    """Return a Heading if the line looks like a lot or article title.

    ``style_level`` is a hint from the source format (DOCX heading styles).
    """
    text = line.strip()
    if not text or len(text) > 160 or _LEADERS.search(text):
        return None  # empty, a paragraph, or a table-of-contents entry

    if m := _LOT.match(text):
        number = m.group(1).upper()
        title = m.group(2).strip(" -:.")
        if number == "UNIQUE":
            return Heading(level=0, number=None, title=f"Lot unique {title}".strip(), is_lot=True)
        return Heading(level=0, number=number, title=title, is_lot=True)

    if _UNIT_AFTER_NUMBER.match(text):
        return None  # "1,3 W/m².K" or "20 mm" is a value, not a heading

    if m := _NUMBERED.match(text):
        number, title = m.group(1), m.group(2).strip()
        first = int(number.split(".")[0])
        sentence_like = title.endswith((".", ";", ",")) and len(title) > 80
        # Real titles start with a capital: "5 étapes de traitement..." is a sentence.
        if first <= 40 and not sentence_like and not title[0].islower():
            return Heading(level=number.count(".") + 1, number=number, title=title.rstrip(" :."))

    if m := _LETTERED.match(text):
        return Heading(level=1, number=m.group(1), title=m.group(2).rstrip(" :."))

    if style_level is not None:
        return Heading(level=style_level, number=None, title=text.rstrip(" :."))

    if _is_mostly_upper(text) and len(text) <= 90 and not text.endswith((".", ";", ",")):
        return Heading(level=1, number=None, title=text.rstrip(" :."))

    return None
