"""Cited question answering over one CCTP (retrieval-augmented, verified quotes)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from zelles.domain.documents import Chunk
from zelles.domain.spec import Citation, Usage
from zelles.extraction.prompts import QA_SYSTEM, format_passages
from zelles.extraction.verify import FUZZY_THRESHOLD, locate_quote
from zelles.llm.base import LLM, Message
from zelles.retrieval.index import DocumentIndex


class _Cite(BaseModel):
    chunk_id: str
    quote: str


class _LLMAnswer(BaseModel):
    found: bool
    answer: str
    citations: list[_Cite] = Field(default_factory=list)


class Answer(BaseModel):
    question: str
    answer: str
    found: bool
    citations: list[Citation] = Field(default_factory=list)
    passages: list[str] = Field(default_factory=list, description="Ids of the passages retrieved.")
    usage: Usage = Field(default_factory=Usage)
    grounded: bool = Field(default=False, description="All citations were found in the source.")


async def answer_question(
    question: str, index: DocumentIndex, llm: LLM | None, *, k: int = 6
) -> Answer:
    hits = await index.search(question, k=k)
    chunks = [h.chunk for h in hits]
    if llm is None or not chunks:
        return _extractive(question, chunks)

    prompt = f"PASSAGES\n\n{format_passages(chunks)}\n\nQUESTION\n{question}"
    result = await llm.complete(
        system=QA_SYSTEM, messages=[Message("user", prompt)], schema=_LLMAnswer
    )
    parsed = result.parsed or _LLMAnswer(found=False, answer="")
    by_id = {c.id: c for c in index.chunks}
    citations: list[Citation] = []
    for cite in parsed.citations:
        chunk = by_id.get(cite.chunk_id.strip("[] "))
        score = locate_quote(cite.quote, chunk.text) if chunk else 0.0
        citations.append(
            Citation(
                chunk_id=chunk.id if chunk else cite.chunk_id,
                quote=cite.quote,
                page=chunk.page_start if chunk else None,
                locator=chunk.locator() if chunk else "",
                match_score=round(score, 3),
            )
        )
    grounded = bool(citations) and all(c.match_score >= FUZZY_THRESHOLD for c in citations)
    return Answer(
        question=question,
        answer=parsed.answer,
        found=parsed.found,
        citations=citations,
        passages=[c.id for c in chunks],
        usage=result.usage,
        grounded=grounded,
    )


def _extractive(question: str, chunks: list[Chunk]) -> Answer:
    """No-LLM mode: return the best passages as the answer."""
    if not chunks:
        return Answer(question=question, answer="No relevant passage found.", found=False)
    best = chunks[:3]
    return Answer(
        question=question,
        answer="\n\n".join(f"{c.locator()}\n{c.text}" for c in best),
        found=True,
        citations=[
            Citation(
                chunk_id=c.id,
                quote=c.text[:300],
                page=c.page_start,
                locator=c.locator(),
                match_score=1.0,
            )
            for c in best
        ],
        passages=[c.id for c in chunks],
        grounded=True,
    )
