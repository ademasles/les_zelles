"""Deterministic domain checks for extracted values.

These run on every requirement, whether a regex or an LLM produced it. They
catch the classic extraction failures: a Uw of 13 instead of 1.3, a solar
factor given in percent, an AEV class that does not exist in the standards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from zelles.domain.spec import SpecField

_NUMBER = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)")
_COMPARATORS = (
    (re.compile(r"≤|<=|inférieur(?:e)? ou égal|au plus|maximum|maxi|max\.?|n'excédant pas"), "<="),
    (re.compile(r"≥|>=|supérieur(?:e)? ou égal|au moins|minimum|mini|min\.?"), ">="),
    (re.compile(r"<|inférieur"), "<"),
    (re.compile(r">|supérieur"), ">"),
)

# NF EN 12207 (air), NF EN 12208 (water), NF EN 12210 (wind)
AEV_AIR = re.compile(r"A\s*\*?\s*([1-4])\b", re.IGNORECASE)
AEV_WATER = re.compile(r"E\s*\*?\s*([1-9][AB]|E\s*\d{3,4})\b", re.IGNORECASE)
AEV_WIND = re.compile(r"V\s*\*?\s*([ABC]\s*[1-5]|E\s*\d{3,4})\b", re.IGNORECASE)

# Plausible ranges, wide on purpose: they flag unit or OCR errors, not design choices.
RANGES: dict[SpecField, tuple[float, float]] = {
    SpecField.UW: (0.4, 6.0),
    SpecField.UG: (0.3, 6.0),
    SpecField.UJN: (0.4, 6.0),
    SpecField.SW: (0.0, 1.0),
    SpecField.TLW: (0.0, 1.0),
    SpecField.ACOUSTIC: (15.0, 60.0),
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    numeric_value: float | None = None
    comparator: str | None = None
    normalized: str | None = None
    message: str | None = None


def parse_number(text: str) -> float | None:
    """Return the first number in French or English notation ('1,3' -> 1.3)."""
    match = _NUMBER.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def parse_comparator(text: str) -> str | None:
    lowered = text.lower()
    for pattern, symbol in _COMPARATORS:
        if pattern.search(lowered):
            return symbol
    return None


def parse_aev(text: str) -> dict[str, str] | None:
    """Parse an AEV classification such as 'A*3 E*7B V*A2' into its three parts."""
    parts: dict[str, str] = {}
    if m := AEV_AIR.search(text):
        parts["air"] = f"A*{m.group(1)}"
    if m := AEV_WATER.search(text):
        parts["water"] = "E*" + re.sub(r"\s+", "", m.group(1)).upper()
    if m := AEV_WIND.search(text):
        parts["wind"] = "V*" + re.sub(r"\s+", "", m.group(1)).upper()
    return parts or None


def format_aev(parts: dict[str, str]) -> str:
    return " ".join(parts[k] for k in ("air", "water", "wind") if k in parts)


def validate(field: SpecField, value: str) -> ValidationResult:
    """Validate and normalize a value for a given field."""
    if not value or not value.strip():
        return ValidationResult(ok=False, message="empty value")

    if field == SpecField.AEV:
        parts = parse_aev(value)
        if not parts:
            return ValidationResult(ok=False, message="no valid AEV class found")
        return ValidationResult(ok=True, normalized=format_aev(parts))

    if field in RANGES:
        number = parse_number(value)
        if number is None:
            return ValidationResult(ok=False, message="no number found")
        low, high = RANGES[field]
        if field in (SpecField.SW, SpecField.TLW) and 1.0 < number <= 100.0:
            number = number / 100.0  # stated as a percentage
        if not low <= number <= high:
            return ValidationResult(
                ok=False,
                numeric_value=number,
                message=f"{number} is outside the plausible range {low}-{high}",
            )
        return ValidationResult(ok=True, numeric_value=number, comparator=parse_comparator(value))

    if field == SpecField.COLOR:
        for code in re.findall(r"RAL\s*(\d{4})", value, flags=re.IGNORECASE):
            if not 1000 <= int(code) <= 9023:
                return ValidationResult(ok=False, message=f"RAL {code} is not a RAL Classic code")

    return ValidationResult(ok=True)
