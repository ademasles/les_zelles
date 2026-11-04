"""Prompts. Written in English; the model is told to keep source values in French."""

from __future__ import annotations

from zelles.domain.documents import Chunk
from zelles.domain.spec import FIELD_CATALOG, Requirement, SpecField

EXTRACTION_SYSTEM = """\
You are a senior estimator for PVC, aluminium and wood joinery in France. You read \
CCTPs (Cahier des Clauses Techniques Particulières) and turn them into a spec sheet \
used to price and select products.

Rules:
- Extract only requirements explicitly stated in the source. Never infer, never fill \
gaps from general knowledge or from what is usual.
- `quote` must be copied verbatim from the source, in French, character for character: \
the shortest sentence or clause that states the value. It is checked automatically.
- `chunk_id` is the id in square brackets of the passage the quote comes from.
- `value` is concise, in the source language, with unit and comparator when stated \
(for example "≤ 1,3 W/m².K", "A*3 E*7B V*A2", "blanc RAL 9016").
- `scope` says what the requirement applies to (a lot, a building, an opening type, \
a facade), taken from the sentence or else from the section heading.
- When a field has different values for different scopes, return one item per scope.
- When the source says nothing about a field, return no item for it.
"""

QA_SYSTEM = """\
You answer questions about a French construction tender specification (CCTP) for \
joinery. Answer only from the passages provided. Cite every claim with the passage \
id and a verbatim quote in French. If the passages do not contain the answer, set \
`found` to false and say what is missing. Answer in the language of the question.
"""

SUMMARY_SYSTEM = """\
You write short briefs for joinery estimators. Use only the requirements given. \
Write 4 to 6 bullet points in English: scope of work, materials, key performances, \
notable constraints or risks for pricing. No preamble.
"""


def format_passages(chunks: list[Chunk]) -> str:
    parts = []
    for chunk in chunks:
        header = f"[{chunk.id}] {chunk.locator()}".rstrip()
        parts.append(f"{header}\n{chunk.text}")
    return "\n\n---\n\n".join(parts)


def extraction_task(fields: list[SpecField], candidates: list[Requirement]) -> str:
    lines = ["Extract the following fields:"]
    for field in fields:
        info = FIELD_CATALOG[field]
        unit = f" (unit: {info.unit})" if info.unit else ""
        lines.append(f"- {field.value}: {info.description}{unit}")
    if candidates:
        lines.append(
            "\nA pattern matcher already found these candidates. They may be incomplete, "
            "mis-scoped or wrong: confirm them, fix their scope, and add what they miss."
        )
        for req in candidates:
            where = f" [{req.citation.chunk_id}]" if req.citation else ""
            lines.append(f"- {req.field.value}: {req.value}{where}")
    return "\n".join(lines)
