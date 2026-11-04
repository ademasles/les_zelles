from __future__ import annotations

from pathlib import Path

import pytest

from zelles.config import Settings

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "evals" / "golden" / "residence_tilleuls" / "cctp.md"

_LATIN1 = {"≤": "<=", "≥": ">=", "œ": "oe", "Œ": "OE", "²": "2", "³": "3", "’": "'"}


@pytest.fixture
def sample_text() -> str:
    return SAMPLE.read_text(encoding="utf-8")


@pytest.fixture
def sample_bytes() -> bytes:
    return SAMPLE.read_bytes()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data", llm_model="none", embedding_model="none", ocr_enabled=False
    )


@pytest.fixture
def sample_pdf(sample_text: str) -> bytes:
    """The sample CCTP rendered as a real PDF (core font, so Latin-1 only)."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for raw in sample_text.splitlines():
        line = raw
        for old, new in _LATIN1.items():
            line = line.replace(old, new)
        if not line.strip():
            pdf.ln(4)
            continue
        pdf.multi_cell(
            0, 5, line.encode("latin-1", "replace").decode("latin-1"), new_x="LMARGIN", new_y="NEXT"
        )
    return bytes(pdf.output())
