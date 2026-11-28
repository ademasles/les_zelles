"""Layout and wording seen in real Word-exported CCTPs (synthetic text, same patterns)."""

import pytest

from zelles.domain.documents import BBox, Chunk
from zelles.domain.spec import SpecField
from zelles.extraction.rules import extract_with_rules
from zelles.ingest.cleaning import clean_text
from zelles.ingest.furniture import is_toc_line, strip_furniture
from zelles.ingest.outline import detect_heading
from zelles.ingest.parsers import _blocks_from_lines, lines_from_chars


def test_word_hyphen_codes_and_symbol_bullets_are_kept() -> None:
    raw = "NF EN 14351\x1e1, vitrage 33.1\x1e15\x1e4, oscillo\x1ebattant,  item, −10"
    assert clean_text(raw) == "NF EN 14351-1, vitrage 33.1-15-4, oscillo-battant, - item, -10"


def test_lines_come_from_pdfium_text_with_char_boxes() -> None:
    # pdfium returns "NF EN 14351-1" and "Emissivité" whole in its page text,
    # while per-rectangle extraction split them at the hyphen and the small capital.
    text = "NF EN 14351-1\r\nTrès Basse Emissivité\r\n"
    boxes: list[tuple[float, float, float, float] | None] = []
    for line_index, line in enumerate(text.split("\r\n")):
        top = 800.0 - 20 * line_index
        boxes += [
            None if c.isspace() else (50.0 + 5 * i, top - 10, 55.0 + 5 * i, top)
            for i, c in enumerate(line)
        ]
        boxes += [None, None]
    lines = lines_from_chars(text, boxes[: len(text)], 842.0)
    assert [t for t, _ in lines] == ["NF EN 14351-1", "Très Basse Emissivité"]
    first_box = lines[0][1]
    assert first_box is not None and first_box.y0 == 42.0 and first_box.x1 == 115.0


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
        "- Etanchéité à l'air : classe A 3\n- Etanchéité à l'eau : classe E 7B\n"
        "- Etanchéité au vent : classe V A3\n"
        "Fenêtre de toit basculante en bois. Classement Air Eau Vent : A*3 E*9 V*A3.\n"
        "Double vitrage type 4.16.4 clair, Très Basse Emissivité (intercalaires noirs).\n"
        "Vitrage feuilleté 33.1-15-4 en allège.\n"
        "Profilés PVC de 70 mm, cinq chambres, renforts acier.\n"
        "Quincaillerie : système Winkhaus ou équivalent.\n"
        "Entrée d'air en traverse haute, module Aldès autoréglable.\n"
        "Persiennes PVC à refoulement latéral.\n"
        "Menuiseries PVC blanc teinté dans la masse.\n"
        "- Coloris blanc\n- Verrouillage automatique\n"
        "Store intérieur occultant, manoeuvre par manivelle. Posées en applique.\n"
        "Isolement acoustique : classement de façade 30 dB(A).\n"
    )
    assert {"A*3 E*7B V*A3", "A*3 E*9 V*A3"} <= found[SpecField.AEV]
    assert any("basculant" in v.lower() for v in found[SpecField.OPENING_TYPE])
    assert {"4.16.4", "33.1-15-4"} <= found[SpecField.GLAZING_COMPOSITION]
    assert any("missivit" in v for v in found[SpecField.GLAZING_TYPE])
    assert any("intercalaires noirs" in v for v in found[SpecField.SPACER])
    assert any("chambres" in v for v in found[SpecField.PROFILE_SYSTEM])
    assert any("Winkhaus" in v for v in found[SpecField.HARDWARE])
    assert any("autoréglable" in v for v in found[SpecField.AIR_INLETS])
    assert any("Persiennes" in v for v in found[SpecField.SHUTTERS])
    assert any("blanc" in v.lower() for v in found[SpecField.COLOR])
    assert not any("Verrouillage" in v for v in found[SpecField.COLOR])
    assert any("teinté dans la masse" in v for v in found[SpecField.FINISH])
    assert any("Store intérieur" in v for v in found[SpecField.SHUTTERS])
    assert any("applique" in v for v in found[SpecField.INSTALLATION])
    assert "30 dB" in found[SpecField.ACOUSTIC]


def test_standard_titles_are_not_requirements() -> None:
    found = _extract(
        "NF EN 13115 : fenêtres - classification des propriétés mécaniques - effort de manœuvre."
    )
    assert SpecField.ACCESSIBILITY not in found
    assert "NF EN 13115" in found[SpecField.STANDARDS]


def test_one_descriptive_value_per_sentence() -> None:
    found = _extract("Persiennes PVC à refoulement latéral, lames persienne fixées par 4 vis.")
    assert len(found[SpecField.SHUTTERS]) == 1


def test_existing_building_sections_are_skipped() -> None:
    existing = Chunk(
        id="c0001",
        index=1,
        text="Les logements sont équipés de persiennes et d'une VMC autoréglable.",
        section_path=["3 Description des installations existantes"],
    )
    works = Chunk(
        id="c0002",
        index=2,
        text="Dépose totale des persiennes existantes.",
        section_path=["4 Dépose des ouvrages existants"],
    )
    reqs = extract_with_rules([existing, works])
    assert {r.citation.chunk_id for r in reqs if r.citation} == {"c0002"}


def test_quantities_are_not_headings() -> None:
    assert detect_heading("3 PC 16 A avec terre, fermées par clapet étanche") is None
    assert detect_heading("5.2 Fenêtres de toit") is not None


def test_citation_page_follows_the_match_across_a_page_break() -> None:
    chunk = Chunk(
        id="c0003",
        index=3,
        text="Fenêtre de toit en bois.\nClassement Air Eau Vent : A*3 E*9 V*A3.",
        page_start=17,
        page_end=18,
        page_offsets=[(0, 17), (25, 18)],
        section_path=["Lot unique", "5 DESCRIPTION DES TRAVAUX", "5.2 Fenêtres de toit"],
        lot="Lot unique",
    )
    (aev,) = [r for r in extract_with_rules([chunk]) if r.field == SpecField.AEV]
    assert aev.citation is not None and aev.citation.page == 18
    assert aev.scope == "5.2 Fenêtres de toit"


def test_generic_headings_do_not_set_the_scope() -> None:
    chunk = Chunk(
        id="c0",
        index=0,
        text="x",
        section_path=["Lot 1", "6.3 OCCULTATION", "FABRICATION", "MIROITERIE"],
        lot="Lot 1",
    )
    assert chunk.scope == "6.3 OCCULTATION"


def test_abbreviations_do_not_end_the_quote() -> None:
    found = _extract("Les ouvrages respecteront le D.T.U. N° 36.1/39.1 en vigueur.")
    assert any("36.1" in v for v in found[SpecField.STANDARDS])


def test_xlsx_export_drops_illegal_characters() -> None:
    from zelles.domain.spec import Citation, Requirement, RequirementSource, SpecSheet
    from zelles.exports import to_xlsx

    req = Requirement(
        field=SpecField.HARDWARE,
        value="targettes-arrêts",
        citation=Citation(chunk_id="c0", quote="grâce aux targettes￾arrêts", page=15),
        source=RequirementSource.RULES,
    )
    sheet = SpecSheet(document_id="0" * 16, filename="x.pdf", model="rules", requirements=[req])
    assert to_xlsx(sheet)[:2] == b"PK"


def test_handle_height_is_an_accessibility_requirement() -> None:
    found = _extract("Les poignées seront placées à une hauteur maximale de 1,30 m du sol.")
    assert any("1,30 m" in v for v in found[SpecField.ACCESSIBILITY])


def test_air_inlet_attenuation_is_not_facade_acoustics() -> None:
    found = _extract("Entrée d'air hygro-régulée, affaiblissement acoustique 37 dB.")
    assert SpecField.ACOUSTIC not in found
    assert any("37 dB" in v for v in found[SpecField.AIR_INLETS])


def test_a_deep_item_heading_that_runs_on_into_its_size() -> None:
    heading = detect_heading("3.4.2.1. Châssis repère A de 1800 x 1350 mm environ, comprenant")
    assert heading is not None and heading.label == "3.4.2.1 Châssis repère A"
    assert heading.rest.startswith("de 1800 x 1350 mm")
    # a shallow numbered line with a quantity is still a list item
    assert detect_heading("3 PC 16 A avec terre, fermées par clapet étanche") is None


def test_capital_labels_inside_an_article_are_not_headings() -> None:
    assert detect_heading("LOCALISATION") is None
    assert detect_heading("NOTA :") is None
    assert detect_heading("MENUISERIES EXTERIEURES") is not None


def test_an_article_number_printed_apart_from_its_title() -> None:
    blocks = _blocks_from_lines(
        [
            _line("Localisation : préau.", 600),
            _line("Porte vitrée à deux vantaux - Finition laquée", 614),
            _line("gris clair", 625),
            _line("02.3.4", 614),
            _line("Fourniture et pose de la porte.", 642),
        ],
        6,
    )
    kinds = [(b.kind.value, b.text) for b in blocks]
    assert (
        "heading",
        "02.3.4 Porte vitrée à deux vantaux - Finition laquée gris clair",
    ) in kinds, kinds
    assert kinds[0] == ("paragraph", "Localisation : préau.")
    # the number may also come first on the row
    first = _blocks_from_lines([_line("02.3.5", 300), _line("Bloc-porte plein", 300)], 1)
    assert [(b.kind.value, b.text) for b in first] == [("heading", "02.3.5 Bloc-porte plein")]


def test_run_on_text_stays_with_its_heading() -> None:
    blocks = _blocks_from_lines(
        [_line("6.1.3.2. Porte de service à un vantail de (900+300) x 2100 m environ", 100)], 17
    )
    assert [(b.kind.value, b.text) for b in blocks] == [
        ("heading", "6.1.3.2 Porte de service à un vantail"),
        ("paragraph", "de (900+300) x 2100 m environ"),
    ]


def test_a_long_run_on_item_line_is_still_a_heading() -> None:
    line = (
        "3.4.2.2. Châssis repère B de 2400 x 1600 mm environ, comprenant une partie fixe "
        "en allège et deux ouvrants à la française en partie haute, avec traverse "
        "intermédiaire et vitrage isolant"
    )
    assert len(line) > 160
    heading = detect_heading(line)
    assert heading is not None and heading.label == "3.4.2.2 Châssis repère B"


def test_a_list_line_in_capitals_is_not_a_heading() -> None:
    assert detect_heading('- "SALLE DES FETES"') is None
    assert detect_heading("- ACCUEIL DU PUBLIC") is None


def test_an_unnumbered_title_closes_with_its_numbered_article() -> None:
    from zelles.domain.documents import Block, BlockKind, ParsedDocument
    from zelles.ingest.chunking import chunk_document

    def h(text: str, level: int) -> Block:
        return Block(kind=BlockKind.HEADING, text=text, heading_level=level)

    def para(text: str) -> Block:
        return Block(text=text)

    doc = ParsedDocument(
        filename="cctp.pdf",
        media_type="application/pdf",
        blocks=[
            h("5.1.2 Protections solaires", 3),
            h("BRISE SOLEIL ORIENTABLE", 1),
            para("Lames de 80 mm."),
            h("5.1.2.1 Ensemble BSO", 4),
            para("Manœuvre électrique."),
            h("5.2 Serrurerie", 2),
            para("Portes en acier."),
        ],
    )
    paths = [c.section_path for c in chunk_document(doc)]
    assert paths == [
        ["5.1.2 Protections solaires", "BRISE SOLEIL ORIENTABLE"],
        ["5.1.2 Protections solaires", "BRISE SOLEIL ORIENTABLE", "5.1.2.1 Ensemble BSO"],
        ["5.2 Serrurerie"],
    ], paths


@pytest.mark.parametrize(
    "line",
    [
        "12 Rue des Lilas - 12345 BOURGVILLE - contact",
        "3 Avenue des Tilleuls",
        "54321 VALMONT",
        "12345 LE VALBOURG",
        "54321 ST ALBANEUF SUR ORNE",
        "2 MARS 2025 Mise à jour suite avis",
        "98 765 SAINT EXEMPLE SUR LOIRE",
        "10000001-A1-01-XX-PLN_V1 BAT A 01/01/2026",
        "800x1200 // TEINTE",
    ],
)
def test_title_block_lines_are_not_headings(line: str) -> None:
    assert detect_heading(line) is None


def test_headings_with_standards_or_sizes_are_kept() -> None:
    assert detect_heading("3.2 Fenêtres conformes à la NF EN 14351") is not None
    assert detect_heading("CHAPITRE 2 - CLAUSES COMMUNES") is not None
