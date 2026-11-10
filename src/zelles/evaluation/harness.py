"""Evaluation harness: score extraction on a golden set of annotated CCTPs.

Layout: ``evals/golden/<case>/`` holds the source (``cctp.pdf|docx|md|txt``) and
``expected.json`` with the requirements a careful estimator would list. A
prediction matches an expectation when the field is the same and the value
matches (numbers exactly, text by containment after accent folding).
Predictions are grouped by field and value, since keys list a value once per
tender, and groups are matched to expected requirements one to one. Precision
counts value groups; recall counts expected requirements.

Two scores are reported. The lenient one also looks in the cited quote, which
credits a correct line whose extracted value is garbled. The strict one looks
at the extracted value only: it is what an estimator reads in the sheet.
Micro F1 comes with a 95 % bootstrap interval over cases (tenders), so a
change smaller than the interval is noise.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from zelles import __version__
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


class RunManifest(BaseModel):
    """What produced a score, so two numbers can be told apart months later."""

    scorer_version: str
    package_version: str
    git_commit: str | None = Field(description="Commit of the code, '+dirty' if modified.")
    keys_sha256: str = Field(description="Hash of every case's expected.json, in case order.")
    cases: int
    model: str
    embedding_model: str
    started_at: datetime


class EvalReport(BaseModel):
    model: str
    manifest: RunManifest | None = None
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


def git_commit(path: Path | None = None) -> str | None:
    """The checked-out commit of the code, or None outside a git checkout."""
    cwd = path or Path(__file__).resolve().parent
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{commit}+dirty" if dirty else commit


def keys_digest(key_files: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in key_files:
        digest.update(path.parent.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


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
_FEMININE = re.compile(r"\b([a-z]{3,}e)e\b")  # "teintée" = "teinté" (accents already folded)
_LETTER_DOT_DIGIT = re.compile(r"(?<=[a-z])\.(?=\d)")  # "NV.65" = "NV 65"
# Spelling variants of one word, not synonyms: the requirement must be the same.
_VARIANTS = {"limitateur": "limiteur"}
_VARIANT = re.compile(r"\b(" + "|".join(_VARIANTS) + r")\b")


def _comparable(text: str) -> str:
    """Normalise wording variants that do not change the requirement.

    Accents and case are folded, hyphens and stars become spaces ("warm-edge" =
    "warm edge"), dotted acronyms and "n°" are dropped ("D.T.U. n°39" = "DTU 39"),
    "1er" is "1", a dot between a code and its number is a space ("NV.65" =
    "NV 65"), spelling variants are unified ("limitateur" = "limiteur"), a unit may be glued to its number ("37dB" = "37 dB"), a
    plural "s" and a participle's feminine "e" are dropped ("teintées" = "teinté"),
    and digit groups compare equal whatever the separator ("NF P 20-501"
    contains "20.501").
    """
    text = fold(text)
    text = _ACRONYM.sub(lambda m: m.group(1).replace(".", "") + " ", text)
    text = _NF_PREFIX.sub("nf ", text)
    text = _NUMERO.sub("", text)
    text = _LETTER_DOT_DIGIT.sub(" ", text)
    text = _VARIANT.sub(lambda m: _VARIANTS[m.group(1)], text)
    text = _FIRST.sub("1", text)
    text = _UNIT_GLUE.sub(" ", text)
    text = _PLURAL.sub(r"\1", text)
    text = _FEMININE.sub(r"\1", text)
    text = " ".join(text.replace("*", " * ").replace("-", " ").split())
    return _DIGIT_SEP.sub(".", text)


SCORER_VERSION = "2"
"""Bump when matching changes: scores from two scorer versions are not comparable."""


def _value_group_key(pred: Requirement) -> tuple[str, str]:
    if pred.numeric_value is not None:
        return pred.field.value, f"{pred.numeric_value:g}"
    return pred.field.value, _comparable(pred.value)


def group_predictions(predicted: Sequence[Requirement]) -> list[list[Requirement]]:
    """One group per field and comparable value.

    Answer keys list each value once per tender, while the sheet repeats it for
    every scope that states it ("PVC" in three articles). Scoring groups keeps
    a repeated correct value from inflating precision and a repeated wrong one
    from counting three times.
    """
    groups: dict[tuple[str, str], list[Requirement]] = {}
    for pred in predicted:
        groups.setdefault(_value_group_key(pred), []).append(pred)
    return list(groups.values())


def _group_matches(group: Sequence[Requirement], exp: Expected, *, strict: bool) -> bool:
    return any(matches(p, exp, strict=strict) for p in group)


def match_pairs(
    groups: Sequence[Sequence[Requirement]], expected: Sequence[Expected], *, strict: bool
) -> dict[int, int]:
    """Maximum one-to-one matching, as {expected index: group index}.

    A prediction can state at most one expected requirement, and an expected
    requirement is found by at most one prediction, so one long value that
    contains two expected values is credited once. Kuhn's augmenting paths:
    a tender has at most a few hundred values, so this is instant.
    """
    edges = [
        [g for g, group in enumerate(groups) if _group_matches(group, exp, strict=strict)]
        for exp in expected
    ]
    owner: dict[int, int] = {}  # group index -> expected index

    def augment(e: int, seen: set[int]) -> bool:
        for g in edges[e]:
            if g in seen:
                continue
            seen.add(g)
            if g not in owner or augment(owner[g], seen):
                owner[g] = e
                return True
        return False

    for e in range(len(expected)):
        augment(e, set())
    return {e: g for g, e in owner.items()}


def score(
    predicted: list[Requirement], expected: list[Expected], *, strict: bool = False
) -> tuple[int, list[Expected], list[Requirement], int]:
    """Return (found, misses, extras, scored predictions) under one-to-one matching.

    Extras are one representative per unmatched value group; ``scored`` is the
    number of value groups, the denominator of precision.
    """
    groups = group_predictions(predicted)
    pairs = match_pairs(groups, expected, strict=strict)
    used = set(pairs.values())
    misses = [e for i, e in enumerate(expected) if i not in pairs]
    extras = [group[0] for g, group in enumerate(groups) if g not in used]
    return len(pairs), misses, extras, len(groups)


def field_counts(predicted: list[Requirement], expected: list[Expected]) -> dict[str, FieldCounts]:
    """Strict per-field counts: where recall is lost and where noise comes from."""
    groups = group_predictions(predicted)
    pairs = match_pairs(groups, expected, strict=True)
    used = set(pairs.values())
    counts: dict[str, FieldCounts] = {}
    for i, exp in enumerate(expected):
        c = counts.setdefault(exp.field.value, FieldCounts())
        c.expected += 1
        c.found += i in pairs
    for g, group in enumerate(groups):
        c = counts.setdefault(group[0].field.value, FieldCounts())
        c.predicted += 1
        c.correct += g in used
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

    started = datetime.now(UTC)
    llm = create_llm(settings.llm_model, settings)
    embedder = create_embedder(settings.embedding_model, settings)
    key_files: list[Path] = []
    cases: list[CaseReport] = []
    all_misses: list[str] = []
    try:
        for case_dir in sorted(p for p in golden_dir.iterdir() if p.is_dir()):  # noqa: ASYNC240
            source = next((case_dir / n for n in SOURCE_NAMES if (case_dir / n).exists()), None)
            if source is None or not (case_dir / "expected.json").exists():
                continue
            key_files.append(case_dir / "expected.json")
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
            tp, misses, extras, scored = score(predicted, expected)
            strict_tp, _, strict_extras, _ = score(predicted, expected, strict=True)
            correct_preds = scored - len(extras)
            strict_correct = scored - len(strict_extras)
            precision = _ratio(correct_preds, scored)
            recall = _ratio(tp, len(expected))
            strict_precision = _ratio(strict_correct, scored)
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
                    predicted=scored,
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
    model = llm.name if llm else "rules"
    manifest = RunManifest(
        scorer_version=SCORER_VERSION,
        package_version=__version__,
        git_commit=git_commit(),
        keys_sha256=keys_digest(key_files),
        cases=len(cases),
        model=model,
        embedding_model=settings.embedding_model,
        started_at=started,
    )
    return EvalReport(
        model=model,
        manifest=manifest,
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
