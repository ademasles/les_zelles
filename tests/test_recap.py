"""The drafted recap: items laid out on a form's rows, every value with its page."""

from __future__ import annotations

import io

from openpyxl import load_workbook

from zelles.domain.items import build_items
from zelles.domain.spec import SpecField, SpecSheet
from zelles.extraction.rules import extract_with_rules
from zelles.ingest.chunking import chunk_document
from zelles.ingest.parsers import parse_document
from zelles.recap import (
    DEFAULT_TEMPLATE,
    RecapRow,
    RecapSection,
    RecapTemplate,
    RecapValue,
    draft_recap,
    recap_to_xlsx,
)

F = SpecField

CCTP = (
    "# 2 Menuiseries extérieures\n\n"
    "## 2.1 Généralités\n\n"
    "Toutes les menuiseries auront un coefficient Uw ≤ 1,4 W/m².K.\n\n"
    "Les ouvrages seront conformes au NF DTU 36.5.\n\n"
    "## 2.2 Fenêtres PVC M1\n\n"
    "Fenêtres en PVC blanc, ouvrant à la française, Uw ≤ 1,3 W/m².K.\n\n"
    "## 2.3 Porte d'entrée P1\n\n"
    "Porte en aluminium avec serrure 3 points.\n"
)


def _book() -> tuple[object, str]:
    document, _ = parse_document(CCTP.encode(), "cctp.md")
    chunks = chunk_document(document)
    sheet = SpecSheet(
        document_id="d", filename="cctp.md", model="rules", requirements=extract_with_rules(chunks)
    )
    return build_items(sheet, chunks), sheet.filename


def _cell(recap, column: int, label: str) -> list[str]:
    index = next(i for i, row in enumerate(recap.template.rows()) if row.label == label)
    return [v.line() for v in recap.columns[column].cells[index]]


def test_a_line_gives_the_page_and_marks_an_inherited_value() -> None:
    assert RecapValue(value="Uw ≤ 1,3", page=12).line() == "Uw ≤ 1,3 (p. 12)"
    assert RecapValue(value="Uw ≤ 1,4", page=3, inherited=True).line() == "↑ Uw ≤ 1,4 (p. 3)"


def test_a_value_said_by_a_longer_one_is_left_out() -> None:
    from zelles.recap import _distinct

    lines = _distinct(
        [
            RecapValue(value="remplissage argon", page=2),
            RecapValue(value="double vitrage 4/16/4 à remplissage argon", page=2),
            RecapValue(value="Double vitrage 4/16/4 à remplissage argon", page=5, inherited=True),
            RecapValue(value="intercalaire warm edge", page=5, inherited=True),
        ]
    )
    assert [v.line() for v in lines] == [
        "double vitrage 4/16/4 à remplissage argon (p. 2)",
        "↑ intercalaire warm edge (p. 5)",
    ]


def test_columns_are_general_clauses_then_items_in_order() -> None:
    book, name = _book()
    recap = draft_recap(book, filename=name)
    assert [c.title for c in recap.columns] == [
        "General clauses",
        "2.2 Fenêtres PVC M1",
        "2.3 Porte d'entrée P1",
    ]
    assert recap.columns[1].codes == ["M1"]
    assert all(len(c.cells) == len(DEFAULT_TEMPLATE.rows()) for c in recap.columns)


def test_an_item_states_its_own_value_and_inherits_the_rest() -> None:
    book, name = _book()
    recap = draft_recap(book, filename=name)
    uw = "Uw (window)"
    assert _cell(recap, 1, uw) == ["Uw ≤ 1,3 W/m2.K"]  # its own value replaces the chapter's
    assert _cell(recap, 2, uw) == ["↑ Uw ≤ 1,4 W/m2.K"]  # the door takes the chapter's clause
    assert _cell(recap, 0, "Standards") == ["NF DTU 36.5"]
    assert _cell(recap, 2, "Standards") == []  # tender-wide: stated once, in the general column


def test_values_no_row_takes_stay_in_their_column() -> None:
    from zelles.recap import OTHER_VALUES

    book, name = _book()
    template = RecapTemplate(
        name="short",
        sections=(RecapSection(title="Thermal", rows=(RecapRow(label="Uw", fields=(F.UW,)),)),),
    )
    recap = draft_recap(book, filename=name, template=template)
    last = recap.template.sections[-1]
    assert last.title == OTHER_VALUES
    assert F.UW not in {f for row in last.rows for f in row.fields}
    assert _cell(recap, 1, "Frame material") == ["PVC"]  # the window's own, in its column
    assert _cell(recap, 0, "Standards") == ["NF DTU 36.5"]
    assert all(len(c.cells) == len(recap.template.rows()) for c in recap.columns)


def test_the_workbook_shows_values_with_their_page() -> None:
    book, name = _book()
    data = recap_to_xlsx(draft_recap(book, filename=name))
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Recap", "Sources", "Not on an item"]
    form = wb["Recap"]
    assert [form.cell(3, c).value for c in range(2, 5)] == [
        "General clauses",
        "2.2 Fenêtres PVC M1",
        "2.3 Porte d'entrée P1",
    ]
    labels = [form.cell(r, 1).value for r in range(1, form.max_row + 1)]
    uw_row = labels.index("Uw (window)") + 1
    assert form.cell(uw_row, 4).value == "↑ Uw ≤ 1,4 W/m2.K"
    sources = wb["Sources"]
    assert sources.max_row > 1
    assert {sources.cell(r, 2).value for r in range(2, sources.max_row + 1)} >= {"Uw (window)"}


def test_a_company_form_is_read_from_its_toml_file() -> None:
    from pathlib import Path

    from zelles.recap import load_templates

    (template,) = load_templates(Path(__file__).parents[1] / "docs/recap-template.example.toml")
    assert template.materials == ("pvc",)
    assert [s.title for s in template.sections] == [
        "Joinery",
        "Glazing and performance",
        "Equipment",
    ]
    assert template.rows()[3].fields == (F.COLOR, F.FINISH)
    assert template.rows()[-1].fields == ()  # left for the estimator


def test_the_form_follows_the_material_of_most_items() -> None:
    from zelles.recap import choose_template

    book, _ = _book()  # a PVC window and an aluminium door: a tie goes to the first form
    pvc = RecapTemplate(name="pvc", materials=("pvc",), sections=())
    alu = RecapTemplate(name="alu", materials=("aluminium", "alu"), sections=())
    assert choose_template([pvc, alu], book).name == "pvc"
    assert choose_template([alu, pvc], book).name == "alu"
    book.items[0].values.pop(F.FRAME_MATERIAL)
    assert choose_template([pvc, alu], book).name == "alu"
    assert choose_template([], book) is DEFAULT_TEMPLATE
