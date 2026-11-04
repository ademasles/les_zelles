"""Evaluation harness: score extraction on a golden set of annotated CCTPs.

Layout: ``evals/golden/<case>/`` holds the source (``cctp.pdf|docx|md|txt``) and
``expected.json`` with the requirements a careful estimator would list. A
prediction matches an expectation when the field is the same and the value
matches (numbers exactly, text by containment after accent folding).
Precision counts every predicted requirement; recall every expected one.
"""

from __future__ import annotations

import json
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


class CaseReport(BaseModel):
    name: str
    predicted: int
    expected: int
    true_positives: int
    precision: float
    recall: float
    f1: float
    grounded_rate: float
    cost_usd: float | None
    seconds: float
    misses: list[str] = Field(default_factory=list)
    extras: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    model: str
    cases: list[CaseReport]
    precision: float
    recall: float
    f1: float
    misses: list[str]


def matches(pred: Requirement, exp: Expected) -> bool:
    if pred.field != exp.field:
        return False
    if exp.numeric is not None:
        return pred.numeric_value is not None and abs(pred.numeric_value - exp.numeric) < 1e-6
    if exp.value is None:
        return False
    want = _comparable(exp.value)
    have = _comparable(pred.value + " " + (pred.citation.quote if pred.citation else ""))
    return want in have


def _comparable(text: str) -> str:
    """Fold accents and case; hyphens and stars as spaces ("warm-edge" = "warm edge")."""
    return " ".join(fold(text).replace("*", " * ").replace("-", " ").split())


def score(
    predicted: list[Requirement], expected: list[Expected]
) -> tuple[int, list[Expected], list[Requirement]]:
    matched_exp = [e for e in expected if any(matches(p, e) for p in predicted)]
    extras = [p for p in predicted if not any(matches(p, e) for e in expected)]
    return len(matched_exp), [e for e in expected if e not in matched_exp], extras


def _f1(p: float, r: float) -> float:
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


async def run_eval(golden_dir: Path, settings: Settings) -> EvalReport:
    from zelles.pipeline import analyze  # noqa: PLC0415

    llm = create_llm(settings.llm_model, settings)
    embedder = create_embedder(settings.embedding_model, settings)
    cases: list[CaseReport] = []
    tp_all = pred_all = exp_all = 0
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
            # precision: a prediction is correct if it matches any expectation
            correct_preds = len(predicted) - len(extras)
            precision = correct_preds / len(predicted) if predicted else 0.0
            recall = tp / len(expected) if expected else 0.0
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
                    precision=precision,
                    recall=recall,
                    f1=_f1(precision, recall),
                    grounded_rate=grounded,
                    cost_usd=analysis.sheet.usage.cost_usd,
                    seconds=analysis.timings.get("total", 0.0),
                    misses=miss_labels,
                    extras=[f"{e.field.value} = {e.value}" for e in extras],
                )
            )
            tp_all += correct_preds
            pred_all += len(predicted)
            exp_all += len(expected)
            all_misses += miss_labels
    finally:
        if llm is not None:
            await llm.aclose()
        if embedder is not None:
            await embedder.aclose()
    recall_all = sum(c.true_positives for c in cases) / exp_all if exp_all else 0.0
    precision_all = tp_all / pred_all if pred_all else 0.0
    return EvalReport(
        model=llm.name if llm else "rules",
        cases=cases,
        precision=precision_all,
        recall=recall_all,
        f1=_f1(precision_all, recall_all),
        misses=all_misses,
    )
