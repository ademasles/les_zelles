"""Joinery focus: a CCTP for every trade is read for its joinery lots only."""

from __future__ import annotations

from zelles.domain.documents import Chunk
from zelles.extraction.scope import focus_on_joinery


def _chunk(i: int, lot: str | None, size: int = 400) -> Chunk:
    return Chunk(id=f"c{i}", index=i, text="x" * size, lot=lot)


def test_keeps_joinery_lots_and_common_clauses() -> None:
    chunks = [
        _chunk(0, None),
        _chunk(1, "Lot 02 - Gros oeuvre"),
        _chunk(2, "Lot 05 - Menuiseries extérieures aluminium"),
        _chunk(3, "Lot 06 - Occultations"),
        _chunk(4, "Lot 07 - Menuiseries intérieures"),
    ]
    focus = focus_on_joinery(chunks)
    assert [c.id for c in focus.chunks] == ["c0", "c2", "c3"]
    assert focus.lots == ["Lot 05 - Menuiseries extérieures aluminium", "Lot 06 - Occultations"]
    assert focus.dropped == 2


def test_reads_everything_when_the_lot_split_is_not_trustworthy() -> None:
    single = [_chunk(0, "Lot 05 - Menuiseries extérieures"), _chunk(1, None)]
    assert focus_on_joinery(single).lots == []  # a joinery-only CCTP
    no_joinery = [_chunk(0, "Lot 01 - VRD"), _chunk(1, "Lot 02 - Gros oeuvre")]
    assert focus_on_joinery(no_joinery).lots == []
    stray = [_chunk(0, "Lot 02 - Gros oeuvre", 100_000), _chunk(1, "Lot 05 - Menuiseries", 100)]
    assert len(focus_on_joinery(stray).chunks) == 2  # a stray heading, not the chapter
