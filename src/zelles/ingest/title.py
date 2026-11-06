"""Find the project name on a CCTP cover page.

Files are often named "CCTP.pdf" or "02_CCTP_LOT02.pdf", so the file name alone
does not tell an estimator which tender is open. The cover page states the
operation ("Construction de 45 logements collectifs", "Réhabilitation du groupe
scolaire ...") next to boilerplate (document type, lot, phase, parties, dates).
This keeps the line that names the works and drops the boilerplate. It returns
None rather than guess: the UI then shows the file name.
"""

from __future__ import annotations

import re

from zelles.domain.documents import ParsedDocument

_LABEL = re.compile(r"^\s*(?:op[ée]ration|projet|objet(?:\s+du\s+march[ée])?|affaire)\s*:\s*", re.I)
_WORKS = re.compile(
    r"\b(?:construction|r[ée]habilitation|r[ée]novation|restructuration|extension|"
    r"cr[ée]ation|r[ée]alisation|r[ée]am[ée]nagement|am[ée]nagement|transformation|"
    r"reconstruction|d[ée]molition|surélévation|mise\s+aux\s+normes|"
    r"logements?|r[ée]sidence|groupe\s+scolaire|[ée]cole|coll[èe]ge|lyc[ée]e|cr[èe]che|"
    r"gymnase|ehpad|m[ée]diath[èe]que|bureaux|[ée]quipement|zac|[îi]lot|b[âa]timent|"
    r"maison|foyer|internat|h[ôo]pital|centre)\b",
    re.I,
)
_BOILERPLATE = re.compile(
    r"cahier\s+des\s+clauses|c\.?\s?c\.?\s?t\.?\s?p|clauses\s+techniques|"
    r"^\s*lot\b|\blot\s*n?\s*[°ºo]?\s*\d|"
    r"ma[îi]tr(?:e|ise)\s+d['’]\s*(?:ouvrage|œuvre|oeuvre)|architecte|bureau\s+d['’]\s*[ée]tudes|"
    r"\b(?:b\.?e\.?t|opc|dce|apd|aps|pro|exe)\b|dossier\s+de\s+consultation|"
    r"\bphase\b|\bindice\b|\bdate\b|\bpage\b|\bt[ée]l\b|@|www\.|siret|"
    r"\bpi[èe]ce\s+n|\bmarch[ée]\s+public",
    re.I,
)
_POSTCODE_ONLY = re.compile(r"^\s*\d{5}\s+[\w\s'’-]+$")
_MAX_CHARS = 140


def _shorten(text: str) -> str:
    text = " ".join(text.split()).strip(" -–:;,.")
    if len(text) <= _MAX_CHARS:
        return text
    return text[:_MAX_CHARS].rsplit(" ", 1)[0] + "…"


def detect_title(document: ParsedDocument) -> str | None:
    """Return the project name from the cover page, or None when unsure."""
    first_page = [b for b in document.blocks if b.page == 1]
    blocks = first_page or document.blocks[:15]
    best: tuple[int, str] | None = None
    for block in blocks:
        text = " ".join(block.text.split())
        labelled = _LABEL.match(text)
        if labelled:
            value = text[labelled.end() :]
            if len(value) >= 8 and not _BOILERPLATE.search(value):
                return _shorten(value)
            continue
        if not 12 <= len(text) <= 260 or _BOILERPLATE.search(text) or _POSTCODE_ONLY.match(text):
            continue
        score = len(_WORKS.findall(text))
        if score and (best is None or score > best[0]):
            best = (score, text)
    return _shorten(best[1]) if best else None
