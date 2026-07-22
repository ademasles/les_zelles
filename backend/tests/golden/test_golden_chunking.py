"""Golden-file tests for Markdown-aware chunking.

Tests verify the chunker produces expected section structure, heading paths,
and metadata. These tests do NOT require a live parser or LLM.
"""

from __future__ import annotations

from pathlib import Path

from app.preprocessing.markdown.section_splitter import chunk_markdown

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_chunking_detects_headings() -> None:
    md = _load_fixture("sample_cctp.md")
    chunks = chunk_markdown(md, document_id="golden-test-doc")

    assert len(chunks) >= 5
    assert all(c["document_id"] == "golden-test-doc" for c in chunks)
    assert all(c["chunk_index"] >= 0 for c in chunks)
    assert all(c["token_count"] is not None for c in chunks)


def test_chunking_preserves_heading_path() -> None:
    md = _load_fixture("sample_cctp.md")
    chunks = chunk_markdown(md)

    paths = {c["section_title"]: c["heading_path"] for c in chunks}

    assert paths.get("Article 1 - Objet") == [
        "CCTP Menuiseries Extérieures",
        "Article 1 - Objet",
    ]
    assert paths.get("2.1 Classement AEV") == [
        "CCTP Menuiseries Extérieures",
        "Article 2 - Performances",
        "2.1 Classement AEV",
    ]


def test_chunking_includes_table_content() -> None:
    md = _load_fixture("sample_cctp.md")
    chunks = chunk_markdown(md)

    aev_chunks = [c for c in chunks if "Classement AEV" in c["section_title"]]
    assert len(aev_chunks) >= 1

    aev_text = aev_chunks[0]["text"]
    assert "A4" in aev_text
    assert "Perméabilité" in aev_text
    assert "Classe 4" in aev_text


def test_chunking_flat_markdown_no_headings() -> None:
    text = "Premier paragraphe.\n\nDeuxième paragraphe.\n\nTroisième paragraphe."
    chunks = chunk_markdown(text, document_id="flat-doc")

    assert len(chunks) >= 1
    assert chunks[0]["section_title"] == ""
    assert chunks[0]["heading_path"] == []


def test_chunking_oversized_section() -> None:
    large_section = "# Big Section\n\n" + "Mot " * 4000
    chunks = chunk_markdown(large_section, document_id="big-doc")

    assert len(chunks) >= 2
    assert all(c["section_title"] == "Big Section" for c in chunks)
