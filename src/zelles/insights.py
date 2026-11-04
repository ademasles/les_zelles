"""Decision support on top of the spec sheet.

* :func:`compare_product` checks a manufacturer's product against the CCTP
  ("can my range answer this tender?").
* :func:`clarification_questions` drafts the questions to send to the project
  owner before pricing (a "demande de précisions"), for missing, conflicting or
  unverified requirements. They are written in French because they go to French
  architects and project owners.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from zelles.domain.spec import FIELD_CATALOG, Requirement, RequirementStatus, SpecField, SpecSheet
from zelles.domain.validators import parse_aev, parse_number
from zelles.graph.knowledge import KnowledgeGraph

# ---------------------------------------------------------------- product checks


class ProductSpec(BaseModel):
    """Declared performances of a product (from a datasheet or a DoP)."""

    name: str
    frame_material: str | None = None
    uw: float | None = None
    ug: float | None = None
    ujn: float | None = None
    sw: float | None = None
    tlw: float | None = None
    aev: str | None = Field(default=None, description="e.g. 'A*4 E*7B V*A2'")
    acoustic_db: float | None = Field(default=None, description="Ra,tr in dB")
    security_class: str | None = Field(default=None, description="e.g. 'RC2'")
    colors: list[str] = Field(default_factory=list)


class Verdict(StrEnum):
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    REVIEW = "review"
    UNKNOWN = "unknown"


class ComplianceCheck(BaseModel):
    field: SpecField
    required: str
    scope: str | None
    offered: str | None
    verdict: Verdict
    reason: str


def _numeric_check(
    req: Requirement, offered: float, *, higher_is_better: bool
) -> tuple[Verdict, str]:
    target = req.numeric_value
    if target is None:
        return Verdict.REVIEW, "required value is not numeric"
    comparator = req.comparator or ("<=" if not higher_is_better else ">=")
    ok = {
        "<=": offered <= target,
        "<": offered < target,
        ">=": offered >= target,
        ">": offered > target,
        "=": abs(offered - target) < 1e-9,
    }.get(comparator, offered == target)
    return (
        Verdict.PASS if ok else Verdict.FAIL
    ), f"offered {offered:g} vs required {comparator} {target:g}"


def _class_rank(value: str) -> tuple[int, int]:
    """Rank AEV sub-classes: 'E*7B' -> (7, 0), 'V*C3' -> (3, 2 for letter C), 'E*E750' -> (750, 0)."""
    body = value.split("*", 1)[-1].upper()
    if body.startswith("E") and body[1:].isdigit():
        return int(body[1:]), 0
    digits = "".join(c for c in body if c.isdigit())
    letters = "".join(c for c in body if c.isalpha())
    letter_rank = {"A": 0, "B": 1, "C": 2}.get(letters[:1], 0) if letters else 0
    return int(digits or 0), letter_rank


def _aev_check(required: str, offered: str) -> tuple[Verdict, str]:
    need, have = parse_aev(required) or {}, parse_aev(offered) or {}
    reasons, verdict = [], Verdict.PASS
    for part in ("air", "water", "wind"):
        if part not in need:
            continue
        if part not in have:
            return Verdict.UNKNOWN, f"product has no {part} class"
        n, h = _class_rank(need[part]), _class_rank(have[part])
        if part == "water" and need[part][-1:] != have[part][-1:] and need[part][-1:] in "AB":
            verdict = Verdict.REVIEW if verdict == Verdict.PASS else verdict
            reasons.append(f"{part}: test methods differ ({have[part]} vs {need[part]})")
            continue
        ok = h[0] >= n[0] and (part != "wind" or h[1] >= n[1])
        if not ok:
            verdict = Verdict.FAIL
        reasons.append(f"{part}: {have[part]} vs {need[part]}")
    return verdict, "; ".join(reasons)


def compare_product(sheet: SpecSheet, product: ProductSpec) -> list[ComplianceCheck]:
    checks: list[ComplianceCheck] = []
    numeric = {
        SpecField.UW: (product.uw, False),
        SpecField.UG: (product.ug, False),
        SpecField.UJN: (product.ujn, False),
        SpecField.SW: (product.sw, True),
        SpecField.TLW: (product.tlw, True),
        SpecField.ACOUSTIC: (product.acoustic_db, True),
    }
    for req in sheet.requirements:
        if req.status == RequirementStatus.INVALID:
            continue
        offered: str | None = None
        verdict, reason = Verdict.UNKNOWN, "not declared for this product"
        if req.field in numeric:
            value, higher = numeric[req.field]
            if value is not None:
                offered = f"{value:g}"
                verdict, reason = _numeric_check(req, value, higher_is_better=higher)
        elif req.field == SpecField.AEV and product.aev:
            offered = product.aev
            verdict, reason = _aev_check(req.value, product.aev)
        elif req.field == SpecField.SECURITY_CLASS and product.security_class:
            offered = product.security_class
            need, have = (
                parse_number(req.value.replace("RC", " ").replace("CR", " ")),
                parse_number(product.security_class.replace("RC", " ").replace("CR", " ")),
            )
            if need is not None and have is not None:
                verdict = Verdict.PASS if have >= need else Verdict.FAIL
                reason = f"offered {product.security_class} vs required {req.value}"
        elif req.field == SpecField.FRAME_MATERIAL and product.frame_material:
            offered = product.frame_material
            same = (
                product.frame_material.lower() in req.value.lower()
                or req.value.lower() in product.frame_material.lower()
            )
            verdict = Verdict.PASS if same else Verdict.FAIL
            reason = "same material" if same else "different material"
        elif req.field == SpecField.COLOR and product.colors:
            offered = ", ".join(product.colors)
            codes = [c for c in req.value.upper().split() if c.isdigit()]
            available = " ".join(product.colors).upper()
            ok = all(code in available for code in codes) if codes else False
            verdict = Verdict.PASS if ok else Verdict.REVIEW
            reason = "color available" if ok else "check color availability"
        else:
            continue
        checks.append(
            ComplianceCheck(
                field=req.field,
                required=req.value,
                scope=req.scope,
                offered=offered,
                verdict=verdict,
                reason=reason,
            )
        )
    return checks


# ---------------------------------------------------------------- clarifications

CRITICAL_FIELDS: dict[SpecField, str] = {
    SpecField.FRAME_MATERIAL: "Pouvez-vous préciser le matériau attendu pour les menuiseries (PVC, aluminium, bois, mixte) ?",
    SpecField.UW: "Quelle performance thermique Uw est exigée pour les menuiseries ?",
    SpecField.AEV: "Quel classement AEV (air, eau, vent) est exigé pour les menuiseries ?",
    SpecField.GLAZING_COMPOSITION: "Quelle composition de vitrage est attendue (épaisseurs, lame de gaz) ?",
    SpecField.COLOR: "Quels coloris (références RAL) sont attendus, en intérieur et en extérieur ?",
    SpecField.INSTALLATION: "Quel mode de pose est retenu (applique, tunnel, feuillure, rénovation sur dormant existant) ?",
    SpecField.ACOUSTIC: "Un affaiblissement acoustique Ra,tr est-il exigé selon l'exposition des façades ?",
}


class Clarification(BaseModel):
    reason: str
    field: SpecField | None
    question: str


def clarification_questions(
    sheet: SpecSheet, graph: KnowledgeGraph | None = None
) -> list[Clarification]:
    out: list[Clarification] = []
    present = {r.field for r in sheet.requirements if r.status != RequirementStatus.INVALID}
    for field, question in CRITICAL_FIELDS.items():
        if field not in present:
            out.append(Clarification(reason="missing", field=field, question=question))
    for conflict in graph.conflicts() if graph else []:
        label = FIELD_CATALOG[conflict.field].label
        where = f" pour « {conflict.scope} »" if conflict.scope else ""
        out.append(
            Clarification(
                reason="conflict",
                field=conflict.field,
                question=f"Le CCTP indique deux valeurs différentes pour {label}{where} "
                f"({' / '.join(conflict.values)}). Laquelle doit être retenue ?",
            )
        )
    for req in sheet.requirements:
        if req.status == RequirementStatus.INVALID:
            out.append(
                Clarification(
                    reason="invalid",
                    field=req.field,
                    question=f"La valeur « {req.value} » ({FIELD_CATALOG[req.field].label}) "
                    "semble incohérente. Pouvez-vous la confirmer ?",
                )
            )
    return out
