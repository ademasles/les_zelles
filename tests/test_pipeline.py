from typing import Any

from zelles.config import Settings
from zelles.domain.spec import RequirementStatus, SpecField
from zelles.llm.base import Message
from zelles.llm.fake import FakeLLM, HashEmbedder
from zelles.pipeline import analyze

from .fakes import extraction_responder


async def test_rules_only(sample_bytes: bytes, settings: Settings) -> None:
    analysis = await analyze(sample_bytes, "cctp.md", settings=settings)
    sheet = analysis.sheet
    assert sheet.model == "rules"
    assert sheet.usage.calls == 0 and sheet.usage.cost_usd == 0.0
    assert sheet.lots == ["Lot 05 - MENUISERIES EXTÉRIEURES"]
    assert sheet.coverage() > 0.9
    assert analysis.graph.stats()["Standard"] >= 3


async def test_llm_adds_values_and_hallucinations_are_flagged(
    sample_bytes: bytes, settings: Settings
) -> None:
    llm = FakeLLM(extraction_responder)
    analysis = await analyze(
        sample_bytes, "cctp.md", settings=settings, llm=llm, embedder=HashEmbedder()
    )
    reqs = analysis.sheet.requirements
    acoustic = {r.numeric_value: r for r in reqs if r.field == SpecField.ACOUSTIC}
    assert set(acoustic) == {30.0, 28.0}
    # Found by the rules too: the LLM confirms it and contributes the precise scope.
    assert acoustic[28.0].scope == "autres façades"
    assert "confirmed by rules and LLM" in acoustic[28.0].notes
    assert acoustic[28.0].status == RequirementStatus.VERIFIED
    rc3 = next(r for r in reqs if r.field == SpecField.SECURITY_CLASS and r.value == "RC3")
    assert rc3.status == RequirementStatus.UNVERIFIED
    uw = next(r for r in reqs if r.field == SpecField.UW and r.numeric_value == 1.3)
    assert "confirmed by rules and LLM" in uw.notes
    assert analysis.sheet.summary and "PVC" in analysis.sheet.summary
    assert len(llm.calls) == 6  # five field groups and one summary


async def test_hybrid_search_prefers_relevant_passage(
    sample_bytes: bytes, settings: Settings
) -> None:
    analysis = await analyze(sample_bytes, "cctp.md", settings=settings, embedder=HashEmbedder())
    hits = await analysis.index.search("volets roulants motorisation", k=3)
    assert hits[0].chunk.heading == "4.1 Volets roulants"
    assert hits[0].lexical_rank == 0


GAP_DOC = (
    "# Lot 05 Menuiseries extérieures\n\n## 1 Généralités\n\n"
    "Les menuiseries extérieures seront en PVC. Ouverture OB pour toutes les fenêtres.\n"
).encode()


def gap_responder(system: str, messages: list[Message], schema: type[Any] | None) -> Any:
    prompt = messages[-1].content
    assert "- frame_material:" not in prompt  # the rules already found it
    items = []
    if "- opening_type:" in prompt:
        quote = "Ouverture OB pour toutes les fenêtres"
        items.append({"field": "opening_type", "value": "OB", "chunk_id": "c0000", "quote": quote})
    if "- security_class:" in prompt:  # a hallucination: no such sentence
        quote = "Les fenêtres seront de classe RC3"
        items.append(
            {"field": "security_class", "value": "RC3", "chunk_id": "c0000", "quote": quote}
        )
    return {"items": items}


async def test_gap_mode_asks_only_missing_fields_and_keeps_grounded_values(
    settings: Settings,
) -> None:
    llm = FakeLLM(gap_responder)
    gaps = settings.model_copy(update={"llm_mode": "gaps"})
    analysis = await analyze(GAP_DOC, "cctp.md", settings=gaps, llm=llm, summarize=False)
    reqs = {(r.field, r.value): r for r in analysis.sheet.requirements}
    assert set(reqs) == {(SpecField.FRAME_MATERIAL, "PVC"), (SpecField.OPENING_TYPE, "OB")}
    assert all(r.status == RequirementStatus.VERIFIED for r in reqs.values())
    prompts = " ".join(m.content for _, msgs in llm.calls for m in msgs)
    assert "- standards:" in prompts  # open list: asked even when the rules find some
