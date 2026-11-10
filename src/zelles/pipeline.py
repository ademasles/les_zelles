"""End-to-end analysis: parse -> chunk -> index -> rules -> LLM -> verify -> merge -> graph.

The pipeline is the same for the API, the CLI, the MCP server and the eval
harness. It never needs a GPU and works with no LLM at all (rules only).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from zelles.config import Settings
from zelles.domain.documents import Chunk, ParsedDocument
from zelles.domain.spec import (
    FIELD_CATALOG,
    Requirement,
    RequirementStatus,
    SpecSheet,
    Usage,
)
from zelles.extraction.dedupe import merge_near_duplicates
from zelles.extraction.llm_extractor import LLMExtractor
from zelles.extraction.merge import merge_requirements
from zelles.extraction.prompts import SUMMARY_SYSTEM
from zelles.extraction.rules import extract_with_rules
from zelles.extraction.verify import verify_requirement
from zelles.graph.knowledge import KnowledgeGraph, build_graph
from zelles.ingest.chunking import chunk_document
from zelles.ingest.parsers import parse_document
from zelles.ingest.title import detect_title
from zelles.llm.base import LLM, Completion, Embedder, LLMError, Message
from zelles.retrieval.index import DocumentIndex

log = logging.getLogger(__name__)

Progress = Callable[[str, float, str], Awaitable[None]]


async def _no_progress(stage: str, fraction: float, message: str) -> None:
    return None


@dataclass
class Analysis:
    document_id: str
    document: ParsedDocument
    chunks: list[Chunk]
    index: DocumentIndex
    sheet: SpecSheet
    graph: KnowledgeGraph
    rendition_pdf: bytes | None = None
    timings: dict[str, float] = field(default_factory=dict)


def document_id_for(data: bytes) -> str:
    """Content-addressed id: the same file always gets the same id (free caching)."""
    return hashlib.sha256(data).hexdigest()[:16]


async def analyze(
    data: bytes,
    filename: str,
    *,
    settings: Settings,
    llm: LLM | None = None,
    embedder: Embedder | None = None,
    progress: Progress = _no_progress,
    summarize: bool = True,
) -> Analysis:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    doc_id = document_id_for(data)

    await progress("parse", 0.05, "Reading the document")
    document, rendition = await asyncio.to_thread(
        parse_document,
        data,
        filename,
        parser=settings.parser,
        ocr=settings.ocr_enabled,
        ocr_language=settings.ocr_language,
    )
    timings["parse"] = time.perf_counter() - t0

    await progress(
        "chunk", 0.2, f"Splitting {document.page_count or 'unpaginated'} pages by article"
    )
    chunks = chunk_document(document, max_chars=settings.chunk_max_chars)
    if not chunks:
        raise ValueError("no text could be extracted from the document")

    await progress("index", 0.3, f"Indexing {len(chunks)} passages")
    t = time.perf_counter()
    index = await DocumentIndex.build(chunks, embedder)
    timings["index"] = time.perf_counter() - t

    await progress("rules", 0.4, "Extracting values with domain rules")
    rule_reqs = extract_with_rules(chunks)

    usage = Usage(cost_usd=0.0 if llm is None else None)
    warnings = list(document.warnings)
    llm_reqs: list[Requirement] = []
    if llm is not None:
        await progress("llm", 0.5, f"Reading the specification with {llm.name}")
        t = time.perf_counter()
        extractor = LLMExtractor(
            llm, top_k=settings.retrieval_top_k, concurrency=settings.llm_concurrency
        )
        for outcome in await extractor.extract(index, rule_reqs):
            usage.add(outcome.usage)
            llm_reqs.extend(outcome.requirements)
            if outcome.error:
                warnings.append(f"LLM group '{outcome.group}' failed: {outcome.error}")
        timings["llm"] = time.perf_counter() - t

    await progress("verify", 0.85, "Checking every value against the source")
    by_id = {c.id: c for c in chunks}
    verified = [verify_requirement(r, by_id) for r in llm_reqs]
    requirements = merge_near_duplicates(merge_requirements(rule_reqs, verified))

    sheet = SpecSheet(
        document_id=doc_id,
        filename=filename,
        title=detect_title(document),
        model=llm.name if llm else "rules",
        lots=sorted({c.lot for c in chunks if c.lot}),
        requirements=requirements,
        usage=usage,
        warnings=warnings,
    )

    if llm is not None and summarize and requirements:
        await progress("summary", 0.92, "Writing the estimator brief")
        sheet.summary = await _summarize(llm, sheet, usage)

    graph = build_graph(sheet, chunks)
    timings["total"] = time.perf_counter() - t0
    sheet.usage.seconds = timings["total"]
    await progress("done", 1.0, f"{len(requirements)} requirements extracted")
    return Analysis(doc_id, document, chunks, index, sheet, graph, rendition, timings)


async def _summarize(llm: LLM, sheet: SpecSheet, usage: Usage) -> str | None:
    lines = [
        f"- {FIELD_CATALOG[r.field].label}: {r.value}" + (f" ({r.scope})" if r.scope else "")
        for r in sheet.requirements
        if r.status == RequirementStatus.VERIFIED
    ]
    try:
        result: Completion[Any] = await llm.complete(
            system=SUMMARY_SYSTEM,
            messages=[Message("user", "Requirements:\n" + "\n".join(lines[:120]))],
            max_tokens=600,
        )
    except LLMError as exc:
        log.warning("summary failed: %s", exc)
        return None
    usage.add(result.usage)
    return result.text.strip() or None
