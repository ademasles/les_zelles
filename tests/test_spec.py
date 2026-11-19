from zelles.domain.spec import FIELD_CATALOG, SpecField
from zelles.evaluation.harness import Expected
from zelles.extraction.llm_extractor import FIELD_GROUPS


def test_every_field_is_catalogued_and_extractable() -> None:
    grouped = [field for fields in FIELD_GROUPS.values() for field in fields]
    assert set(FIELD_CATALOG) == set(SpecField)
    assert sorted(grouped) == sorted(SpecField)


def test_answer_key_accepts_fire_rating() -> None:
    entry = Expected.model_validate({"field": "fire_rating", "value": "EI 30"})
    assert entry.field is SpecField.FIRE_RATING
    assert not FIELD_CATALOG[SpecField.FIRE_RATING].numeric
