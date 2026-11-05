"""Grounding checks: every value must be backed by a quote that exists in the source.

This is the main defence against hallucination, and it costs nothing: the
model must quote the source verbatim, we find the quote in the chunk text
(exact, then fuzzy), and for numeric fields the number itself must appear in
the quote. Failing values are kept but marked, never shown as verified.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from zelles.domain.documents import Chunk
from zelles.domain.spec import (
    FIELD_CATALOG,
    Requirement,
    RequirementSource,
    RequirementStatus,
    SpecField,
)
from zelles.domain.validators import parse_number, validate
from zelles.ingest.cleaning import normalize_for_match

FUZZY_THRESHOLD = 0.88
_CODE_TOKEN = re.compile(r"[\w*/.,+-]*\d[\w*/.,+-]*")


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_for_match(text))


def _stem_pattern(term: str) -> re.Pattern[str]:
    words = normalize_for_match(term).split()
    parts = [
        re.escape(w) + r"\b" if len(w) <= 3 else re.escape(w[: max(4, len(w) - 2)]) for w in words
    ]
    return re.compile(r"\b" + r"\W*".join(parts))


_FIELD_TERMS = {
    field: [_stem_pattern(t) for t in info.search_terms] for field, info in FIELD_CATALOG.items()
}


def mentions_field(field: SpecField, text: str) -> bool:
    """True when ``text`` uses some of the field's own vocabulary (accent and plural tolerant)."""
    folded = normalize_for_match(text)
    return any(p.search(folded) for p in _FIELD_TERMS[field])


def value_codes_in_quote(value: str, quote: str) -> bool:
    """Every token of the value that carries a digit (A*3, RAL 9010, 4/16/4) is in the quote.

    Tokens are compared whole, so A*2 does not match inside V*A2; a token may span up
    to three quote words ("RAL9010" against "RAL 9010").
    """
    words = [w for w in (_alnum(w) for w in normalize_for_match(quote).split()) if w]
    spans = {"".join(words[i : i + n]) for n in (1, 2, 3) for i in range(len(words))}
    return all(_alnum(t) in spans for t in _CODE_TOKEN.findall(value) if _alnum(t))


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
    elif (
        req.source == RequirementSource.LLM
        and not FIELD_CATALOG[req.field].numeric
        and not value_codes_in_quote(req.value, citation.quote)
    ):
        status = RequirementStatus.UNVERIFIED
        confidence = min(confidence, 0.35)
        notes.append("the value is not in the quoted text")
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
