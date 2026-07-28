"""Service for handling questions and answers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.ollama_client import OllamaClient
from app.rag.retriever import Retriever
from app.repositories.answer_repository import AnswerRepository, QuestionRepository
from app.repositories.document_repository import DocumentRepository
from app.services.rag_service import answer_question


class QuestionService:
    def __init__(self, db: AsyncSession, retriever: Retriever):
        self.db = db
        self.retriever = retriever
        self.llm_client = OllamaClient()
        self.question_repo = QuestionRepository(self.db)
        self.answer_repo = AnswerRepository(self.db)
        self.doc_repo = DocumentRepository(self.db)

    async def ask_question_on_document(
        self, question_text: str, document_id: str, project_id: str
    ) -> dict[str, Any]:
        # 1. Get the answer from the RAG service
        rag_result = await answer_question(
            question=question_text,
            retriever=self.retriever,
            llm=self.llm_client,
            db=self.db,
            document_id=document_id,
            project_id=project_id,
        )

        # 2. Persist the question and the answer with its citations
        question = await self.question_repo.create(
            project_id=project_id,
            question_text=question_text,
            document_id=document_id,
        )

        await self.answer_repo.create_answer_with_citations(
            question_id=question.id,
            answer_text=rag_result.get("answer"),
            model_name=rag_result.get("model_name"),
            prompt_version=rag_result.get("prompt_version"),
            evidence_quality=rag_result.get("evidence_quality"),
            latency_ms=rag_result.get("latency_ms"),
            citations=rag_result.get("citations"),
        )

        return rag_result

    async def run_predefined_queries(self, document_id: str) -> dict[str, Any]:
        doc = await self.doc_repo.get(document_id)
        if not doc or not doc.project_id:
            raise ValueError("Document or associated project not found")

        queries_file = Path(settings.queries_path)
        if not queries_file.exists():
            return {}

        queries: dict[str, str] = json.loads(queries_file.read_text(encoding="utf-8"))
        results: dict[str, Any] = {}

        for q_label, q_text in queries.items():
            rag_result = await self.ask_question_on_document(q_text, document_id, doc.project_id)
            # Reformat to legacy response structure for the frontend
            results[q_label] = {
                "question": q_text,
                "best_answer": rag_result.get("answer"),
                "alternatives": [
                    {
                        "response": c.get("quote", ""),
                        "score": c.get("score", 0),
                        "summary": "",
                        "page_number": c.get("page_start"),
                        "chunk_id": c.get("chunk_id", ""),
                        "chunk_text": c.get("quote", ""),
                        "bboxes": c.get("bboxes", []),
                    }
                    for c in rag_result.get("citations", [])
                ],
            }
        return results
