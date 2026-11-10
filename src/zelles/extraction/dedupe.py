"""Merge near-duplicate values of one field into the most complete one.

Rules often read one requirement several times: "SP615" and "type SP615 ou
équivalent", "D.T.U. 36.5" and "NF D.T.U. 36.5", "treuil" and "manœuvre par
treuil à tige". An estimator reads those as noise. A value is dropped, and
its place noted on the one kept, when it reads as one run of words inside a
longer value of the same field, or when the two differ only by label words
("coloris gris foncé" = "teinte gris foncé"; the longer, then the first
read, is kept). Values only ever fold into a longer or earlier one, so the
merge cannot loop.
Containment must be contiguous: "crémone pompier" is not absorbed by
"crémone à levier, ferme-porte pompier", which says something else.

Only descriptive fields are merged. Numbers, classes and materials stay apart:
"aluminium" and "bois-aluminium" are two different frames.
"""

from __future__ import annotations

from zelles.domain.spec import Requirement, SpecField
from zelles.retrieval.text import comparable

F = SpecField

MERGED_FIELDS = frozenset(
    {
        F.COLOR,
        F.FINISH,
        F.PROFILE_SYSTEM,
        F.GLAZING_TYPE,
        F.SAFETY_GLAZING,
        F.HARDWARE,
        F.SHUTTERS,
        F.INSTALLATION,
        F.STANDARDS,
    }
)

# Label and filler words that do not change a value: "Coloris : blanc" = "blanc".
_LABELS = frozenset(
    {
        "colori",  # "coloris" after the plural fold
        "couleur",
        "teinte",
        "type",
        "ou",
        "equivalent",
        "techniquement",
        "similaire",
    }
)


def _stripped(value: str) -> str:
    return " ".join(w for w in comparable(value).replace(":", " ").split() if w not in _LABELS)


def _absorbs(long: str, short: str) -> bool:
    """``short`` is a whole-word run inside ``long``."""
    return f" {short} " in f" {long} "


def merge_near_duplicates(requirements: list[Requirement]) -> list[Requirement]:
    """Drop values contained in a longer value of the same field, or equal but for labels."""
    plain = [comparable(r.value).replace(":", " ") for r in requirements]
    plain = [" ".join(p.split()) for p in plain]
    bare = [_stripped(r.value) for r in requirements]
    absorbed_by: dict[int, int] = {}
    for i, req in enumerate(requirements):
        if req.field not in MERGED_FIELDS or req.numeric_value is not None or not bare[i]:
            continue
        candidates = [
            j
            for j, other in enumerate(requirements)
            if j != i
            and other.field == req.field
            and other.status == req.status
            and (
                (len(plain[i]) < len(plain[j]) and _absorbs(plain[j], plain[i]))
                or (bare[i] == bare[j] and (len(plain[j]), -j) > (len(plain[i]), -i))
            )
        ]
        if candidates:
            # the most complete value wins; ties go to the first one read
            absorbed_by[i] = max(candidates, key=lambda j: (len(plain[j]), -j))

    def root(i: int) -> int:
        while i in absorbed_by:
            i = absorbed_by[i]
        return i

    kept: dict[int, Requirement] = {}
    for i, req in enumerate(requirements):
        if i not in absorbed_by:
            kept[i] = req
    for i, req in enumerate(requirements):
        if i in absorbed_by:
            keeper = kept[root(i)]
            where = req.citation.locator if req.citation and req.citation.locator else req.scope
            note = f"also stated as '{req.value}'" + (f" ({where})" if where else "")
            if note not in keeper.notes:
                keeper.notes.append(note)
    return [kept[i] for i in sorted(kept)]
