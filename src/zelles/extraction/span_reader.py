"""Read the free-text fields article by article with a local extraction model.

Rules are near-perfect on codes and numbers but weak on prose: hardware parts,
shutter descriptions, installation methods. A small extraction model
(NuExtract 2.0 through Ollama) reads one article at a time against a JSON
template and returns spans copied from the text. A span the article does not
contain is dropped, so the reader can miss a value but cannot invent one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from zelles.domain.documents import Chunk
from zelles.domain.spec import (
    FIELD_CATALOG,
    Citation,
    Requirement,
    RequirementSource,
    RequirementStatus,
    SpecField,
    Usage,
)
from zelles.extraction.rules import describes_existing, sentences
from zelles.extraction.verify import mentions_field
from zelles.ingest.cleaning import normalize_for_match
from zelles.llm.base import LLM, Completion, LLMError, Message

log = logging.getLogger(__name__)
F = SpecField

# Template keys say what to copy; the model reads the key, so it carries the guide's rule.
READER_FIELDS: dict[str, SpecField] = {
    "hardware parts with their model (crémone, paumelle, serrure, ferme-porte, poignée)": (
        F.HARDWARE
    ),
    "shutters, blinds and sun protection with their box and drive": F.SHUTTERS,
    "installation method (pose en applique, en tunnel, en rénovation, dépose)": F.INSTALLATION,
    "finish of the frames (thermolaqué, anodisé, plaxé, lasure, wood species)": F.FINISH,
    "named profile range or system": F.PROFILE_SYSTEM,
    "regulations and heritage constraints (RE2020, ERP, ABF)": F.REGULATION,
    "glazing type (double vitrage, faible émissivité, argon, contrôle solaire)": F.GLAZING_TYPE,
    "safety glazing (feuilleté, trempé, 44.2, SP10, P2A)": F.SAFETY_GLAZING,
    "accessibility requirements (PMR thresholds, handle heights)": F.ACCESSIBILITY,
    "opening types (oscillo-battant, coulissant, châssis fixe, porte à 2 vantaux)": (
        F.OPENING_TYPE
    ),
    "air inlets (entrées d'air, débit, hygroréglable)": F.AIR_INLETS,
}
TEMPLATE = json.dumps({key: ["verbatim-string"] for key in READER_FIELDS}, ensure_ascii=False)

_JSON = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class ReaderOutcome:
    requirements: list[Requirement]
    usage: Usage = field(default_factory=Usage)
    articles_read: int = 0
    errors: list[str] = field(default_factory=list)


def worth_reading(chunk: Chunk) -> bool:
    """Skip articles that use none of the fields' vocabulary: most of a CCTP is site logistics."""
    return any(mentions_field(f, chunk.text) for f in READER_FIELDS.values())


def prompt_for(chunk: Chunk) -> str:
    """NuExtract's input: the template, then the text."""
    return f"# Template:\n{TEMPLATE}\n# Context:\n{chunk.text}"


def parse_reply(text: str) -> dict[str, list[str]]:
    """The model's JSON, keeping only template keys and string values."""
    found = _JSON.search(text)
    if not found:
        return {}
    try:
        data = json.loads(found.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, values in data.items():
        if key not in READER_FIELDS:
            continue
        items = values if isinstance(values, list) else [values]
        out[key] = [v.strip() for v in items if isinstance(v, str) and v.strip()]
    return out


def _sentence_with(text: str, span: str) -> str:
    folded = normalize_for_match(span)
    for start, end in sentences(text):
        sentence = text[start:end].strip()
        if folded in normalize_for_match(sentence):
            return sentence
    return span


def spans_to_requirements(chunk: Chunk, reply: dict[str, list[str]]) -> list[Requirement]:
    """Keep the spans the article really contains, one requirement each."""
    body = normalize_for_match(chunk.text)
    seen: set[tuple[SpecField, str]] = set()
    out: list[Requirement] = []
    for key, values in reply.items():
        spec_field = READER_FIELDS[key]
        for value in values:
            folded = normalize_for_match(value)
            if len(folded) < 2 or folded not in body or (spec_field, folded) in seen:
                continue
            seen.add((spec_field, folded))
            out.append(
                Requirement(
                    field=spec_field,
                    value=" ".join(value.split()),
                    unit=FIELD_CATALOG[spec_field].unit,
                    scope=chunk.scope,
                    citation=Citation(
                        chunk_id=chunk.id,
                        quote=_sentence_with(chunk.text, value),
                        locator=chunk.locator(),
                        match_score=1.0,
                    ),
                    source=RequirementSource.LLM,
                    status=RequirementStatus.VERIFIED,
                    confidence=0.7,
                )
            )
    return out


class SpanReader:
    def __init__(self, llm: LLM, *, concurrency: int = 1, max_tokens: int = 1024) -> None:
        self.llm = llm
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.max_tokens = max_tokens

    async def read(self, chunks: list[Chunk]) -> ReaderOutcome:
        chosen = [c for c in chunks if not describes_existing(c) and worth_reading(c)]
        outcome = ReaderOutcome(requirements=[], articles_read=len(chosen))
        results = await asyncio.gather(*(self._read_one(c, outcome) for c in chosen))
        seen: set[tuple[str, str]] = set()
        for reqs in results:
            for req in reqs:
                key = (req.field.value, normalize_for_match(req.value))
                if key not in seen:  # once per tender, as the answer keys list values
                    seen.add(key)
                    outcome.requirements.append(req)
        return outcome

    async def _read_one(self, chunk: Chunk, outcome: ReaderOutcome) -> list[Requirement]:
        async with self.semaphore:
            try:
                reply: Completion[BaseModel] = await self.llm.complete(
                    system="",
                    messages=[Message("user", prompt_for(chunk))],
                    max_tokens=self.max_tokens,
                )
            except LLMError as exc:
                log.warning("article %s failed: %s", chunk.id, exc)
                outcome.errors.append(f"{chunk.id}: {exc}")
                return []
        outcome.usage.add(reply.usage)
        return spans_to_requirements(chunk, parse_reply(reply.text))
