"""Merge rule and LLM requirements. Agreement between the two raises confidence."""

from __future__ import annotations

from zelles.domain.spec import Requirement, RequirementStatus

_STATUS_RANK = {
    RequirementStatus.VERIFIED: 0,
    RequirementStatus.UNVERIFIED: 1,
    RequirementStatus.INVALID: 2,
}


def _value_key(req: Requirement) -> str:
    if req.numeric_value is not None:
        return f"{req.numeric_value:g}"
    return " ".join(req.value.lower().split())


def _same_place(a: Requirement, b: Requirement) -> bool:
    if a.citation and b.citation and a.citation.chunk_id == b.citation.chunk_id:
        return True
    if a.scope and b.scope:
        return a.scope.lower() == b.scope.lower()
    return True


def _related_values(a: Requirement, b: Requirement) -> bool:
    ka, kb = _value_key(a), _value_key(b)
    if a.numeric_value is not None or b.numeric_value is not None:
        return ka == kb
    return ka == kb or ka in kb or kb in ka


def merge_requirements(rules: list[Requirement], llm: list[Requirement]) -> list[Requirement]:
    merged: list[Requirement] = list(rules)
    for candidate in llm:
        match = next(
            (
                r
                for r in merged
                if r.field == candidate.field
                and _related_values(r, candidate)
                and _same_place(r, candidate)
            ),
            None,
        )
        if match is None:
            if candidate.status != RequirementStatus.VERIFIED and any(
                r.field == candidate.field
                and r.status == RequirementStatus.VERIFIED
                and _same_place(r, candidate)
                for r in merged
            ):
                continue  # an ungrounded value that contradicts a grounded one
            if not any(m.dedupe_key() == candidate.dedupe_key() for m in merged):
                merged.append(candidate)
            continue
        index = merged.index(match)
        if match.source == candidate.source:
            continue
        if candidate.status == RequirementStatus.VERIFIED:
            # Two independent extractors agree: keep the rule's exact citation,
            # take the model's wording and scope, which carry more context.
            merged[index] = match.model_copy(
                update={
                    "value": candidate.value
                    if len(candidate.value) >= len(match.value)
                    else match.value,
                    "scope": candidate.scope or match.scope,
                    "confidence": min(0.98, max(match.confidence, candidate.confidence) + 0.1),
                    "notes": [*match.notes, "confirmed by rules and LLM"],
                }
            )
    merged.sort(
        key=lambda r: (list(type(r.field)).index(r.field), _STATUS_RANK[r.status], -r.confidence)
    )
    return merged
