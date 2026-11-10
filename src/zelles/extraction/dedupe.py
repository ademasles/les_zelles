"""Merge near-duplicate values of one field into the most complete one.

Rules often read one requirement several times: "SP615" and "type SP615 ou
équivalent", "D.T.U. 36.5" and "NF D.T.U. 36.5", "treuil" and "manœuvre par
treuil à tige". An estimator reads those as noise. When every meaningful word
of a value also appears in a longer value of the same field, the shorter one
is dropped and its place is noted on the one kept; between two values with
the same words, the first one read is kept.

Only descriptive fields are merged. Numbers, classes and materials stay apart:
"aluminium" and "bois-aluminium" are two different frames.
"""

from __future__ import annotations

from zelles.domain.spec import Requirement, SpecField
from zelles.retrieval.text import STOPWORDS, comparable

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


def _words(value: str) -> frozenset[str]:
    return frozenset(
        w for w in comparable(value).replace(":", " ").split() if w not in STOPWORDS | _LABELS
    )


def merge_near_duplicates(requirements: list[Requirement]) -> list[Requirement]:
    """Drop values whose words are all contained in a longer value of the same field."""
    words = [_words(r.value) for r in requirements]
    absorbed_by: dict[int, int] = {}
    for i, req in enumerate(requirements):
        if req.field not in MERGED_FIELDS or req.numeric_value is not None or not words[i]:
            continue
        candidates = [
            j
            for j, other in enumerate(requirements)
            if j != i
            and other.field == req.field
            and other.status == req.status
            and words[i] <= words[j]
            and (len(words[i]) < len(words[j]) or (words[i] == words[j] and j < i))
        ]
        if candidates:
            # the most complete value wins; ties go to the first one read
            absorbed_by[i] = max(candidates, key=lambda j: (len(words[j]), -j))

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
