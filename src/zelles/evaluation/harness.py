"""Evaluation harness: score extraction on a golden set of annotated CCTPs.

Layout: ``evals/golden/<case>/`` holds the source (``cctp.pdf|docx|md|txt``) and
``expected.json`` with the requirements a careful estimator would list. A
prediction matches an expectation when the field is the same and the value
matches (numbers exactly, text by containment after accent folding).
Precision counts every predicted requirement; recall every expected one.

Two scores are reported. The lenient one also looks in the cited quote, which
credits a correct line whose extracted value is garbled. The strict one looks
at the extracted value only: it is what an estimator reads in the sheet.
Micro F1 comes with a 95 % bootstrap interval over cases (tenders), so a
change smaller than the interval is noise.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from zelles.config import Settings
from zelles.domain.spec import Requirement, SpecField
from zelles.llm.registry import create_embedder, create_llm
from zelles.retrieval.text import fold

SOURCE_NAMES = ("cctp.pdf", "cctp.docx", "cctp.md", "cctp.txt")


class Expected(BaseModel):
    field: SpecField
    value: str | None = None
    numeric: float | None = None


class FieldCounts(BaseModel):
    """Strict counts for one field, summed into the per-field table."""

    expected: int = 0
    found: int = 0
    predicted: int = 0
    correct: int = 0

    def add(self, other: FieldCounts) -> None:
        self.expected += other.expected
        self.found += other.found
        self.predicted += other.predicted
        self.correct += other.correct

    @property
    def misses(self) -> int:
        return self.expected - self.found

    @property
    def extras(self) -> int:
        return self.predicted - self.correct


class CaseReport(BaseModel):
    name: str
    predicted: int
    expected: int
    true_positives: int
    correct_predictions: int
    strict_true_positives: int
    strict_correct_predictions: int
    precision: float
    recall: float
    f1: float
    strict_precision: float
    strict_recall: float
    strict_f1: float
    grounded_rate: float
    cost_usd: float | None
    seconds: float
    misses: list[str] = Field(default_factory=list)
    extras: list[str] = Field(default_factory=list)
    fields: dict[str, FieldCounts] = Field(default_factory=dict)


class EvalReport(BaseModel):
    model: str
    cases: list[CaseReport]
    precision: float
    recall: float
    f1: float
    f1_ci: tuple[float, float]
    strict_precision: float
    strict_recall: float
    strict_f1: float
    strict_f1_ci: tuple[float, float]
    misses: list[str]
    fields: dict[str, FieldCounts] = Field(default_factory=dict)

    def blinded(self) -> EvalReport:
        """Counts only: no case names, values or quotes (for a held-out set)."""
        cases = [
            c.model_copy(update={"name": f"case {i}", "misses": [], "extras": []})
            for i, c in enumerate(self.cases, 1)
        ]
        return self.model_copy(update={"cases": cases, "misses": []})


def matches(pred: Requirement, exp: Expected, *, strict: bool = False) -> bool:
    """Whether a prediction states the expected requirement.

    ``strict`` looks at the extracted value only; otherwise the cited quote counts too.
    """
    if pred.field != exp.field:
        return False
    if exp.numeric is not None:
        return pred.numeric_value is not None and abs(pred.numeric_value - exp.numeric) < 1e-6
    if exp.value is None:
        return False
    want = _comparable(exp.value)
    quote = "" if strict or pred.citation is None else " " + pred.citation.quote
    return want in _comparable(pred.value + quote)


_ACRONYM = re.compile(r"\b((?:[a-z]+\.)+[a-z]+)\b\.?")  # "d.t.u." / "cer.f.f" -> "dtu" / "cerff"
_NF_PREFIX = re.compile(r"\bnf\s*\.\s*(?=[a-z])|\bnf(?=[abepsx]\s*\d)")  # "nf.p", "nfp 20"
_NUMERO = re.compile(r"\bn\s*[°º]\s*")  # "n°39", "n° 39"
_FIRST = re.compile(r"\b1er\b")  # "1er août" = "1 août"
_DIGIT_SEP = re.compile(r"(?<=\d)(?:\s*[.\-]\s*|,|\s+)(?=\d)")  # "20.501" = "20-501" = "20 501"
_UNIT_GLUE = re.compile(r"(?<=\d)(?=[a-z])")  # "37dB" = "37 dB"
_PLURAL = re.compile(r"\b([a-z]{4,})s\b")  # "thermolaqués" = "thermolaqué"


def _comparable(text: str) -> str:
    """Normalise wording variants that do not change the requirement.

    Accents and case are folded, hyphens and stars become spaces ("warm-edge" =
    "warm edge"), dotted acronyms and "n°" are dropped ("D.T.U. n°39" = "DTU 39"),
    "1er" is "1", a unit may be glued to its number ("37dB" = "37 dB"), a
    plural "s" is dropped, and digit groups compare equal whatever the separator
    ("NF P 20-501" contains "20.501").
    """
    text = fold(text)
    text = _ACRONYM.sub(lambda m: m.group(1).replace(".", "") + " ", text)
    text = _NF_PREFIX.sub("nf ", text)
    text = _NUMERO.sub("", text)
    text = _FIRST.sub("1", text)
    text = _UNIT_GLUE.sub(" ", text)
    text = _PLURAL.sub(r"\1", text)
    text = " ".join(text.replace("*", " * ").replace("-", " ").split())
    return _DIGIT_SEP.sub(".", text)


def score(
    predicted: list[Requirement], expected: list[Expected], *, strict: bool = False
) -> tuple[int, list[Expected], list[Requirement]]:
    matched_exp = [e for e in expected if any(matches(p, e, strict=strict) for p in predicted)]
    extras = [p for p in predicted if not any(matches(p, e, strict=strict) for e in expected)]
    return len(matched_exp), [e for e in expected if e not in matched_exp], extras


def field_counts(predicted: list[Requirement], expected: list[Expected]) -> dict[str, FieldCounts]:
    """Strict per-field counts: where recall is lost and where noise comes from."""
    counts: dict[str, FieldCounts] = {}
    for exp in expected:
        c = counts.setdefault(exp.field.value, FieldCounts())
        c.expected += 1
        c.found += any(matches(p, exp, strict=True) for p in predicted)
    for pred in predicted:
        c = counts.setdefault(pred.field.value, FieldCounts())
        c.predicted += 1
        c.correct += any(matches(pred, e, strict=True) for e in expected)
    return counts


def sum_fields(cases: Sequence[CaseReport]) -> dict[str, FieldCounts]:
    total: dict[str, FieldCounts] = {}
    for case in cases:
        for name, counts in case.fields.items():
            total.setdefault(name, FieldCounts()).add(counts)
    return dict(sorted(total.items(), key=lambda kv: (-(kv[1].misses + kv[1].extras), kv[0])))


def _f1(p: float, r: float) -> float:
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def _ratio(num: int, den: int) -> float:
    return num / den if den else 0.0


def micro_f1(cases: Sequence[CaseReport], *, strict: bool = False) -> tuple[float, float, float]:
    """Micro precision, recall and F1 from summed counts."""
    correct = sum(c.strict_correct_predictions if strict else c.correct_predictions for c in cases)
    found = sum(c.strict_true_positives if strict else c.true_positives for c in cases)
    precision = _ratio(correct, sum(c.predicted for c in cases))
    recall = _ratio(found, sum(c.expected for c in cases))
    return precision, recall, _f1(precision, recall)


def bootstrap_f1(
    cases: Sequence[CaseReport],
    *,
    strict: bool = False,
    samples: int = 2000,
    seed: int = 0,
) -> tuple[float, float]:
    """95 % percentile interval of micro F1, resampling cases with replacement.

    Cases, not requirements, are resampled: values within one tender are
    correlated (same author, same template), so tenders are the unit of evidence.
    """
    if not cases:
        return (0.0, 0.0)
    rng = random.Random(seed)  # noqa: S311 - reproducible resampling, not security
    scores = sorted(
        micro_f1(rng.choices(cases, k=len(cases)), strict=strict)[2] for _ in range(samples)
    )
    return scores[int(0.025 * (samples - 1))], scores[int(0.975 * (samples - 1))]


async def run_eval(golden_dir: Path, settings: Settings) -> EvalReport:
    from zelles.pipeline import analyze  # noqa: PLC0415

    llm = create_llm(settings.llm_model, settings)
    embedder = create_embedder(settings.embedding_model, settings)
    cases: list[CaseReport] = []
    all_misses: list[str] = []
    try:
        for case_dir in sorted(p for p in golden_dir.iterdir() if p.is_dir()):  # noqa: ASYNC240
            source = next((case_dir / n for n in SOURCE_NAMES if (case_dir / n).exists()), None)
            if source is None or not (case_dir / "expected.json").exists():
                continue
            expected = [
                Expected.model_validate(e)
                for e in json.loads((case_dir / "expected.json").read_text())["requirements"]
            ]
            analysis = await analyze(
                source.read_bytes(),
                source.name,
                settings=settings,
                llm=llm,
                embedder=embedder,
                summarize=False,
            )
            predicted = analysis.sheet.requirements
            tp, misses, extras = score(predicted, expected)
            strict_tp, _, strict_extras = score(predicted, expected, strict=True)
            # precision: a prediction is correct if it matches any expectation
            correct_preds = len(predicted) - len(extras)
            strict_correct = len(predicted) - len(strict_extras)
            precision = _ratio(correct_preds, len(predicted))
            recall = _ratio(tp, len(expected))
            strict_precision = _ratio(strict_correct, len(predicted))
            strict_recall = _ratio(strict_tp, len(expected))
            grounded = (
                sum(1 for p in predicted if p.status == "verified") / len(predicted)
                if predicted
                else 0.0
            )
            miss_labels = [
                f"{case_dir.name}: {m.field.value} = {m.value or m.numeric}" for m in misses
            ]
            cases.append(
                CaseReport(
                    name=case_dir.name,
                    predicted=len(predicted),
                    expected=len(expected),
                    true_positives=tp,
                    correct_predictions=correct_preds,
                    strict_true_positives=strict_tp,
                    strict_correct_predictions=strict_correct,
                    precision=precision,
                    recall=recall,
                    f1=_f1(precision, recall),
                    strict_precision=strict_precision,
                    strict_recall=strict_recall,
                    strict_f1=_f1(strict_precision, strict_recall),
                    grounded_rate=grounded,
                    cost_usd=analysis.sheet.usage.cost_usd,
                    seconds=analysis.timings.get("total", 0.0),
                    misses=miss_labels,
                    extras=[f"{e.field.value} = {e.value}" for e in extras],
                    fields=field_counts(predicted, expected),
                )
            )
            all_misses += miss_labels
    finally:
        if llm is not None:
            await llm.aclose()
        if embedder is not None:
            await embedder.aclose()
    precision_all, recall_all, f1_all = micro_f1(cases)
    strict_p, strict_r, strict_f = micro_f1(cases, strict=True)
    return EvalReport(
        model=llm.name if llm else "rules",
        cases=cases,
        precision=precision_all,
        recall=recall_all,
        f1=f1_all,
        f1_ci=bootstrap_f1(cases),
        strict_precision=strict_p,
        strict_recall=strict_r,
        strict_f1=strict_f,
        strict_f1_ci=bootstrap_f1(cases, strict=True),
        misses=all_misses,
        fields=sum_fields(cases),
    )
