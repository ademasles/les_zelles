"""The drafted récapitulatif technique: a tender's joinery items, row by row, each value cited.

An estimator fills one recap per tender: a fixed list of rows (frame, glazing, Uw,
hardware...) read off the CCTP for every item. The draft lays the item book out on
those rows, one column per item, and gives the page of every value so each line can
be checked against the source. Rows the tender does not answer stay empty; values no
row takes are listed at the end, so nothing extracted is dropped silently.
"""

from __future__ import annotations

import io
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from zelles.domain.documents import Chunk
from zelles.domain.items import ItemBook, ItemKind, JoineryItem, build_items
from zelles.domain.spec import FIELD_CATALOG, Category, Requirement, SpecField, SpecSheet
from zelles.retrieval.text import comparable

_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


class RecapRow(BaseModel, frozen=True):
    label: str
    fields: tuple[SpecField, ...] = ()


class RecapSection(BaseModel, frozen=True):
    title: str
    rows: tuple[RecapRow, ...]


class RecapTemplate(BaseModel, frozen=True):
    """The rows of a recap form, in printed order, and the fields each row takes."""

    name: str
    materials: tuple[str, ...] = Field(
        default=(), description="Frame materials the form is for: ('pvc',) or ('aluminium', 'alu')."
    )
    sections: tuple[RecapSection, ...]

    def rows(self) -> list[RecapRow]:
        return [row for section in self.sections for row in section.rows]

    def fields(self) -> set[SpecField]:
        return {f for row in self.rows() for f in row.fields}


_SECTION_TITLES = {
    Category.MATERIALS: "Materials and finishes",
    Category.GLAZING: "Glazing",
    Category.THERMAL: "Thermal and solar",
    Category.WEATHER: "Weather tightness",
    Category.ACOUSTICS: "Acoustics",
    Category.SECURITY: "Security and hardware",
    Category.EQUIPMENT: "Equipment",
    Category.ACCESSIBILITY: "Accessibility",
    Category.INSTALLATION: "Installation",
    Category.COMPLIANCE: "Compliance",
}

# One row per field of the catalogue, grouped by category: the form until a company's
# own recap template is set.
DEFAULT_TEMPLATE = RecapTemplate(
    name="default",
    sections=tuple(
        RecapSection(
            title=title,
            rows=tuple(
                RecapRow(label=info.label, fields=(info.field,))
                for info in FIELD_CATALOG.values()
                if info.category == category
            ),
        )
        for category, title in _SECTION_TITLES.items()
    ),
)


def load_templates(path: Path) -> list[RecapTemplate]:
    """A company's recap forms, read from TOML files kept with its data, not in the code.

    ``path`` is one file or a folder of them. A file lists sections in printed order,
    each with its rows and the fields a row takes; see docs/recap-template.example.toml.
    """
    files = sorted(path.glob("*.toml")) if path.is_dir() else [path]
    return [
        RecapTemplate.model_validate(tomllib.loads(f.read_text(encoding="utf-8"))) for f in files
    ]


def choose_template(templates: Sequence[RecapTemplate], book: ItemBook) -> RecapTemplate:
    """The form for the material most items are made of (a PVC form, an aluminium form).

    Items vote with the material stated under their own heading; a general clause
    ("tablier de volet en PVC") only counts when no item states one.
    """
    if not templates:
        return DEFAULT_TEMPLATE
    own = [comparable(r.value) for i in book.items for r in i.own(SpecField.FRAME_MATERIAL)]
    materials = own or [
        comparable(v.requirement.value)
        for item in book.items
        for v in item.values.get(SpecField.FRAME_MATERIAL, [])
    ]

    def votes(template: RecapTemplate) -> int:
        words = [comparable(m) for m in template.materials]
        return sum(any(re.search(rf"\b{re.escape(w)}", m) for w in words) for m in materials)

    return max(templates, key=votes)  # the first form wins a tie


KIND_LABELS = {
    ItemKind.WINDOW: "Window",
    ItemKind.DOOR: "Door",
    ItemKind.FACADE: "Glazed facade",
    ItemKind.SHUTTER: "Shutter",
}


class RecapValue(BaseModel):
    value: str
    page: int | None = None
    inherited: bool = Field(
        default=False, description="Read in a general clause of the item's chapter."
    )
    quote: str = ""

    def line(self) -> str:
        page = f" (p. {self.page})" if self.page is not None else ""
        return f"{'↑ ' if self.inherited else ''}{self.value}{page}"


class RecapColumn(BaseModel):
    """One column of the recap: the general clauses, or one item."""

    title: str
    group: str | None = None
    codes: list[str] = Field(default_factory=list)
    kind: ItemKind | None = None
    cells: list[list[RecapValue]] = Field(
        default_factory=list, description="One cell per template row, in row order."
    )


class Recap(BaseModel):
    filename: str
    template: RecapTemplate
    columns: list[RecapColumn]
    accessories: dict[str, list[tuple[SpecField, RecapValue]]] = Field(default_factory=dict)
    outside: dict[str, list[tuple[SpecField, RecapValue]]] = Field(default_factory=dict)


def _value(req: Requirement, *, inherited: bool = False) -> RecapValue:
    citation = req.citation
    return RecapValue(
        value=req.value,
        page=citation.page if citation else None,
        inherited=inherited,
        quote=citation.quote if citation else "",
    )


def _distinct(values: list[RecapValue]) -> list[RecapValue]:
    """One line per value, the item's own statement first.

    A value already said by a longer one in the same cell is left out:
    "remplissage argon" beside "double vitrage 4/16/4 à remplissage argon".
    """
    out: list[tuple[str, RecapValue]] = []
    for value in sorted(values, key=lambda v: (v.inherited, -len(v.value))):
        key = comparable(value.value)
        if not any(re.search(rf"(?<!\S){re.escape(key)}(?!\S)", kept) for kept, _ in out):
            out.append((key, value))
    return [value for _, value in out]


def _item_values(item: JoineryItem) -> dict[SpecField, list[RecapValue]]:
    return {
        field: [_value(v.requirement, inherited=v.inherited) for v in values]
        for field, values in item.values.items()
    }


def _column(
    title: str, values: dict[SpecField, list[RecapValue]], template: RecapTemplate
) -> RecapColumn:
    return RecapColumn(
        title=title,
        cells=[
            _distinct([v for f in row.fields for v in values.get(f, [])]) for row in template.rows()
        ],
    )


OTHER_VALUES = "Other values (no row of this form takes them)"


def draft_recap(
    book: ItemBook, *, filename: str, template: RecapTemplate = DEFAULT_TEMPLATE
) -> Recap:
    """Lay an item book out on a recap form: general clauses first, then one column per item.

    Fields that no row of the form takes get rows of their own in a last section, so each
    value stays in its item's column.
    """
    general = {f: [_value(r) for r in reqs] for f, reqs in book.general.items()}
    item_values = [_item_values(item) for item in book.items]
    taken = template.fields()
    left = {f for values in [general, *item_values] for f in values if f not in taken}
    if left:
        rows = tuple(
            RecapRow(label=info.label, fields=(f,))
            for f, info in FIELD_CATALOG.items()
            if f in left
        )
        template = template.model_copy(
            update={"sections": (*template.sections, RecapSection(title=OTHER_VALUES, rows=rows))}
        )
    columns = [_column("General clauses", general, template)]
    for item, values in zip(book.items, item_values, strict=True):
        column = _column(item.name, values, template)
        column.group, column.codes, column.kind = item.group, item.codes, item.kind
        columns.append(column)
    return Recap(
        filename=filename,
        template=template,
        columns=columns,
        accessories={
            heading: [(r.field, _value(r)) for r in reqs]
            for heading, reqs in book.accessories.items()
        },
        outside={
            heading: [(r.field, _value(r)) for r in reqs] for heading, reqs in book.outside.items()
        },
    )


def recap_workbook(
    sheet: SpecSheet, chunks: Sequence[Chunk], templates: Sequence[RecapTemplate] = ()
) -> bytes:
    """The recap workbook of an analysed document, on the form that fits its items."""
    book = build_items(sheet, chunks)
    template = choose_template(templates, book)
    return recap_to_xlsx(draft_recap(book, filename=sheet.filename, template=template))


def _safe(value: object) -> object:
    """Excel cells cannot hold control characters or non-characters such as U+FFFE."""
    return _ILLEGAL_XML.sub("", value) if isinstance(value, str) else value


def recap_to_xlsx(recap: Recap) -> bytes:
    """The recap as a workbook: the form, every value with its quote, and what no item took."""
    from openpyxl import Workbook  # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415

    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2F4858")
    section_fill = PatternFill("solid", fgColor="DDE6EA")
    top = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()
    ws = wb.active
    ws.title = "Recap"
    ws.append([_safe(f"Technical recap (draft) - {recap.filename}")])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["↑ read in a general clause of the item's chapter, not under the item itself"])
    ws["A2"].font = Font(italic=True, color="666666")
    ws.append(["", *(_safe(c.title) for c in recap.columns)])
    ws.append(["Type", *(KIND_LABELS[c.kind] if c.kind else "" for c in recap.columns)])
    ws.append(["Marks", *(", ".join(c.codes) for c in recap.columns)])
    ws.append(["Chapter", *(_safe(c.group or "") for c in recap.columns)])
    for row in ws.iter_rows(min_row=3, max_row=6):
        for cell in row:
            cell.font, cell.fill, cell.alignment = head_font, head_fill, top
    index = 0
    for section in recap.template.sections:
        ws.append([_safe(section.title)])
        for cell in ws[ws.max_row][: len(recap.columns) + 1]:
            cell.font, cell.fill = Font(bold=True), section_fill
        for row in section.rows:
            lines = ["\n".join(v.line() for v in c.cells[index]) for c in recap.columns]
            ws.append([_safe(row.label), *(_safe(t) for t in lines)])
            index += 1
    for row in ws.iter_rows(min_row=7):
        for cell in row:
            cell.alignment = top
    ws.column_dimensions["A"].width = 30
    for col in range(2, len(recap.columns) + 2):
        ws.column_dimensions[ws.cell(3, col).column_letter].width = 36
    ws.freeze_panes = "B7"

    sources = wb.create_sheet("Sources")
    sources.append(["Column", "Row", "Value", "Page", "Inherited", "Quote"])
    rows = recap.template.rows()
    for column in recap.columns:
        for row, cell in zip(rows, column.cells, strict=True):
            for v in cell:
                sources.append(
                    [_safe(column.title), _safe(row.label), _safe(v.value), v.page,
                     "yes" if v.inherited else "", _safe(v.quote)]
                )  # fmt: skip
    _header(sources, head_font, head_fill, {"A": 30, "B": 28, "C": 40, "F": 90})

    other = wb.create_sheet("Not on an item")
    other.append(["Where", "Article", "Field", "Value", "Page", "Quote"])
    for where, groups in (("Accessory", recap.accessories), ("Other trade", recap.outside)):
        for heading, found in groups.items():
            for spec, value in found:
                other.append(
                    [where, _safe(heading), FIELD_CATALOG[spec].label, _safe(value.value),
                     value.page, _safe(value.quote)]
                )  # fmt: skip
    _header(other, head_font, head_fill, {"B": 36, "C": 24, "D": 40, "F": 90})

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _header(ws: object, font: object, fill: object, widths: dict[str, int]) -> None:
    from openpyxl.styles import Alignment  # noqa: PLC0415
    from openpyxl.worksheet.worksheet import Worksheet  # noqa: PLC0415

    assert isinstance(ws, Worksheet)
    for cell in ws[1]:
        cell.font, cell.fill = font, fill
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for column, width in widths.items():
        ws.column_dimensions[column].width = width
    ws.freeze_panes = "A2"
