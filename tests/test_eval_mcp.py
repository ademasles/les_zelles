from pathlib import Path

import pytest

from zelles.config import Settings
from zelles.evaluation.harness import run_eval

from .conftest import ROOT


async def test_rules_only_baseline(settings: Settings) -> None:
    report = await run_eval(ROOT / "evals" / "golden", settings)
    assert report.model == "rules"
    assert report.cases and report.f1 >= 0.9


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
