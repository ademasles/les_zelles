"""Keep the joinery lot of a CCTP that covers every trade.

Many tenders publish one CCTP for all lots. Read whole, it yields hundreds of
values from masonry, plumbing or roofing that an estimator for the joinery lot
does not want. When the outline shows several lots and some of them are
joinery, extraction reads only those lots and the text outside any lot
(general clauses that bind every trade).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from zelles.corpus.boamp import Lot
from zelles.domain.documents import Chunk

# Below this share of the text, a "joinery lot" is more likely a stray heading
# ("Lot 05 : voir CCTP menuiseries") than the chapter itself.
MIN_SHARE = 0.03


@dataclass(frozen=True)
class Focus:
    chunks: list[Chunk]
    lots: list[str]  # the joinery lots kept; empty when the whole text is read
    dropped: int


def joinery_lot(label: str) -> bool:
    return Lot("", label).is_joinery


def focus_on_joinery(chunks: Sequence[Chunk]) -> Focus:
    """The chunks of the joinery lots plus those outside any lot, when that is safe."""
    labels = list(dict.fromkeys(c.lot for c in chunks if c.lot))
    keep = [label for label in labels if joinery_lot(label)]
    whole = Focus(list(chunks), [], 0)
    if not keep or len(keep) == len(labels):
        return whole
    size = sum(len(c.text) for c in chunks) or 1
    joinery_size = sum(len(c.text) for c in chunks if c.lot in keep)
    if joinery_size / size < MIN_SHARE:
        return whole
    kept = [c for c in chunks if c.lot is None or c.lot in keep]
    return Focus(kept, keep, len(chunks) - len(kept))
