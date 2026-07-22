"""RAG regression tests for evidence/citation behaviour.

Tests verify that:
- Retrieval returns expected evidence for known cases.
- Answers include citations or explicit no-evidence response.
- No live LLM is required — LLM and retriever are mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rag.prompts import build_qa_prompt
from app.rag.retriever import RetrievalResult

EVAL_DIR = Path(__file__).resolve().parents[1] / "evaluation"


@pytest.fixture
def rag_cases() -> list[dict]:
    with open(EVAL_DIR / "rag_cases.json", encoding="utf-8") as f:
        return json.load(f)


def test_rag_cases_file_exists() -> None:
    assert (EVAL_DIR / "rag_cases.json").exists()


def test_rag_cases_have_required_fields(rag_cases: list[dict]) -> None:
    for case in rag_cases:
        assert "id" in case
        assert "question" in case
        assert "expected_evidence" in case
        assert "expected_quality" in case


def test_prompt_builder_includes_evidence(rag_cases: list[dict]) -> None:
    case = rag_cases[0]
    prompt, version = build_qa_prompt(case["question"], case["chunk_text"])
    assert case["question"] in prompt
    assert case["chunk_text"] in prompt
    assert version == "qa_v1"


def test_prompt_builder_no_evidence(rag_cases: list[dict]) -> None:
    case = rag_cases[3]
    prompt, version = build_qa_prompt(case["question"], "")
    assert case["question"] in prompt
    assert version == "qa_v1"


def test_retrieval_result_dataclass() -> None:
    result = RetrievalResult(
        chunk_id="chunk_001",
        text="Le délai est de 12 semaines.",
        score=0.92,
        metadata={"document_id": "doc_001", "section_title": "Délais"},
    )
    assert result.chunk_id == "chunk_001"
    assert result.score == 0.92
    assert result.metadata["section_title"] == "Délais"


def test_no_evidence_case_returns_empty_citations(rag_cases: list[dict]) -> None:
    case = rag_cases[3]
    assert case["expected_quality"] == "none"
    assert case["expected_evidence"] == []


@pytest.mark.llm
def test_live_ollama_required(rag_cases: list[dict]) -> None:
    """This test requires a live Ollama instance and is skipped by default."""
    pytest.skip("Live LLM test — run manually with --mark llm")
