"""Wording variants: the matcher and the rules on synthetic CCTP sentences."""

from __future__ import annotations

import pytest

from zelles.evaluation.harness import _comparable


@pytest.mark.parametrize(
    ("want", "have"),
    [
        ("20.501", "conforme à la norme NF P 20-501"),
        ("20.501", "essais selon NF.P 20 501"),
        ("NF P 20-501", "essais selon NF.P 20.501"),
        ("DTU 39", "mise en oeuvre suivant le D.T.U. n°39"),
        ("DTU 39", "suivant le D.T.U. N° 39 Vitrerie"),
        ("1 aout 2006", "arrêté du 1er août 2006 relatif à l'accessibilité"),
        ("S.N.J.F", "joints titulaires du label S.N.J.F."),
        ("NFS 61-937", "conforme aux normes NFS 61.937"),
        ("1.30 m", "commandes situées entre 0,90 et 1,30 m"),
    ],
)
def test_comparable_folds_wording_variants(want: str, have: str) -> None:
    assert _comparable(want) in _comparable(have)


@pytest.mark.parametrize(
    ("want", "have"),
    [
        ("20.501", "norme NF P 20.502"),
        ("DTU 39", "DTU 36.5"),
        ("4/16/4", "4/20/4"),
    ],
)
def test_comparable_keeps_different_values_apart(want: str, have: str) -> None:
    assert _comparable(want) not in _comparable(have)
