from zelles.config import Settings
from zelles.domain.spec import RequirementStatus, SpecField
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
