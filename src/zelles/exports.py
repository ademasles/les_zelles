"""Exports of a spec sheet: JSON, CSV and Excel (for quoting tools)."""

from __future__ import annotations

import csv
import io

from zelles.domain.spec import FIELD_CATALOG, SpecSheet

COLUMNS = [
    "category",
    "field",
    "label",
    "value",
    "numeric_value",
    "unit",
    "comparator",
    "scope",
    "status",
    "confidence",
    "source",
    "page",
    "location",
    "quote",
]


def rows(sheet: SpecSheet) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for req in sheet.requirements:
        info = FIELD_CATALOG[req.field]
        out.append(
            {
                "category": info.category.value,
                "field": req.field.value,
                "label": info.label,
                "value": req.value,
                "numeric_value": req.numeric_value,
                "unit": req.unit,
                "comparator": req.comparator,
                "scope": req.scope,
                "status": req.status.value,
                "confidence": round(req.confidence, 2),
                "source": req.source.value,
                "page": req.citation.page if req.citation else None,
                "location": req.citation.locator if req.citation else None,
                "quote": req.citation.quote if req.citation else None,
            }
        )
    return out


def to_csv(sheet: SpecSheet) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows(sheet))
    return buffer.getvalue()


def to_xlsx(sheet: SpecSheet) -> bytes:
    from openpyxl import Workbook  # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415

    wb = Workbook()
    ws = wb.active
    ws.title = "Spec sheet"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F4858")
    fills = {"verified": "E3F2E1", "unverified": "FFF4D6", "invalid": "FBE3E1"}
    for row in rows(sheet):
        ws.append([row[c] for c in COLUMNS])
        fill = fills.get(str(row["status"]))
        if fill:
            ws.cell(ws.max_row, COLUMNS.index("status") + 1).fill = PatternFill(
                "solid", fgColor=fill
            )
    widths = {"value": 40, "scope": 36, "location": 40, "quote": 80, "label": 24}
    for index, name in enumerate(COLUMNS, start=1):
        ws.column_dimensions[ws.cell(1, index).column_letter].width = widths.get(name, 14)
    for row_cells in ws.iter_rows(min_row=2):
        for cell in row_cells:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"

    info = wb.create_sheet("About")
    info.append(["Document", sheet.filename])
    info.append(["Document id", sheet.document_id])
    info.append(["Model", sheet.model])
    info.append(["Generated", sheet.generated_at.isoformat()])
    info.append(["Lots", ", ".join(sheet.lots)])
    info.append(["LLM calls", sheet.usage.calls])
    info.append(["Estimated cost (USD)", sheet.usage.cost_usd])
    if sheet.summary:
        info.append(["Summary", sheet.summary])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
