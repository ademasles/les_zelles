from pathlib import Path

import pytest

from zelles.config import Settings
from zelles.domain.spec import Citation, Requirement, SpecField
from zelles.evaluation.harness import (
    CaseReport,
    Expected,
    bootstrap_f1,
    field_counts,
    matches,
    micro_f1,
    run_eval,
)

from .conftest import ROOT


async def test_rules_only_baseline(settings: Settings) -> None:
    report = await run_eval(ROOT / "evals" / "golden", settings)
    assert report.model == "rules"
    assert report.cases and report.f1 >= 0.9
    assert report.strict_f1 <= report.f1
    assert report.f1_ci[0] <= report.f1 <= report.f1_ci[1]


def _req(value: str, quote: str) -> Requirement:
    return Requirement(
        field=SpecField.FINISH, value=value, citation=Citation(chunk_id="c1", quote=quote)
    )


def test_strict_match_ignores_the_quote() -> None:
    expected = Expected(field=SpecField.FINISH, value="RAL 9016")
    garbled = _req(
        "laqué blanc placé entre 0", "Profilés laqués blanc RAL 9016 placés entre 0,90 m"
    )
    clean = _req("laqué RAL 9016", "Profilés laqués blanc RAL 9016")
    assert matches(garbled, expected)
    assert not matches(garbled, expected, strict=True)
    assert matches(clean, expected, strict=True)


def test_strict_match_ignores_gender_agreement() -> None:
    expected = Expected(field=SpecField.FINISH, value="teintées dans la masse")
    assert matches(_req("teinté dans la masse", "PVC teinté dans la masse"), expected, strict=True)
    assert not matches(_req("teinte grise", "teinte grise"), expected, strict=True)


def test_strict_match_ignores_code_dots_and_spelling_variants() -> None:
    nv = Expected(field=SpecField.FINISH, value="NV 65")
    assert matches(_req("Règles NV.65", "Règles NV.65"), nv, strict=True)
    assert not matches(_req("NV 84", "NV 84"), nv, strict=True)
    limiter = Expected(field=SpecField.FINISH, value="limiteur de débattement")
    assert matches(_req("limitateur de débattement", "x"), limiter, strict=True)


def test_field_counts_split_misses_and_extras() -> None:
    expected = [
        Expected(field=SpecField.FINISH, value="RAL 9016"),
        Expected(field=SpecField.FINISH, value="anodisé"),
    ]
    predicted = [
        _req("laqué RAL 9016", "Profilés laqués blanc RAL 9016"),
        _req("brut", "Profilés bruts"),
    ]
    finish = field_counts(predicted, expected)["finish"]
    assert (finish.expected, finish.found, finish.misses) == (2, 1, 1)
    assert (finish.predicted, finish.correct, finish.extras) == (2, 1, 1)


async def test_blinded_report_keeps_counts_only(settings: Settings) -> None:
    report = await run_eval(ROOT / "evals" / "golden", settings)
    blind = report.blinded()
    dumped = blind.model_dump_json()
    assert "residence_tilleuls" not in dumped
    assert blind.fields == report.fields and blind.strict_f1 == report.strict_f1
    assert all(not c.misses and not c.extras for c in blind.cases)


def _case(name: str, predicted: int, expected: int, correct: int) -> CaseReport:
    p, r = correct / predicted, correct / expected
    f1 = 2 * p * r / (p + r)
    return CaseReport(
        name=name,
        predicted=predicted,
        expected=expected,
        true_positives=correct,
        correct_predictions=correct,
        strict_true_positives=correct,
        strict_correct_predictions=correct,
        precision=p,
        recall=r,
        f1=f1,
        strict_precision=p,
        strict_recall=r,
        strict_f1=f1,
        grounded_rate=1.0,
        cost_usd=0.0,
        seconds=0.0,
    )


def test_bootstrap_interval_spans_the_case_spread() -> None:
    cases = [_case("a", 10, 10, 10), _case("b", 10, 10, 5), _case("c", 20, 20, 18)]
    low, high = bootstrap_f1(cases)
    assert low < micro_f1(cases)[2] < high
    assert low >= 0.5 and high <= 1.0
    assert bootstrap_f1(cases) == (low, high)  # seeded, so reproducible
    assert bootstrap_f1([cases[0]]) == (1.0, 1.0)


async def test_mcp_server_exposes_tools(settings: Settings) -> None:
    pytest.importorskip("mcp")
    from zelles.mcp_server import build_server

    server = build_server(settings)
    tools = {t.name for t in await server.list_tools()}
    assert {"analyze_file", "search_passages", "check_product", "graph_neighbors"} <= tools


def test_cli_analyze(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from zelles.cli import app
    from zelles.config import get_settings

    monkeypatch.setenv("ZELLES_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ZELLES_OCR_ENABLED", "false")
    get_settings.cache_clear()
    out = tmp_path / "sheet.xlsx"
    result = CliRunner().invoke(
        app, ["analyze", str(ROOT / "evals/golden/residence_tilleuls/cctp.md"), "-o", str(out)]
    )
    get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert out.exists() and "Saved as document" in result.output
