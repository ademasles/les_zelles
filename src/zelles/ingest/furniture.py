"""Remove page furniture: running headers, footers, page numbers and the table of contents.

Word CCTPs repeat the architect's name, the project and "Phase PRO - Indice B"
on every page, and start with a table of contents. Left in, these lines are
read as section titles and give every requirement the wrong scope.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

from zelles.domain.documents import BBox
from zelles.ingest.cleaning import clean_text

Line = tuple[str, BBox | None]

BAND = 0.15  # top and bottom share of the page where headers and footers live
_DIGITS = re.compile(r"\d+")
_PAGE_NUMBER = re.compile(r"^(?:page\s*)?#(?:\s*(?:/|sur|de)\s*#)?$|^-\s*#\s*-$", re.IGNORECASE)
_TOC_LINE = re.compile(
    r"^\s*(?:\d{1,2}(?:\.\d{1,3}){0,4}\.?\s+|[A-H][.)]\s+|lot\s+\w+\s*[-:]?\s*)"
    r"[^\n]{2,140}?(?:\s*\.{3,}\s*|\s*…+\s*|\s+)(\d{1,3})\s*$",
    re.IGNORECASE,
)
_TOC_TITLE = re.compile(r"\b(?:sommaire|table\s+des\s+mati[èe]res)\b", re.IGNORECASE)


def _key(text: str) -> str:
    return " ".join(_DIGITS.sub("#", clean_text(text).lower()).split())


def _in_band(box: BBox | None, height: float | None) -> bool:
    if box is None or not height:
        return False
    return box.y1 <= BAND * height or box.y0 >= (1 - BAND) * height


def is_toc_line(text: str) -> bool:
    """A line that ends with a page number, with dot leaders or after an outline title."""
    text = clean_text(text)
    if re.search(r"\.{3,}|…", text) and re.search(r"\d{1,3}\s*$", text):
        return True
    m = _TOC_LINE.match(text)
    if not m:
        return False
    body = text[: m.start(1)].strip(" .…")
    letters = [c for c in body if c.isalpha()]
    # "1 GENERALITES 3": a numbered upper-case title followed by its page number.
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) >= 0.8


def strip_furniture(pages: list[tuple[list[Line], float | None]]) -> list[list[Line]]:
    """Return each page's lines without repeated headers/footers, page numbers and TOC lines."""
    if not pages:
        return []
    seen: dict[str, set[int]] = defaultdict(set)
    for index, (lines, height) in enumerate(pages):
        for text, box in lines:
            if _in_band(box, height):
                seen[_key(text)].add(index)
    threshold = max(2, math.ceil(0.5 * len(pages)))
    repeated = {key for key, where in seen.items() if len(where) >= threshold}
    if len(pages) < 3:
        repeated = set()

    out: list[list[Line]] = []
    for lines, height in pages:
        toc_like = [is_toc_line(t) for t, _ in lines]
        toc_page = sum(toc_like) >= 4 or (
            sum(toc_like) >= 2 and any(_TOC_TITLE.search(t) for t, _ in lines)
        )
        kept: list[Line] = []
        for (text, box), toc in zip(lines, toc_like, strict=True):
            key = _key(text)
            if _in_band(box, height) and (key in repeated or _PAGE_NUMBER.match(key)):
                continue
            if toc_page and (toc or _TOC_TITLE.fullmatch(clean_text(text).strip(" :"))):
                continue
            kept.append((text, box))
        out.append(kept)
    return out
