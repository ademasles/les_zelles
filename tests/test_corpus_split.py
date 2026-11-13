"""Corpus split: one buyer per split, reproducible, and the test set only grows."""

from __future__ import annotations

from pathlib import Path

import pytest

from zelles.corpus.split import assign, buyer_group, read_manifest

CASES = [(f"26-{i}", f"Commune {i // 2}") for i in range(30)]  # 15 buyers, 2 tenders each


def test_buyer_names_are_normalised() -> None:
    assert buyer_group("OPH  Val-d'Oise Habitat") == buyer_group("val d oise habitat")
    assert buyer_group("Société Publique") == "societe publique"


def test_split_keeps_each_buyer_together_and_hits_the_shares() -> None:
    split = assign(CASES, salt="s")
    for i in range(0, 30, 2):
        assert split.cases[f"26-{i}"] == split.cases[f"26-{i + 1}"]
    assert split.counts() == {"test": 12, "validation": 6, "train": 12}


def test_split_is_reproducible_and_order_free() -> None:
    assert assign(CASES, salt="s").cases == assign(CASES[::-1], salt="s").cases
    assert assign(CASES, salt="s").cases != assign(CASES, salt="t").cases


def test_new_tenders_never_move_earlier_ones() -> None:
    first = assign(CASES[:20], salt="s")
    grown = assign([*CASES, ("26-99", "Commune 0")], salt="other", existing=first)
    assert all(grown.cases[c] == s for c, s in first.cases.items())
    assert grown.cases["26-99"] == first.cases["26-0"]  # same buyer, same split
    assert grown.salt == "s"


def test_shares_must_cover_every_split() -> None:
    with pytest.raises(ValueError, match="shares"):
        assign(CASES, salt="s", shares={"test": 1.0})


def test_manifest_keeps_downloaded_rows_only(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "idweb,buyer,status\n26-1,Ville A,ok\n26-2,Ville B,skipped:login\n",
        encoding="utf-8",
    )
    assert read_manifest(manifest) == [("26-1", "Ville A")]
