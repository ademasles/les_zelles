"""Layout and wording seen in real Word-exported CCTPs (synthetic text, same patterns)."""

import pytest

from zelles.domain.documents import BBox, Chunk
from zelles.domain.spec import SpecField
from zelles.extraction.rules import extract_with_rules
from zelles.ingest.cleaning import clean_text
from zelles.ingest.furniture import is_toc_line, strip_furniture
from zelles.ingest.outline import detect_heading
from zelles.ingest.parsers import _merge


def test_word_hyphen_codes_and_symbol_bullets_are_kept() -> None:
    raw = "NF EN 14351\x1e1, vitrage 33.1\x1e15\x1e4, oscillo\x1ebattant,  item, −10"
    assert clean_text(raw) == "NF EN 14351-1, vitrage 33.1-15-4, oscillo-battant, - item, -10"


def test_small_capitals_are_glued() -> None:
    # "O" in a larger font, then "BJET": two touching rects on one baseline.
    segments = [(50.0, 700.0, 58.0, 712.0, "1 O"), (58.2, 700.0, 90.0, 710.0, "BJET")]
    text, _ = _merge(segments, 842.0)
    assert text == "1 OBJET"
    spaced = [(50.0, 700.0, 70.0, 712.0, "Uw"), (74.0, 700.0, 90.0, 712.0, "1,3")]
    assert _merge(spaced, 842.0)[0] == "Uw 1,3"


@pytest.mark.parametrize(
    ("line", "toc"),
    [
        ("1 GENERALITES 3", True),
        ("2.1 OBJET DU MARCHE 4", True),
        ("Article 4 ........ 12", True),
        ("3.2 Vitrages", False),
        ("PORTES FENETRES TYPE 2", False),
        ("Uw ≤ 1,3 W/m².K", False),
    ],
)
def test_toc_lines(line: str, toc: bool) -> None:
    assert is_toc_line(line) is toc


def _line(text: str, y: float) -> tuple[str, BBox]:
    return text, BBox(x0=50, y0=y, x1=400, y1=y + 10)


def test_headers_footers_and_toc_are_removed() -> None:
    height = 842.0
    toc = [
        _line("SOMMAIRE", 120),
        _line("1 GENERALITES 3", 140),
        _line("2 DESCRIPTION DES OUVRAGES 4", 160),
        _line("3 MENUISERIES PVC 5", 180),
    ]
    pages = []
    for number in range(1, 5):
        body = toc if number == 1 else [_line(f"Texte courant de la page {number}.", 300)]
        lines = [
            _line("CABINET EXEMPLE ARCHITECTES - RESIDENCE TEST", 20),
            *body,
            _line(f"Mars 2025 V 1.0 - page {number}/4", 810),
        ]
        pages.append((lines, height))
    cleaned = strip_furniture(pages)
    assert cleaned[0] == []
    assert [t for t, _ in cleaned[2]] == ["Texte courant de la page 3."]


@pytest.mark.parametrize(
    ("line", "label"),
    [
        ("LOT UNIQUE - MENUISERIES EXTERIEURES", "Lot unique MENUISERIES EXTERIEURES"),
        ("5 étapes de traitement du bois sont nécessaires", None),
        ("1 GENERALITES ........ 3", None),
    ],
)
def test_heading_edge_cases(line: str, label: str | None) -> None:
    heading = detect_heading(line)
    assert (heading.label if heading else None) == label


def _extract(text: str) -> dict[SpecField, set[str]]:
    chunk = Chunk(id="c0000", index=0, text=text, section_path=["5 Menuiseries"])
    out: dict[SpecField, set[str]] = {}
    for req in extract_with_rules([chunk]):
        out.setdefault(req.field, set()).add(req.value)
    return out


def test_non_standard_wording_is_extracted() -> None:
    found = _extract(
        "Etanchéité à l'air : classe A 3 / eau E 7B / vent V A3.\n"
        "Double vitrage type 4.16.4 clair, Très Basse Emissivité (intercalaires noirs).\n"
        "Vitrage feuilleté 33.1-15-4 en allège.\n"
        "Profilés PVC de 70 mm, cinq chambres, renforts acier.\n"
        "Quincaillerie : système Winkhaus ou équivalent.\n"
        "Entrée d'air en traverse haute, module Aldès autoréglable.\n"
        "Persiennes PVC à refoulement latéral.\n"
        "Menuiseries PVC blanc teinté dans la masse.\n"
        "Isolement acoustique : classement de façade 30 dB(A).\n"
    )
    assert "A*3 E*7B V*A3" in found[SpecField.AEV]
    assert {"4.16.4", "33.1-15-4"} <= found[SpecField.GLAZING_COMPOSITION]
    assert any("missivit" in v for v in found[SpecField.GLAZING_TYPE])
    assert any("intercalaires noirs" in v for v in found[SpecField.SPACER])
    assert any("chambres" in v for v in found[SpecField.PROFILE_SYSTEM])
    assert any("Winkhaus" in v for v in found[SpecField.HARDWARE])
    assert any("autoréglable" in v for v in found[SpecField.AIR_INLETS])
    assert any("Persiennes" in v for v in found[SpecField.SHUTTERS])
    assert any("teinté dans la masse" in v for v in found[SpecField.COLOR])
    assert "30 dB" in found[SpecField.ACOUSTIC]


def test_standard_titles_are_not_requirements() -> None:
    found = _extract(
        "NF EN 13115 : fenêtres - classification des propriétés mécaniques - effort de manœuvre."
    )
    assert SpecField.ACCESSIBILITY not in found
    assert "NF EN 13115" in found[SpecField.STANDARDS]
