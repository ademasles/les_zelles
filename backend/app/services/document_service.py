"""Service for document-related operations like summarization."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.ollama_client import OllamaClient
from app.rag.prompts import build_summary_prompt
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm_client = OllamaClient()
        self.chunk_repo = ChunkRepository(self.db)
        self.doc_repo = DocumentRepository(self.db)

    async def generate_and_save_summary(self, document_id: str) -> str:
        """
        Generates a summary for a document, saves it, and returns it.
        If a summary already exists, it returns the existing one.
        """
        doc = await self.doc_repo.get(document_id)
        if not doc:
            raise ValueError("Document not found")

        if doc.summary:
            return doc.summary

        chunks = await self.chunk_repo.get_by_document(document_id)
        if not chunks:
            return "No content available to summarize."

        full_text = "\n".join(c.text for c in chunks if c.text)
        if not full_text.strip():
            return "No textual content available to summarize."

        prompt, _ = build_summary_prompt(full_text)
        summary = self.llm_client.generate(prompt)

        doc.summary = summary
        await self.doc_repo.update_document(doc)

        return summary
