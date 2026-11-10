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
from zelles.extraction.verify import locate_quote, mentions_field, verify_requirement
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


def test_llm_value_codes_must_be_quoted(sample_bytes: bytes) -> None:
    chunks = {c.id: c for c in _chunks(sample_bytes)}
    aev = next(c for c in chunks.values() if "A*3" in c.text)
    start = aev.text.index("A*3")
    quote = aev.text[max(0, start - 20) : start + 20]
    invented = Requirement(
        field=SpecField.AEV,
        value="A*2 V*A2",
        source=RequirementSource.LLM,
        citation=Citation(chunk_id=aev.id, quote=quote),
    )
    checked = verify_requirement(invented, chunks)
    assert checked.status == RequirementStatus.UNVERIFIED
    assert "the value is not in the quoted text" in checked.notes


def test_mentions_field_tolerates_plurals_and_accents() -> None:
    assert mentions_field(SpecField.SHUTTERS, "Persiennes en aluminium")
    assert mentions_field(SpecField.HARDWARE, "Poignées en Zamak")
    assert not mentions_field(SpecField.SHUTTERS, "Poignées en Zamak, système Winkhaus")
    assert not mentions_field(SpecField.FINISH, "largeur vue inférieure à 80 mm")
    assert not mentions_field(SpecField.SW, "Les ouvrants seront oscillo-battants")
    assert not mentions_field(SpecField.PROFILE_SYSTEM, "système Winkhaus pour les fermetures")
    assert mentions_field(SpecField.PROFILE_SYSTEM, "profilés de 60 mm à quatre chambres")


def test_merge_drops_ungrounded_value_beside_grounded_one() -> None:
    def req(value: str, source: RequirementSource, status: RequirementStatus) -> Requirement:
        return Requirement(
            field=SpecField.AEV,
            value=value,
            source=source,
            status=status,
            citation=Citation(chunk_id="c0001", quote=value),
        )

    rules = [req("A*3 E*7B V*A3", RequirementSource.RULES, RequirementStatus.VERIFIED)]
    llm = [req("A*2 V*A2", RequirementSource.LLM, RequirementStatus.UNVERIFIED)]
    assert [r.value for r in merge_requirements(rules, llm)] == ["A*3 E*7B V*A3"]


def _hw(value: str, chunk: str = "c1") -> Requirement:
    return Requirement(
        field=SpecField.HARDWARE,
        value=value,
        citation=Citation(chunk_id=chunk, quote=value, locator=f"art {chunk}"),
        status=RequirementStatus.VERIFIED,
    )


def test_near_duplicates_merge_into_the_most_complete_value() -> None:
    from zelles.extraction.dedupe import merge_near_duplicates

    reqs = [
        _hw("SP615"),
        _hw("type SP615 ou équivalent"),
        _hw("treuil", "c2"),
        _hw("Manœuvre par treuil à tige semi-mobile", "c3"),
        _hw("crémone"),
    ]
    kept = merge_near_duplicates(reqs)
    assert [r.value for r in kept] == [
        "SP615",  # same words as "type SP615 ou équivalent": the first one read stays
        "Manœuvre par treuil à tige semi-mobile",
        "crémone",
    ]
    assert any("also stated as 'treuil' (art c2)" in n for n in kept[1].notes)


def test_label_words_and_code_spelling_do_not_make_two_values() -> None:
    from zelles.extraction.dedupe import merge_near_duplicates

    colors = [
        Requirement(field=SpecField.COLOR, value=v, status=RequirementStatus.VERIFIED)
        for v in ("teinte gris foncé", "coloris gris foncé", "blanc")
    ]
    assert [r.value for r in merge_near_duplicates(colors)] == ["teinte gris foncé", "blanc"]
    standards = [
        Requirement(field=SpecField.STANDARDS, value=v, status=RequirementStatus.VERIFIED)
        for v in ("NF.P 20.302", "NF P20-302", "NF D.T.U. 36.5", "D.T.U. 36.5")
    ]
    assert [r.value for r in merge_near_duplicates(standards)] == ["NF.P 20.302", "NF D.T.U. 36.5"]


def test_materials_and_numbers_are_never_merged() -> None:
    from zelles.extraction.dedupe import merge_near_duplicates

    frames = [
        Requirement(field=SpecField.FRAME_MATERIAL, value=v, status=RequirementStatus.VERIFIED)
        for v in ("aluminium", "bois-aluminium")
    ]
    assert len(merge_near_duplicates(frames)) == 2
