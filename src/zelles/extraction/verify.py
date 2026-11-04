"""Grounding checks: every value must be backed by a quote that exists in the source.

This is the main defence against hallucination, and it costs nothing: the
model must quote the source verbatim, we find the quote in the chunk text
(exact, then fuzzy), and for numeric fields the number itself must appear in
the quote. Failing values are kept but marked, never shown as verified.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from zelles.domain.documents import Chunk
from zelles.domain.spec import FIELD_CATALOG, Requirement, RequirementStatus
from zelles.domain.validators import parse_number, validate
from zelles.ingest.cleaning import normalize_for_match

FUZZY_THRESHOLD = 0.88


def locate_quote(quote: str, text: str) -> float:
    """Return how well ``quote`` matches a span of ``text`` (1.0 = verbatim)."""
    q, t = normalize_for_match(quote), normalize_for_match(text)
    if not q:
        return 0.0
    if q in t:
        return 1.0
    window = len(q)
    if window > len(t):
        return SequenceMatcher(None, q, t).ratio()
    best = 0.0
    step = max(1, window // 8)
    for start in range(0, len(t) - window + 1, step):
        ratio = SequenceMatcher(None, q, t[start : start + window]).ratio()
        if ratio > best:
            best = ratio
            if best >= 0.98:
                break
    return best


def verify_requirement(req: Requirement, chunks: dict[str, Chunk]) -> Requirement:
    """Check citation and value; set status, confidence and notes."""
    notes = list(req.notes)
    check = validate(req.field, req.value)
    if check.numeric_value is not None:
        req.numeric_value = check.numeric_value
    if check.comparator and not req.comparator:
        req.comparator = check.comparator
    if check.normalized:
        req.value = check.normalized
    if req.unit is None:
        req.unit = FIELD_CATALOG[req.field].unit

    citation = req.citation
    if citation is None or not citation.quote.strip():
        notes.append("no citation")
        return req.model_copy(
            update={
                "status": RequirementStatus.UNVERIFIED,
                "confidence": min(req.confidence, 0.3),
                "notes": notes,
            }
        )

    chunk = chunks.get(citation.chunk_id)
    score = locate_quote(citation.quote, chunk.text) if chunk else 0.0
    if score < FUZZY_THRESHOLD:  # the model may have cited the wrong chunk id
        for other in chunks.values():
            other_score = locate_quote(citation.quote, other.text)
            if other_score > score:
                chunk, score = other, other_score
            if score >= 0.99:
                break
    if chunk is not None:
        citation.chunk_id = chunk.id
        position = chunk.text.find(citation.quote)
        citation.page = chunk.page_at(position) if position >= 0 else chunk.page_start
        citation.locator = chunk.locator()
        if req.scope is None:
            req.scope = chunk.scope
    citation.match_score = round(score, 3)

    status = RequirementStatus.VERIFIED
    confidence = req.confidence
    if score < FUZZY_THRESHOLD:
        status = RequirementStatus.UNVERIFIED
        confidence = min(confidence, 0.35)
        notes.append(f"quote not found in source (best match {score:.0%})")
    elif not check.ok:
        status = RequirementStatus.INVALID
        confidence = min(confidence, 0.3)
        notes.append(check.message or "value failed validation")
    elif FIELD_CATALOG[req.field].numeric and req.numeric_value is not None:
        quoted = parse_numbers(citation.quote)
        if not any(
            abs(n - req.numeric_value) < 1e-6 or abs(n / 100 - req.numeric_value) < 1e-6
            for n in quoted
        ):
            status = RequirementStatus.UNVERIFIED
            confidence = min(confidence, 0.4)
            notes.append("the number is not in the quoted text")
    return req.model_copy(update={"status": status, "confidence": confidence, "notes": notes})


def parse_numbers(text: str) -> list[float]:
    out: list[float] = []
    for token in text.replace("≤", " ").replace("≥", " ").split():
        n = parse_number(token)
        if n is not None:
            out.append(n)
    return out
