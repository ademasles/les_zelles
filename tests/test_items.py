"""Joinery items: the spec sheet grouped by the item each value applies to."""

from __future__ import annotations

import pytest

from zelles.domain.documents import Chunk
from zelles.domain.items import ItemKind, build_items, code_of, kind_of
from zelles.domain.spec import SpecField, SpecSheet
from zelles.extraction.rules import extract_with_rules
from zelles.ingest.chunking import chunk_document
from zelles.ingest.parsers import parse_document

F = SpecField


@pytest.mark.parametrize(
    ("heading", "kind"),
    [
        ("3.2.1 Fenêtres PVC des logements", ItemKind.WINDOW),
        ("02.05.01 CHÂSSIS OSCILLO-BATTANT DU PRÉAU", ItemKind.WINDOW),
        ("Porte-fenêtre à 2 vantaux", ItemKind.WINDOW),
        ("3.1.4 M7 - dim. 120x215", ItemKind.WINDOW),
        ("02.01.02 PORTE D'ENTRÉE VITRÉE DU HALL", ItemKind.DOOR),
        ("6.2.1 Bloc-porte plein du local technique", ItemKind.DOOR),
        ("3.3 Façade vitrée du foyer et baies d'accès", ItemKind.FACADE),
        ("02.08 VOLETS ROULANTS DES CHAMBRES", ItemKind.SHUTTER),
        ("4.4 Stores à projection des bureaux", ItemKind.SHUTTER),
        ("2.1 Généralités", None),
        ("Prescriptions communes aux menuiseries", None),
        ("2.9 Spécifications de quincaillerie", None),
        ("6.3 Baies d'accès du garage", ItemKind.DOOR),
        ("3.6 Tablettes intérieures", None),
        ("1.4 CARACTÉRISTIQUES DES PROFILÉS", None),
        ("3.2 Ensemble de menuiserie du préau", ItemKind.WINDOW),
        ("8.2 Ensemble de boîtes aux lettres", None),
        ("8.1 Signalétique du bâtiment", None),
        ("1.4.1 MENUISERIES BOIS", None),
        ("3.7 Calfeutrements des fenêtres et portes", None),
    ],
)
def test_kind_of_a_heading(heading: str, kind: ItemKind | None) -> None:
    assert kind_of(heading) is kind


def test_code_of_a_heading() -> None:
    assert code_of("3.1.4 M7 - dim. 120x215") == "M7"
    assert code_of("Porte PE 3 du hall") == "PE3"
    assert code_of("3.2 Fenêtres PVC") is None


def _read(text: str) -> tuple[SpecSheet, list[Chunk]]:
    document, _ = parse_document(text.encode(), "cctp.md")
    chunks = chunk_document(document)
    reqs = extract_with_rules(chunks)
    sheet = SpecSheet(document_id="d", filename="cctp.md", model="rules", requirements=reqs)
    return sheet, chunks


def _sheet(text: str) -> SpecSheet:
    return _read(text)[0]


CCTP = (
    "# 2 Menuiseries extérieures\n\n"
    "## 2.1 Généralités\n\n"
    "Toutes les menuiseries auront un coefficient Uw ≤ 1,4 W/m².K.\n\n"
    "Le vitrage sera un double vitrage 4/16/4 à remplissage argon.\n\n"
    "## 2.2 Fenêtres PVC M1\n\n"
    "Fenêtres en PVC blanc, ouvrant à la française, Uw ≤ 1,3 W/m².K.\n\n"
    "## 2.3 Porte d'entrée P1\n\n"
    "Porte en aluminium avec serrure 3 points.\n\n"
    "## 2.4 Volets roulants\n\n"
    "Volets roulants en aluminium à manœuvre électrique.\n"
)


def test_values_are_grouped_by_item_in_reading_order() -> None:
    book = build_items(_sheet(CCTP))
    assert [(i.codes[0] if i.codes else None, i.kind) for i in book.items] == [
        ("M1", ItemKind.WINDOW),
        ("P1", ItemKind.DOOR),
        (None, ItemKind.SHUTTER),
    ]
    window = book.items[0]
    assert [r.numeric_value for r in window.own(F.UW)] == [1.3]
    assert window.own(F.FRAME_MATERIAL)
    assert F.UW in book.general


def test_items_inherit_general_clauses_they_do_not_state() -> None:
    book = build_items(_sheet(CCTP))
    window, door, shutter = book.items
    # the window states its own Uw: the general 1.4 does not override it
    assert all(not v.inherited for v in window.values[F.UW])
    # the door states none: it inherits the general Uw, marked as such
    assert door.values[F.UW] and all(v.inherited for v in door.values[F.UW])
    assert any(v.inherited for v in door.values.get(F.GLAZING_COMPOSITION, []))
    # a shutter has no glazing or Uw of its own
    assert F.UW not in shutter.values and F.GLAZING_COMPOSITION not in shutter.values
    assert shutter.own(F.SHUTTERS)
    # standards bind the whole tender, not each item
    assert all(F.STANDARDS not in i.values or i.own(F.STANDARDS) for i in book.items)


def test_values_follow_the_catalogue_order_within_an_item() -> None:
    book = build_items(_sheet(CCTP))
    order = list(book.items[0].values)
    assert order == sorted(order, key=list(F).index)


TWO_CHAPTERS = (
    "# 4 Menuiseries extérieures\n\n"
    "## 4.0 Généralités\n\n"
    "### 4.0.1 Caractéristiques des matériaux\n\n"
    "#### 4.0.1.1 Menuiseries aluminium\n\n"
    "Profilés en aluminium thermolaqué à rupture de pont thermique.\n\n"
    "#### 4.0.1.2 Menuiseries bois\n\n"
    "Bois de classe d'emploi 3, finition lasurée.\n\n"
    "## 4.1 Portes\n\n"
    "### 4.1.1 Type 1\n\n"
    "#### 4.1.1.1 Porte vitrée\n\n"
    "ME01 - Porte en aluminium avec serrure 3 points.\n\n"
    "### 4.1.2 Type 2\n\n"
    "#### 4.1.2.1 Porte vitrée\n\n"
    "Porte en aluminium avec serrure à larder.\n\n"
    "## 4.2 Tablettes d'appuis\n\n"
    "Tablettes en aluminium laqué RAL 7016.\n\n"
    "# 5 Menuiseries intérieures\n\n"
    "## 5.0 Généralités\n\n"
    "Les blocs-portes seront à âme pleine.\n\n"
    "Les huisseries seront en bois avec affaiblissement acoustique Rw ≥ 35 dB.\n\n"
    "## 5.1 Bloc-porte des bureaux\n\n"
    "Bloc-porte en bois, serrure à condamnation.\n"
)


def test_items_with_their_outline_marks_and_chapter_clauses() -> None:
    sheet, chunks = _read(TWO_CHAPTERS)
    book = build_items(sheet, chunks)
    names = [(i.group, i.name) for i in book.items]
    assert names == [
        ("4.1.1 Type 1", "4.1.1.1 Porte vitrée"),
        ("4.1.2 Type 2", "4.1.2.1 Porte vitrée"),
        ("5 Menuiseries intérieures", "5.1 Bloc-porte des bureaux"),
    ], names
    first, _, office = book.items
    assert first.codes == ["ME01"]
    # the material clauses are general, and an aluminium door takes only the aluminium ones
    assert F.FINISH not in first.values or all(
        "lasur" not in v.requirement.value for v in first.values[F.FINISH]
    )
    # a clause of the interior chapter does not bind an exterior door
    assert F.ACOUSTIC not in first.values
    assert office.values.get(F.ACOUSTIC) and all(v.inherited for v in office.values[F.ACOUSTIC])
    # accessories are kept apart and bind no item
    assert any("Tablettes" in name for name in book.accessories)


PARENT_AND_TRADES = (
    "# 5 Menuiseries extérieures\n\n"
    "## 5.1 Brise-soleil orientable\n\n"
    "Brise-soleil orientable à lames de 80 mm, manœuvre électrique.\n\n"
    "### 5.1.1 Brise-soleil des bureaux\n\n"
    "BSO avec coulisses en aluminium extrudé.\n\n"
    "## 5.2 Signalétique extérieure\n\n"
    "Lettres découpées en aluminium laqué RAL 7016.\n"
)


def test_a_parent_item_describes_its_children_and_other_trades_are_set_aside() -> None:
    sheet, chunks = _read(PARENT_AND_TRADES)
    book = build_items(sheet, chunks)
    assert [i.name for i in book.items] == ["5.1.1 Brise-soleil des bureaux"]
    shutters = book.items[0].values[F.SHUTTERS]
    assert any(not v.inherited for v in shutters)
    assert any(v.inherited and "80 mm" in v.requirement.value for v in shutters), shutters
    assert "5.2 Signalétique extérieure" in book.outside


def test_a_family_heading_is_the_item_when_nothing_is_more_precise() -> None:
    book = build_items(
        _sheet("# 3 Menuiseries PVC\n\nMenuiseries en PVC blanc, Uw ≤ 1,3 W/m².K.\n")
    )
    assert [i.name for i in book.items] == ["3 Menuiseries PVC"]


TYPES = (
    "# 5 Menuiseries extérieures\n\n"
    "## 5.1 Façade vitrée du foyer\n\n"
    "Menuiseries en aluminium à rupture de pont thermique, serrure 3 points.\n\n"
    "### 5.1.1 Châssis repère A\n\n"
    "ME11 - Châssis de 2100 x 1500 mm, localisation foyer.\n\n"
    "### 5.1.2 Châssis repère B\n\n"
    "ME12 - Châssis de 900 x 1500 mm avec imposte, voir aussi ME11.\n"
)


def test_every_item_heading_is_an_item_and_takes_its_parent_description() -> None:
    sheet, chunks = _read(TYPES)
    book = build_items(sheet, chunks)
    assert [(i.name, i.codes) for i in book.items] == [
        ("5.1.1 Châssis repère A", ["ME11"]),
        ("5.1.2 Châssis repère B", ["ME12"]),
    ]
    for item in book.items:
        assert item.values.get(F.FRAME_MATERIAL), item.name
        assert all(v.inherited for v in item.values[F.FRAME_MATERIAL])
    # the parent's values bind its children, not the whole tender
    assert F.FRAME_MATERIAL not in book.general


ANNEXES = (
    "# 5 Menuiseries\n\n"
    "## 5.0 Sommaire\n\n"
    "### 5.2.1 Porte de garage - Bat\n\n"
    "Page 6\n\n"
    "## 5.1 Menuiseries du foyer\n\n"
    "### 5.1.1 Fenêtre type 1\n\n"
    "Fenêtre en aluminium, Uw ≤ 1,4 W/m².K.\n\n"
    "### 5.1.4 Ouvrages annexes\n\n"
    "#### 5.1.4.1 Dispositif anti-pince-doigts\n\n"
    "Joint anti-pince-doigts sur toutes les portes, en PVC noir.\n\n"
    "## 5.2 Garage\n\n"
    "### 5.2.1 Porte de garage - Battante\n\n"
    "Porte en acier, serrure 3 points.\n"
)


def test_annex_clauses_bind_their_chapter_and_contents_lines_make_no_item() -> None:
    sheet, chunks = _read(ANNEXES)
    book = build_items(sheet, chunks)
    names = [i.name for i in book.items]
    assert names == ["5.1.1 Fenêtre type 1", "5.2.1 Porte de garage - Battante"], names
    _, door = book.items
    annex = {
        r.value for r in sheet.requirements if r.scope == "5.1.4.1 Dispositif anti-pince-doigts"
    }
    assert annex, "the annex states something"
    # the annex binds the items of 5.1, not the door of 5.2
    inherited = {v.requirement.value for vs in door.values.values() for v in vs if v.inherited}
    assert not annex & inherited


REVISIONS = (
    "# MODIFICATIONS\n\n"
    "Indice B : mise à jour des performances, Uw ≤ 1,7 W/m².K supprimé.\n\n"
    "## 4.0 Généralités\n\n"
    "Les menuiseries auront un Uw ≤ 1,4 W/m².K.\n\n"
    "## 4.1 Fenêtres PVC\n\n"
    "Fenêtres en PVC blanc.\n"
)


def test_a_revision_block_heading_does_not_take_the_lot_clauses_with_it() -> None:
    sheet, chunks = _read(REVISIONS)
    book = build_items(sheet, chunks)
    (window,) = book.items
    uw = [v.requirement.numeric_value for v in window.values.get(F.UW, [])]
    assert 1.4 in uw and 1.7 not in uw, uw
    assert "MODIFICATIONS" in book.outside


KINDS = (
    "# 3 Menuiseries aluminium\n\n"
    "## 3.1 Généralités\n\n"
    "Les fenêtres auront un coefficient Uw ≤ 1,4 W/m².K. Les portes auront un Ud ≤ 1,8 W/m².K.\n\n"
    "Quincaillerie : ferme-porte hydraulique à bras compas.\n\n"
    "Les fenêtres seront équipées de crémones à 2 points.\n\n"
    "Isolement acoustique Ra,tr ≥ 30 dB.\n\n"
    "Les volets roulants auront des lames en aluminium à manœuvre électrique.\n\n"
    "Teinte RAL 7016.\n\n"
    "## 3.2 Fenêtres F1\n\n"
    "Fenêtres oscillo-battantes en aluminium.\n\n"
    "## 3.3 Porte d'entrée P1\n\n"
    "Porte en aluminium vitrée.\n\n"
    "## 3.4 Volets roulants des chambres\n\n"
    "Coffre extérieur.\n"
)


def test_each_kind_of_item_inherits_only_what_describes_it() -> None:
    sheet, chunks = _read(KINDS)
    window, door, shutter = build_items(sheet, chunks).items

    def inherited(item, field):  # type: ignore[no-untyped-def]
        return [v.requirement.value for v in item.values.get(field, []) if v.inherited]

    assert inherited(window, F.UW) == ["Uw ≤ 1,4 W/m2.K"]
    assert inherited(door, F.UW) == ["Ud ≤ 1,8 W/m2.K"]  # the tender gives doors their own Ud
    assert inherited(window, F.HARDWARE) == ["crémones à 2 points"]
    assert inherited(door, F.HARDWARE) == ["ferme-porte hydraulique à bras compas"]
    # the shutters are items of their own: their clause is not the windows'
    assert inherited(window, F.SHUTTERS) == []
    assert inherited(shutter, F.SHUTTERS) != []
    # a shutter takes colours and its own clauses, not the windows' acoustics or Uw
    assert set(shutter.values) == {F.COLOR, F.SHUTTERS}
