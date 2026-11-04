from zelles.domain.documents import Chunk
from zelles.domain.spec import (
    Citation,
    Requirement,
    RequirementSource,
    RequirementStatus,
    SpecField,
)
from zelles.extraction.llm_extractor import LLMExtractor
from zelles.extraction.merge import merge_requirements
from zelles.extraction.rules import extract_with_rules
from zelles.extraction.verify import locate_quote, verify_requirement
from zelles.ingest.chunking import chunk_document
from zelles.ingest.parsers import parse_document
from zelles.llm.fake import FakeLLM


def _chunks(sample_bytes: bytes) -> list[Chunk]:
    doc, _ = parse_document(sample_bytes, "cctp.md")
    return chunk_document(doc)


def test_rules_find_core_values_with_citations(sample_bytes: bytes) -> None:
    reqs = extract_with_rules(_chunks(sample_bytes))
    uw = {r.numeric_value: r for r in reqs if r.field == SpecField.UW}
    assert set(uw) == {1.3, 1.6}
    assert uw[1.3].comparator == "<="
    assert uw[1.3].scope == "2 MENUISERIES PVC - LOGEMENTS"
    assert uw[1.6].scope == "3 MENUISERIES ALUMINIUM - HALL ET LOCAUX COMMUNS"
    assert {r.value for r in reqs if r.field == SpecField.AEV} == {"A*3 E*7B V*A2", "A*4 E*9A V*C3"}
    assert all(r.citation and r.citation.quote for r in reqs)
    assert all(r.status == RequirementStatus.VERIFIED for r in reqs)


def test_rules_skip_heading_lines(sample_bytes: bytes) -> None:
    reqs = extract_with_rules(_chunks(sample_bytes))
    assert not any(r.value == "Volets roulants" for r in reqs)


def test_locate_quote_exact_and_fuzzy() -> None:
    text = "Coefficient de transmission thermique des fenêtres : Uw ≤ 1,3 W/m².K. Facteur solaire Sw ≥ 0,40."
    assert locate_quote("Uw ≤ 1,3 W/m².K", text) == 1.0
    assert locate_quote("Uw <= 1,3 W/m2.K", text) > 0.85
    assert locate_quote("Uw ≤ 1,1 W/m².K pour les portes", text) < 0.88


def test_verify_flags_hallucinated_quote(sample_bytes: bytes) -> None:
    chunks = {c.id: c for c in _chunks(sample_bytes)}
    fake = Requirement(
        field=SpecField.UW,
        value="≤ 0,9 W/m².K",
        citation=Citation(chunk_id="c0005", quote="Uw ≤ 0,9 W/m².K pour toutes les menuiseries"),
    )
    checked = verify_requirement(fake, chunks)
    assert checked.status == RequirementStatus.UNVERIFIED
    assert checked.confidence <= 0.35


def test_verify_requires_number_in_quote(sample_bytes: bytes) -> None:
    chunks = {c.id: c for c in _chunks(sample_bytes)}
    wrong_number = Requirement(
        field=SpecField.UW,
        value="≤ 1,4 W/m².K",
        citation=Citation(
            chunk_id="c0005",
            quote="Coefficient de transmission thermique des fenêtres : Uw ≤ 1,3 W/m².K",
        ),
    )
    checked = verify_requirement(wrong_number, chunks)
    assert checked.status == RequirementStatus.UNVERIFIED
    assert "the number is not in the quoted text" in checked.notes


def test_verify_repairs_wrong_chunk_id(sample_bytes: bytes) -> None:
    chunks = {c.id: c for c in _chunks(sample_bytes)}
    req = Requirement(
        field=SpecField.ACOUSTIC,
        value="28 dB",
        scope="autres façades",
        citation=Citation(chunk_id="c0001", quote="28 dB pour les autres façades"),
    )
    checked = verify_requirement(req, chunks)
    assert checked.status == RequirementStatus.VERIFIED
    assert checked.citation is not None and "2.3 Performances" in checked.citation.locator


def test_merge_boosts_agreement(sample_bytes: bytes) -> None:
    chunks = _chunks(sample_bytes)
    rules = extract_with_rules(chunks)
    rule_uw = next(r for r in rules if r.field == SpecField.UW and r.numeric_value == 1.3)
    llm = rule_uw.model_copy(
        update={
            "source": RequirementSource.LLM,
            "value": "≤ 1,3 W/m².K",
            "scope": "Logements",
            "confidence": 0.7,
        }
    )
    merged = merge_requirements(rules, [llm])
    uw = [r for r in merged if r.field == SpecField.UW and r.numeric_value == 1.3]
    assert len(uw) == 1
    assert uw[0].confidence > rule_uw.confidence
    assert uw[0].scope == "Logements"
    assert "confirmed by rules and LLM" in uw[0].notes


def test_llm_extractor_fits_the_context_window() -> None:
    unbounded = LLMExtractor(FakeLLM(lambda *_: None))
    small = FakeLLM(lambda *_: None)
    small.context_tokens = 8192  # type: ignore[attr-defined]
    bounded = LLMExtractor(small)
    assert unbounded.whole_document_chars == 24_000
    assert bounded.whole_document_chars < 16_000
    prompt_tokens = (bounded.max_context_chars + 1_100 + 3_000) / 3.2
    assert prompt_tokens + 2048 < 8192
