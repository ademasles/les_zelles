"""RAG service — orchestrates retrieval, prompt building, LLM, and citation persistence."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.llm.base import LLMClient
from app.rag.prompts import build_qa_prompt
from app.rag.retriever import Retriever

logger = logging.getLogger(__name__)


def _assess_evidence_quality(results: list, answer_text: str | None) -> str:
    if not results:
        return "none"
    if answer_text and "ne trouve pas" in answer_text.lower():
        return "none"
    top_score = results[0].score if results else 0
    if top_score > 0.85 and len(results) >= 2:
        return "strong"
    if top_score > 0.6:
        return "medium"
    return "weak"


def build_evidence_text(results: list) -> str:
    parts = []
    for r in results:
        meta = r.metadata or {}
        section = meta.get("section_title", "")
        page = meta.get("page_start", "")
        header = f"[Section: {section}" + (f", Page: {page}" if page else "") + "]"
        parts.append(f"{header}\n{r.text}")
    return "\n\n---\n\n".join(parts) if parts else ""


async def answer_question(
    question: str,
    retriever: Retriever,
    llm: LLMClient,
    project_id: str | None = None,
    document_id: str | None = None,
) -> dict[str, Any]:
    filters = {}
    if document_id:
        filters["document_id"] = document_id
    if project_id:
        filters["project_id"] = project_id

    start = time.perf_counter()
    results = retriever.retrieve(question, top_k=5, filters=filters)
    evidence = build_evidence_text(results)

    prompt, prompt_version = build_qa_prompt(question, evidence)
    answer_text = llm.generate(prompt)
    latency_ms = int((time.perf_counter() - start) * 1000)

    citations = []
    for r in results:
        meta = r.metadata or {}
        citations.append({
            "document_id": meta.get("document_id", ""),
            "document_name": meta.get("document_name", ""),
            "chunk_id": r.chunk_id,
            "page_start": meta.get("page_start"),
            "page_end": meta.get("page_end"),
            "section_title": meta.get("section_title", ""),
            "quote": r.text[:500] if r.text else "",
            "score": r.score,
        })

    return {
        "answer": answer_text,
        "citations": citations,
        "evidence_quality": _assess_evidence_quality(results, answer_text),
        "model_name": getattr(llm, "model", "unknown"),
        "prompt_version": prompt_version,
        "latency_ms": latency_ms,
        "warnings": [],
    }
