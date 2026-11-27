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
# A quantity inside the title ("3 PC 16 A avec terre") means a list item, not a heading.
_QUANTITY = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:A|V|W|mm|cm|m|m2|m²|kg|dB|Pa|%)(?![\w*])")
_NUMBERED = re.compile(
    r"^\s*(?:article|art\.?|chapitre|section)?\s*"
    r"(\d{1,2}(?:\.\d{1,3}){0,5})\.?\s*[-:)]?\s+"
    r"([A-Za-zÀ-ÿ\"'(].{1,140})$",
    re.IGNORECASE,
)
# An item heading that runs on into its size: "3.4.2.1. Châssis repère A de 1800 x 1350 mm
# environ…". The title ends where the size starts; the rest is the item's text.
_SIZE_CLAUSE = re.compile(r"\s+(?:de|d')\s*(?=[(\d])")
# Labels written in capitals inside an article: not headings.
_LABELS = re.compile(
    r"^(?:localisations?|nota(?:\s+bene)?|n\.?\s?b|remarques?|observations?|important|"
    r"attention|rappels?)\W*$",
    re.IGNORECASE,
)
# Title-block and address lines that survive page-furniture removal: "12 Rue des
# Lilas - 12345 BOURGVILLE", "54321 VALMONT", "10000001-A1-01-PLN_V1 BAT A 01/01/2026",
# "800x1200 // TEINTE". They are no headings, and must not stay open in the outline.
_STREET = re.compile(
    r"^(?:rue|avenue|av\.|boulevard|bd|chemin|all[ée]e|impasse|place|route|quai|square|"
    r"cours|lieu-dit|z\.?[ai]\.?|zac|b\.?p\.?|c\.?s\.?)\b",
    re.IGNORECASE,
)
_POSTCODE = re.compile(r"(?<!EN )(?<!ISO )(?<!NF )\b\d{2}\s?\d{3}\s+[A-ZÀ-Ÿ][A-ZÀ-Ÿ'-]{2,}")
_REFERENCE_CODE = re.compile(r"\d{6,}|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{2,4}\s?[x×]\s?\d{2,4}\b")
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
    rest: str = ""  # text on the heading's line after the title, when the line runs on

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
    if not text or _LEADERS.search(text):
        return None  # empty or a table-of-contents entry
    if len(text) > 160:
        return _run_on_item(text, style_level)  # a paragraph, unless an item heading runs on

    if _POSTCODE.search(text):
        return None  # an address on a title block
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
        if _STREET.match(title):
            return None  # "12 Rue des Lilas", "3 Avenue des Tilleuls"
        first = int(number.split(".")[0])
        sentence_like = title.endswith((".", ";", ",")) and len(title) > 80
        # Real titles start with a capital: "5 étapes de traitement..." is a sentence.
        if first <= 40 and not sentence_like and not title[0].islower():
            if not _QUANTITY.search(title):
                level = number.count(".") + 1
                return Heading(level=level, number=number, title=title.rstrip(" :."))
            if (run_on := _run_on_item(text, style_level)) is not None:
                return run_on

    if m := _LETTERED.match(text):
        return Heading(level=1, number=m.group(1), title=m.group(2).rstrip(" :."))

    if style_level is not None:
        return Heading(level=style_level, number=None, title=text.rstrip(" :."))

    if (
        _is_mostly_upper(text)
        and len(text) <= 90
        and text[:1] not in '-•*"«“'  # a list line of capitals: '- "ACCUEIL"'
        and not text.endswith((".", ";", ","))
        and not _LABELS.match(text)
        and not _REFERENCE_CODE.search(text)  # a plan reference, a date or a size
    ):
        return Heading(level=1, number=None, title=text.rstrip(" :."))

    return None


_DEEP_NUMBERED = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,3}){2,5})\.?\s*[-:)]?\s+([A-ZÀ-Ÿ].*)$")


def _run_on_item(text: str, style_level: int | None) -> Heading | None:
    """A deep item heading that runs on into its size, however long the line.

    "3.4.2.1. Châssis repère A de 1800 x 1350 mm environ, comprenant …" is the
    heading "3.4.2.1 Châssis repère A" followed by the item's text. Only deep
    articles qualify: "3 PC 16 A avec terre" stays a list item.
    """
    m = _DEEP_NUMBERED.match(text)
    if m is None or style_level is not None:
        return None
    number, title = m.group(1), m.group(2)
    cut = _SIZE_CLAUSE.search(title)
    if cut is None or int(number.split(".")[0]) > 40:
        return None
    head = title[: cut.start()]
    if len(head.split()) < 2 or len(head) > 140:
        return None
    return Heading(
        level=number.count(".") + 1, number=number, title=head, rest=title[cut.start() :].strip()
    )
