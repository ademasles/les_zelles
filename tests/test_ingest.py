import io

import pytest

from zelles.domain.documents import BlockKind, ParsedDocument
from zelles.ingest.chunking import chunk_document
from zelles.ingest.cleaning import clean_text
from zelles.ingest.outline import detect_heading
from zelles.ingest.parsers import (
    DocxParser,
    UnsupportedDocumentError,
    parse_document,
    sniff_media_type,
)


def test_clean_text_keeps_decimals_and_refs() -> None:
    assert clean_text("Uw ≤ 1,3 W/m² K") == "Uw ≤ 1,3 W/m2 K"
    assert "NF EN 14351-1" in clean_text("NF EN 14351‑1")
    assert clean_text("menui-\nserie") == "menuiserie"


@pytest.mark.parametrize(
    ("line", "level", "lot"),
    [
        ("LOT 05 - MENUISERIES EXTÉRIEURES", 0, True),
        ("Lot n°5 : Menuiseries", 0, True),
        ("3.2.1 Menuiseries PVC", 3, False),
        ("ARTICLE 2 - GÉNÉRALITÉS", 1, False),
    ],
)
def test_detect_heading(line: str, level: int, lot: bool) -> None:
    heading = detect_heading(line)
    assert heading is not None
    assert heading.level == level
    assert heading.is_lot is lot


@pytest.mark.parametrize(
    "line", ["1,3 W/m².K", "20 mm d'épaisseur", "Le présent lot comprend la fourniture."]
)
def test_values_are_not_headings(line: str) -> None:
    assert detect_heading(line) is None


def test_chunks_follow_outline(sample_bytes: bytes) -> None:
    doc, rendition = parse_document(sample_bytes, "cctp.md")
    assert rendition is None
    chunks = chunk_document(doc)
    perf = next(c for c in chunks if c.heading == "2.3 Performances")
    assert perf.lot == "Lot 05 - MENUISERIES EXTÉRIEURES"
    assert perf.scope == "2 MENUISERIES PVC - LOGEMENTS"
    assert "Uw ≤ 1,3" in perf.text
    assert all(c.id == f"c{c.index:04d}" for c in chunks)


def test_pdf_parsing_keeps_pages_and_boxes(sample_pdf: bytes) -> None:
    doc, rendition = parse_document(sample_pdf, "cctp.pdf", ocr=False)
    assert rendition == sample_pdf
    assert doc.page_count >= 1
    assert all(b.page is not None and b.bbox is not None for b in doc.blocks)
    headings = [b.text for b in doc.blocks if b.kind == BlockKind.HEADING]
    assert "2.3 Performances" in headings
    chunks = chunk_document(doc)
    assert any("A*3 E*7B V*A2" in c.text for c in chunks)


def test_docx_parser_uses_heading_styles_and_tables() -> None:
    from docx import Document

    source = Document()
    source.add_heading("LOT 05 - MENUISERIES", level=1)
    source.add_heading("2.3 Performances", level=2)
    source.add_paragraph("Uw ≤ 1,3 W/m².K pour toutes les fenêtres.")
    table = source.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Repère", "Uw"
    table.cell(1, 0).text, table.cell(1, 1).text = "F1", "1,2"
    buffer = io.BytesIO()
    source.save(buffer)

    doc = DocxParser().parse(buffer.getvalue(), "cctp.docx")
    kinds = [b.kind for b in doc.blocks]
    assert kinds == [BlockKind.HEADING, BlockKind.HEADING, BlockKind.PARAGRAPH, BlockKind.TABLE]
    chunks = chunk_document(doc)
    assert chunks[0].lot == "Lot 05 - MENUISERIES"
    assert chunks[0].has_table


def test_sniff_rejects_unknown() -> None:
    with pytest.raises(UnsupportedDocumentError):
        sniff_media_type(b"MZ\x90\x00", "virus.exe")
    with pytest.raises(UnsupportedDocumentError):
        sniff_media_type(b"PK\x03\x04", "archive.zip")


# --------------------------------------------------------------------------- cover title
def _cover(*lines: str) -> ParsedDocument:
    from zelles.domain.documents import Block

    blocks = [Block(kind=BlockKind.PARAGRAPH, text=t, page=1) for t in lines]
    blocks.append(Block(kind=BlockKind.PARAGRAPH, text="Construction d'un hangar", page=2))
    return ParsedDocument(filename="cctp.pdf", media_type="application/pdf", blocks=blocks)


def test_title_is_the_line_naming_the_works() -> None:
    from zelles.ingest.title import detect_title

    doc = _cover(
        "CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES",
        "LOT N°05 MENUISERIES EXTÉRIEURES",
        "Maître d'ouvrage : Office public de l'habitat",
        "CONSTRUCTION DE 32 LOGEMENTS COLLECTIFS ET D'UN PARKING",
        "12 rue des Lilas",
        "91000 Exempleville",
        "Phase DCE - Indice B - Date : 03/2026",
    )
    assert detect_title(doc) == "CONSTRUCTION DE 32 LOGEMENTS COLLECTIFS ET D'UN PARKING"


def test_title_prefers_a_labelled_operation() -> None:
    from zelles.ingest.title import detect_title

    doc = _cover(
        "Opération : Réhabilitation du groupe scolaire des Érables",
        "Extension du bâtiment B",
    )
    assert detect_title(doc) == "Réhabilitation du groupe scolaire des Érables"


def test_no_title_when_the_cover_is_only_boilerplate() -> None:
    from zelles.ingest.title import detect_title

    doc = _cover("C.C.T.P.", "Lot 02 - Menuiseries extérieures", "Architecte : Atelier X")
    assert detect_title(doc) is None


def test_sample_cctp_gets_its_title(sample_bytes: bytes) -> None:
    from zelles.ingest.title import detect_title

    doc, _ = parse_document(sample_bytes, "cctp.md")
    assert detect_title(doc) == (
        "Construction de 24 logements collectifs - Résidence Les Tilleuls "
        "(document synthétique de test)"
    )


def test_title_joins_capital_lines_and_drops_parties_and_address() -> None:
    from zelles.ingest.title import detect_title

    doc = _cover(
        "MARCHÉ PUBLIC DE TRAVAUX",
        "MAÎTRE D'OUVRAGE",
        "COMMUNE D'EXEMPLEVILLE",
        "RESTRUCTURATION DU GROUPE SCOLAIRE",
        "JEAN MOULIN - BÂTIMENT B",
        "12 rue des Lilas 91000 Exempleville",
        "Architecte : Atelier X",
        "CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES",
    )
    assert detect_title(doc) == "RESTRUCTURATION DU GROUPE SCOLAIRE JEAN MOULIN - BÂTIMENT B"


def test_title_after_a_label_on_its_own_line() -> None:
    from zelles.ingest.title import detect_title

    doc = _cover(
        "REMPLACEMENT DES MENUISERIES EXTÉRIEURES",
        "Opération",
        "Résidence Les Érables - 48 logements",
        "Lot 03 Menuiseries extérieures",
    )
    assert detect_title(doc) == "Résidence Les Érables - 48 logements"


def test_title_cuts_an_address_glued_to_the_line() -> None:
    from zelles.ingest.title import detect_title

    doc = _cover(
        "Description du projet : Construction d'une crèche de 60 berceaux "
        "Site Nord 4 avenue des Peupliers 94000 Exempleville",
    )
    assert detect_title(doc) == "Construction d'une crèche de 60 berceaux Site Nord"


def test_title_falls_back_to_a_short_capital_name() -> None:
    from zelles.ingest.title import detect_title

    doc = _cover("PARC NORD - HALL C", "DOSSIER DCE", "LOT 05 MENUISERIES EXTÉRIEURES")
    assert detect_title(doc) == "PARC NORD - HALL C"
