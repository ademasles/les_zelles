"""Split the tender corpus into train, validation and a sealed test set.

Tenders from one buyer share an author and a template, so they are split as a
group: a buyer's tenders all land in the same split, and a rule tuned on one
cannot leak into the score of another. Groups are ordered by a salted hash and
filled split by split, so the assignment is reproducible from the salt and does
not depend on the order of the input.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from zelles.corpus.boamp import fold

SPLITS = ("test", "validation", "train")
DEFAULT_SHARES: Mapping[str, float] = {"test": 0.4, "validation": 0.2, "train": 0.4}
SEAL_FILE = "SEALED"

_LEGAL_FORM = re.compile(r"\b(sa|sas|sarl|sem|spl|opac|oph|epa|epic)\b")


def buyer_group(buyer: str) -> str:
    """The buyer name without accents, case, punctuation or legal form."""
    words = re.sub(r"[^a-z0-9]+", " ", fold(buyer))
    return " ".join(_LEGAL_FORM.sub(" ", words).split())


class Split(BaseModel):
    """Which split each case belongs to, and how it was drawn."""

    salt: str
    shares: dict[str, float]
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cases: dict[str, str] = Field(default_factory=dict, description="case id -> split")

    def members(self, split: str) -> list[str]:
        return sorted(c for c, s in self.cases.items() if s == split)

    def counts(self) -> dict[str, int]:
        return {s: len(self.members(s)) for s in SPLITS}


def _rank(salt: str, group: str) -> str:
    return hashlib.sha256(f"{salt}\0{group}".encode()).hexdigest()


def assign(
    cases: Iterable[tuple[str, str]],
    *,
    salt: str,
    shares: Mapping[str, float] = DEFAULT_SHARES,
    existing: Split | None = None,
) -> Split:
    """Assign ``(case id, buyer)`` pairs to splits, keeping each buyer in one split.

    Cases already in ``existing`` keep their split, and so do new cases from a
    buyer it already placed, so the sealed test set only ever grows.
    """
    if set(shares) != set(SPLITS) or abs(sum(shares.values()) - 1) > 1e-9:
        raise ValueError(f"shares must cover {SPLITS} and sum to 1")
    pairs = list(cases)
    placed = dict(existing.cases) if existing else {}
    group_of = {case: buyer_group(buyer) for case, buyer in pairs}
    group_split: dict[str, str] = {}
    for case, split in placed.items():
        if case in group_of:
            group_split[group_of[case]] = split
    groups: dict[str, list[str]] = defaultdict(list)
    for case, group in group_of.items():
        groups[group].append(case)

    total = len({*placed, *group_of})
    target = {s: round(shares[s] * total) for s in SPLITS}
    count = dict.fromkeys(SPLITS, 0)
    for case, split in placed.items():
        if case not in group_of:  # placed earlier, not in this input
            count[split] += 1
    for group, split in group_split.items():
        count[split] += len(groups[group])

    for group in sorted(groups, key=lambda g: _rank(salt, g)):
        if group in group_split:
            continue
        split = next((s for s in SPLITS if count[s] < target[s]), "train")
        group_split[group] = split
        count[split] += len(groups[group])

    for case, group in group_of.items():
        placed[case] = group_split[group]
    return Split(
        salt=existing.salt if existing else salt,
        shares=dict(existing.shares if existing else shares),
        cases=dict(sorted(placed.items())),
    )


def read_manifest(path: Path) -> list[tuple[str, str]]:
    """``(idweb, buyer)`` for each downloaded tender in a corpus manifest CSV."""
    with path.open(newline="", encoding="utf-8") as f:
        return [
            (row["idweb"], row.get("buyer", ""))
            for row in csv.DictReader(f)
            if row.get("status", "ok").strip().lower() in {"ok", "yes", ""}
        ]
