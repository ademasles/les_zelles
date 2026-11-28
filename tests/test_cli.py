"""The command line: results go where the user asked, or it says why not before working."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from typer.testing import CliRunner

from zelles.cli import app

CCTP = (
    "# 2 Menuiseries extérieures\n\n"
    "## 2.1 Fenêtres PVC M1\n\n"
    "Fenêtres en PVC blanc, Uw ≤ 1,3 W/m².K.\n"
)


def _run(tmp_path: Path, *args: str) -> tuple[int, str]:
    source = tmp_path / "cctp.md"
    source.write_text(CCTP, encoding="utf-8")
    env = {"ZELLES_LLM_MODEL": "none", "ZELLES_EMBEDDING_MODEL": "none", "COLUMNS": "200"}
    result = CliRunner().invoke(app, ["analyze", str(source), "--no-save", *args], env=env)
    return result.exit_code, result.output


def test_the_recap_is_written(tmp_path: Path) -> None:
    target = tmp_path / "recap.xlsx"
    code, _ = _run(tmp_path, "--recap", str(target))
    assert code == 0
    assert load_workbook(target).sheetnames[0] == "Recap"


def test_a_missing_folder_fails_before_the_analysis(tmp_path: Path) -> None:
    code, out = _run(tmp_path, "--recap", str(tmp_path / "nowhere" / "recap.xlsx"))
    assert code != 0
    assert "does not exist" in out
    assert "Frame material" not in out  # the sheet was never printed: nothing ran


def test_a_wrong_extension_fails_before_the_analysis(tmp_path: Path) -> None:
    code, out = _run(tmp_path, "--output", str(tmp_path / "sheet.pdf"))
    assert code != 0
    assert "Frame material" not in out
