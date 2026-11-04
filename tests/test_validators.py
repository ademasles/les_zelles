import pytest

from zelles.domain.spec import SpecField
from zelles.domain.validators import parse_aev, parse_comparator, parse_number, validate


def test_parse_number_french_decimal() -> None:
    assert parse_number("Uw ≤ 1,3 W/m².K") == 1.3
    assert parse_number("no number") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A*3 E*7B V*A2", {"air": "A*3", "water": "E*7B", "wind": "V*A2"}),
        ("classement A*4 - E*E750 - V*C3", {"air": "A*4", "water": "E*E750", "wind": "V*C3"}),
        ("A* 2 E* 5A V* B2", {"air": "A*2", "water": "E*5A", "wind": "V*B2"}),
    ],
)
def test_parse_aev(text: str, expected: dict[str, str]) -> None:
    assert parse_aev(text) == expected


def test_comparators() -> None:
    assert parse_comparator("Uw ≤ 1,3") == "<="
    assert parse_comparator("au moins 30 dB") == ">="


def test_ranges_catch_unit_errors() -> None:
    assert not validate(SpecField.UW, "Uw = 13 W/m².K").ok
    assert validate(SpecField.UW, "Uw ≤ 1,3").numeric_value == 1.3
    sw = validate(SpecField.SW, "Sw = 40 %")
    assert sw.ok and sw.numeric_value == 0.4


def test_invalid_ral() -> None:
    assert not validate(SpecField.COLOR, "RAL 0999").ok
    assert validate(SpecField.COLOR, "gris anthracite RAL 7016").ok


def test_aev_normalized() -> None:
    result = validate(SpecField.AEV, "a* 3 e*7b v*a2")
    assert result.ok and result.normalized == "A*3 E*7B V*A2"
