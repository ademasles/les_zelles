"""Find the project name on a CCTP cover page.

Files are often named "CCTP.pdf" or "02_CCTP_LOT02.pdf", so the file name alone
does not tell an estimator which tender is open. Covers state the operation
next to boilerplate (document type, lot, phase, parties, address, dates), and
the operation itself is often set in capitals over two or three lines:

    MAÎTRE D'OUVRAGE                     <- role label, the next lines are a party
    OFFICE PUBLIC DE L'HABITAT
    CONSTRUCTION DE 32 LOGEMENTS         <- one title over two lines
    COLLECTIFS ET D'UN PARKING
    12 rue des Lilas 91000 Exempleville  <- address, not part of the title
    CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES

The detector cuts the page-1 lines at addresses and role names, joins
consecutive title lines into runs, and keeps a labelled operation
("Opération :", "Description du projet") first, then the run naming the works,
then the first run in capitals. It returns None rather than guess: the UI then
shows the file name.
"""

from __future__ import annotations

import re

from zelles.domain.documents import ParsedDocument

_LABEL = re.compile(
    r"^\s*(?:op[ée]ration|projet|description\s+du\s+projet|objet(?:\s+du\s+march[ée])?|"
    r"affaire|d[ée]signation)\s*(?::|$)\s*",
    re.I,
)
_ROLE = re.compile(
    r"ma[îi]tr(?:e|ise)\s+d['’]\s*(?:ouvrage|œuvre|oeuvre)|\bmoa\b|\bmoe\b|architecte|"
    r"bureau\s+(?:d['’]\s*[ée]tudes|de\s+contr[ôo]le)|\bb\.?e\.?t\.?\b|[ée]conomiste|"
    r"mandataire|assistan(?:t|ce)\s+[àa]\s+ma[îi]trise|coordonn?ateur|\bopc\b|\bsps\b",
    re.I,
)
_BOILERPLATE = re.compile(
    r"cahier\s+des\s+clauses|c\.?\s?c\.?\s?t\.?\s?p|clauses\s+techniques|"
    r"^\s*lot\b|\blot\s*n?\s*[°ºo]?\s*\d|dossier\s+(?:de\s+consultation|dce|pro)|"
    r"\b(?:dce|apd|aps|exe)\b|^\s*pro\s*$|\bphase\b|\bindice\b|\bdate\b|\bpage\b|"
    r"\bt[ée]l\b|@|www\.|siret|\bpi[èe]ce\s+n|\bmarch[ée]s?\s+public|consultation|"
    r"proc[ée]dure|r[ée]f[ée]rence|\bversion\b|\d{1,2}/\d{1,2}/\d{2,4}",
    re.I,
)
_ADDRESS = re.compile(
    r"\b\d{1,4}\s*(?:bis|ter)?\s*,?\s*(?:rue|avenue|av\.|boulevard|bd|chemin|place|all[ée]e|"
    r"impasse|quai|route|cours|square|voie|rond[- ]point|esplanade|parvis)\b|\b\d{5}\b",
    re.I,
)
_WORKS = re.compile(
    r"\b(?:construction|r[ée]habilitation|r[ée]novation|restructuration|extension|"
    r"cr[ée]ation|r[ée]alisation|r[ée]am[ée]nagement|am[ée]nagement|transformation|"
    r"reconstruction|d[ée]molition|sur[ée]l[ée]vation|remplacement|r[ée]fection|"
    r"mise\s+aux\s+normes|logements?|r[ée]sidence|groupe\s+scolaire|[ée]cole|coll[èe]ge|"
    r"lyc[ée]e|cr[èe]che|gymnase|ehpad|m[ée]diath[èe]que|bureaux|[ée]quipement|zac|"
    r"[îi]lot|b[âa]timent|maison|foyer|internat|h[ôo]pital)\b",
    re.I,
)
_CONTINUES = re.compile(
    r"(?:\b(?:de|des|du|d['’]|et|à|a|au|aux|en|sur|pour|la|le|les)|[-–,&])$", re.I
)
_TAIL = re.compile(  # where a title line stops: a lot, or the next label
    r"[-–(,]?\s*\blot\s*(?:n\s*[°ºo]\.?\s*)?\d|"
    r"\badresse\s+du\s+(?:projet|chantier|site)\b|"
    r"\b(?:adresse|lieu(?:\s+d['’]ex[ée]cution)?|localisation|situation|commune)\s*:",
    re.I,
)
_POSTCODE_IN_PARENS = re.compile(r"\(\s*\d{2,5}\s*\)")  # "EXEMPLEVILLE (91)" names a place
_WORD = re.compile(r"[^\W\d_]{4,}")
_MAX_CHARS = 200


def _mostly_upper(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) >= 0.8


def _tidy(text: str) -> str:
    return " ".join(_POSTCODE_IN_PARENS.sub("", text).split()).strip(" -–:;,.")


def _cut(text: str) -> str:
    """Keep what precedes a lot, a label, an address or a party; "" if the line is one."""
    text = _tidy(text)
    starts = [m.start() for p in (_TAIL, _ADDRESS, _ROLE) if (m := p.search(text))]
    return _tidy(text[: min(starts)]) if starts else text


def _is_reference(text: str) -> bool:
    """Parcel or file references ("AB 12 - AB 13"): codes, no words."""
    return any(c.isdigit() for c in text) and not _WORD.search(text)


def _shorten(text: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    return text[:_MAX_CHARS].rsplit(" ", 1)[0] + "…"


def _cover_lines(document: ParsedDocument) -> list[str]:
    first_page = [b for b in document.blocks if b.page == 1]
    blocks = first_page or document.blocks[:15]
    return [" ".join(b.text.split()) for b in blocks if b.text.strip()]


def detect_title(document: ParsedDocument) -> str | None:
    """Return the project name from the cover page, or None when unsure."""
    runs: list[tuple[str, bool]] = []  # (title, labelled)
    run: list[str] = []
    labelled = False
    skip_party = False

    def close() -> None:
        nonlocal run, labelled
        if run:
            runs.append((" ".join(run), labelled))
        run, labelled = [], False

    for cover_line in _cover_lines(document):
        raw = cover_line
        if label := _LABEL.match(raw):
            close()
            labelled, skip_party = True, False
            raw = raw[label.end() :]
            if not raw:
                continue
        elif _ROLE.match(raw):
            close()
            # "MAÎTRE D'OUVRAGE" alone: the next line names the party
            skip_party = len(_cut(_ROLE.sub("", raw, count=1))) < 3
            continue
        if skip_party:
            skip_party = False
            continue
        if _is_reference(raw):
            continue
        line = _cut(raw)
        if len(line) < 3 or _BOILERPLATE.search(line):
            close()
            continue
        if run and not (
            (_mostly_upper(run[-1]) and _mostly_upper(line))
            or _CONTINUES.search(run[-1])
            or line[:1].islower()
        ):
            close()
        run.append(line)
        if len(line) < len(_tidy(raw)):
            close()  # an address or a party followed: the title ends here
    close()

    labelled_runs = [t for t, is_labelled in runs if is_labelled and len(t) >= 6]
    if labelled_runs:
        return _shorten(labelled_runs[0])
    scored = [(len(_WORKS.findall(t)), -i, t) for i, (t, _) in enumerate(runs)]
    if scored and (best := max(scored))[0]:
        return _shorten(best[2])
    capitals = [t for t, _ in runs if _mostly_upper(t) and len(t) >= 6]
    return _shorten(capitals[0]) if capitals else None
