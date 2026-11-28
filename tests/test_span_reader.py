"""The article reader on synthetic CCTP text, with a fake extraction model."""

from __future__ import annotations

import json
from typing import Any

from zelles.config import Settings
from zelles.domain.spec import Requirement, SpecField
from zelles.extraction.span_reader import (
    READER_FIELDS,
    SpanReader,
    combine_with_rules,
    parse_reply,
    worth_reading,
)
from zelles.ingest.chunking import chunk_document
from zelles.ingest.parsers import parse_document
from zelles.llm.base import Message
from zelles.llm.fake import FakeLLM
from zelles.pipeline import analyze

F = SpecField
KEY = {field: key for key, field in READER_FIELDS.items()}

CCTP = """# 3 Menuiseries extérieures

## 3.1 Quincaillerie

Les fenêtres seront équipées d'une crémone pompier Vachette laquée blanc et de paumelles
renforcées. Uw ≤ 1,3 W/m².K.

## 3.2 Installation de chantier

La base vie sera installée près du portail.
"""


def _chunks() -> list[Any]:
    document, _ = parse_document(CCTP.encode(), "cctp.md")
    return chunk_document(document)


def _reply(_system: str, messages: list[Message], _schema: Any) -> str:
    text = messages[-1].content
    out: dict[str, list[str]] = {key: [] for key in READER_FIELDS}
    if "crémone" in text:
        out[KEY[F.HARDWARE]] = ["crémone pompier Vachette", "paumelles renforcées", "gâche"]
    return "Here is the result:\n" + json.dumps(out, ensure_ascii=False)


def test_parse_reply_keeps_template_keys_and_strings() -> None:
    key = KEY[F.AIR_INLETS]
    raw = json.dumps({key: ["entrées d'air", 3, " "], "other": ["x"]}, ensure_ascii=False)
    reply = parse_reply(f"noise {raw} end")
    assert reply == {key: ["entrées d'air"]}
    assert parse_reply("no json here") == {}


def test_only_articles_with_field_vocabulary_are_read() -> None:
    chunks = _chunks()
    read = [c for c in chunks if worth_reading(c)]
    assert any("crémone" in c.text for c in read)
    assert not any("base vie" in c.text for c in read)


async def test_spans_missing_from_the_article_are_dropped() -> None:
    llm = FakeLLM(_reply)
    outcome = await SpanReader(llm).read(_chunks())
    values = {r.value for r in outcome.requirements if r.field == F.HARDWARE}
    assert values == {"crémone pompier Vachette", "paumelles renforcées"}  # no "gâche"
    assert all(r.citation and "crémone" in r.citation.quote for r in outcome.requirements)
    assert all(system == "" for system, _ in llm.calls)  # no system prompt for NuExtract


async def test_article_mode_keeps_rule_values_the_reader_does_not_restate() -> None:
    settings = Settings(llm_reader="articles", joinery_focus=False)
    analysis = await analyze(
        CCTP.encode(), "cctp.md", settings=settings, llm=FakeLLM(_reply), summarize=True
    )
    reqs = analysis.sheet.requirements
    hardware = {r.value for r in reqs if r.field == F.HARDWARE}
    assert {"crémone pompier Vachette", "paumelles renforcées"} <= hardware
    assert not any(v.lower() in {"crémone", "crémone pompier"} for v in hardware), hardware
    assert any(r.field == F.UW and r.numeric_value == 1.3 for r in reqs)  # rules keep codes
    assert analysis.sheet.summary is None  # an extraction model writes no brief


def test_combine_keeps_rule_values_no_span_restates() -> None:
    def req(field: SpecField, value: str) -> Requirement:
        return Requirement(field=field, value=value)

    rules = [req(F.HARDWARE, "crémone"), req(F.HARDWARE, "paumelles"), req(F.SHUTTERS, "volet")]
    read = [req(F.HARDWARE, "crémone pompier Vachette")]
    combined = {r.value for r in combine_with_rules(rules, read)}
    assert combined == {"crémone pompier Vachette", "paumelles", "volet"}


def test_spans_from_contents_reference_lines_or_wrong_items_are_dropped() -> None:
    from zelles.extraction.span_reader import spans_to_requirements

    text = (
        "# 3 Menuiseries\n\n## 3.1 Généralités\n\n"
        "Ferme-porte hydraulique, finition anodisé noir.\n\n"
        "NF P 78-201 Verre feuilleté de sécurité\n\n"
        "Profilés thermolaqués RAL 7016.\n\n"
        "Exutoire de désenfumage CAST-PMR.\n"
    )
    document, _ = parse_document(text.encode(), "cctp.md")
    chunk = next(c for c in chunk_document(document) if "Ferme-porte" in c.text)
    reply = {
        KEY[F.FINISH]: ["anodisé noir", "thermolaqués"],
        KEY[F.SAFETY_GLAZING]: ["Verre feuilleté"],
        KEY[F.ACCESSIBILITY]: ["CAST-PMR"],
    }
    kept = {(r.field, r.value) for r in spans_to_requirements(chunk, reply)}
    assert kept == {(F.FINISH, "thermolaqués")}
