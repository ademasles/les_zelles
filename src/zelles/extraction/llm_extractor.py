"""LLM extraction by field group, grounded on retrieved passages."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from zelles.domain.documents import Chunk
from zelles.domain.spec import (
    FIELD_CATALOG,
    Citation,
    Requirement,
    RequirementSource,
    SpecField,
    Usage,
)
from zelles.extraction.prompts import EXTRACTION_SYSTEM, extraction_task, format_passages
from zelles.extraction.verify import mentions_field
from zelles.llm.base import LLM, LLMError, Message
from zelles.retrieval.index import DocumentIndex

log = logging.getLogger(__name__)
F = SpecField

FIELD_GROUPS: dict[str, list[SpecField]] = {
    "materials": [F.FRAME_MATERIAL, F.OPENING_TYPE, F.PROFILE_SYSTEM, F.COLOR, F.FINISH],
    "glazing_thermal": [
        F.GLAZING_COMPOSITION,
        F.GLAZING_TYPE,
        F.SAFETY_GLAZING,
        F.SPACER,
        F.UW,
        F.UG,
        F.UJN,
        F.SW,
        F.TLW,
    ],
    "performance": [F.AEV, F.ACOUSTIC, F.SECURITY_CLASS, F.HARDWARE],
    "equipment": [F.SHUTTERS, F.AIR_INLETS, F.ACCESSIBILITY, F.INSTALLATION],
    "compliance": [F.STANDARDS, F.CERTIFICATIONS, F.REGULATION],
}


def gap_fields(candidates: list[Requirement]) -> set[SpecField]:
    """Fields the rules found nothing for: the only ones worth an LLM call in gap mode."""
    return set(SpecField) - {c.field for c in candidates}


# Below this size the whole document goes into the (cached) system prompt.
WHOLE_DOCUMENT_CHARS = 24_000
MAX_CONTEXT_CHARS = 14_000
# For models with a known context window (local servers): French CCTP text runs
# at about 3.2 characters per token; keep room for the answer and the task.
CHARS_PER_TOKEN = 3
OUTPUT_RESERVE_TOKENS = 2048
TASK_RESERVE_CHARS = 3_000


class ExtractedItem(BaseModel):
    field: str = Field(description="One of the requested field names.")
    value: str
    scope: str | None = None
    chunk_id: str
    quote: str


class ExtractionResult(BaseModel):
    items: list[ExtractedItem] = Field(default_factory=list)


@dataclass
class GroupOutcome:
    group: str
    requirements: list[Requirement]
    usage: Usage
    error: str | None = None


class LLMExtractor:
    def __init__(self, llm: LLM, *, top_k: int = 6, concurrency: int = 2) -> None:
        self.llm = llm
        self.top_k = top_k
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.whole_document_chars = WHOLE_DOCUMENT_CHARS
        self.max_context_chars = MAX_CONTEXT_CHARS
        context_tokens: int | None = getattr(llm, "context_tokens", None)
        if context_tokens:
            room = (context_tokens - OUTPUT_RESERVE_TOKENS) * CHARS_PER_TOKEN
            room -= len(EXTRACTION_SYSTEM) + TASK_RESERVE_CHARS
            self.whole_document_chars = min(WHOLE_DOCUMENT_CHARS, room)
            self.max_context_chars = max(2_000, min(MAX_CONTEXT_CHARS, room))

    async def extract(
        self,
        index: DocumentIndex,
        candidates: list[Requirement],
        *,
        only: set[SpecField] | None = None,
    ) -> list[GroupOutcome]:
        """Run one call per field group; ``only`` restricts the fields asked for."""
        groups = {
            name: [f for f in fields if only is None or f in only]
            for name, fields in FIELD_GROUPS.items()
        }
        total_chars = sum(len(c.text) for c in index.chunks)
        whole = total_chars <= self.whole_document_chars
        system = EXTRACTION_SYSTEM
        if whole:  # identical prefix for every group: providers can cache it
            system += "\n\nSOURCE DOCUMENT\n\n" + format_passages(index.chunks)
        tasks = [
            self._run_group(name, fields, index, candidates, system=system, whole=whole)
            for name, fields in groups.items()
            if fields
        ]
        return list(await asyncio.gather(*tasks))

    async def _run_group(
        self,
        name: str,
        fields: list[SpecField],
        index: DocumentIndex,
        candidates: list[Requirement],
        *,
        system: str,
        whole: bool,
    ) -> GroupOutcome:
        group_candidates = [c for c in candidates if c.field in fields]
        prompt = extraction_task(fields, group_candidates)
        if not whole:
            passages = await self._passages(fields, index, group_candidates)
            prompt = f"PASSAGES\n\n{format_passages(passages)}\n\n{prompt}"
        async with self.semaphore:
            try:
                result = await self.llm.complete(
                    system=system,
                    messages=[Message("user", prompt)],
                    schema=ExtractionResult,
                )
            except LLMError as exc:
                log.warning("group %s failed: %s", name, exc)
                return GroupOutcome(name, [], Usage(), str(exc))
        allowed = {f.value for f in fields}
        requirements: list[Requirement] = []
        parsed = result.parsed or ExtractionResult()
        for item in parsed.items:
            if item.field not in allowed or not item.value.strip():
                continue
            if not mentions_field(SpecField(item.field), f"{item.quote} {item.scope or ''}"):
                log.debug("dropped %s = %r: quote is about another topic", item.field, item.value)
                continue
            requirements.append(
                Requirement(
                    field=SpecField(item.field),
                    value=item.value.strip(),
                    scope=(item.scope or None),
                    unit=FIELD_CATALOG[SpecField(item.field)].unit,
                    citation=Citation(chunk_id=item.chunk_id.strip("[] "), quote=item.quote),
                    source=RequirementSource.LLM,
                    confidence=0.7,
                )
            )
        return GroupOutcome(name, requirements, result.usage)

    async def _passages(
        self, fields: list[SpecField], index: DocumentIndex, candidates: list[Requirement]
    ) -> list[Chunk]:
        query = " ".join(term for f in fields for term in FIELD_CATALOG[f].search_terms)
        hits = await index.search(query, k=self.top_k)
        by_id = {c.id: c for c in index.chunks}
        chosen: dict[str, Chunk] = {h.chunk.id: h.chunk for h in hits}
        for cand in candidates:  # always show the model where the rules found something
            if cand.citation and cand.citation.chunk_id in by_id:
                chosen.setdefault(cand.citation.chunk_id, by_id[cand.citation.chunk_id])
        ordered = sorted(chosen.values(), key=lambda c: c.index)
        out: list[Chunk] = []
        size = 0
        for chunk in ordered:
            if size + len(chunk.text) > self.max_context_chars and out:
                break
            out.append(chunk)
            size += len(chunk.text)
        return out
