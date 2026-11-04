"""Scripted LLM responses for tests."""

from __future__ import annotations

from typing import Any

from zelles.llm.base import Message


def extraction_responder(system: str, messages: list[Message], schema: type[Any] | None) -> Any:
    prompt = messages[-1].content
    if schema is None:
        return "- Lot 05 joinery: PVC dwellings, aluminium hall.\n- Uw ≤ 1,3 W/m².K."
    if schema.__name__ != "ExtractionResult":
        raise AssertionError(schema)
    items = []
    if "- acoustic:" in prompt:
        items += [
            {
                "field": "acoustic",
                "value": "Ra,tr ≥ 30 dB",
                "scope": "façades sur rue",
                "chunk_id": "c0005",
                "quote": "Ra,tr ≥ 30 dB pour les façades sur rue",
            },
            {
                "field": "acoustic",
                "value": "28 dB",
                "scope": "autres façades",
                "chunk_id": "c0005",
                "quote": "28 dB pour les autres façades",
            },
            # a hallucination: the quote does not exist
            {
                "field": "security_class",
                "value": "RC3",
                "scope": "logements",
                "chunk_id": "c0003",
                "quote": "Les fenêtres des logements seront de classe RC3",
            },
        ]
    if "- uw:" in prompt:
        items.append(
            {
                "field": "uw",
                "value": "≤ 1,3 W/m².K",
                "scope": "Logements (PVC)",
                "chunk_id": "c0005",
                "quote": "Coefficient de transmission thermique des fenêtres : Uw ≤ 1,3 W/m².K",
            }
        )
    return {"items": items}
