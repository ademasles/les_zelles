"""Processing service — orchestrates document parsing, chunking, embedding, indexing."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.preprocessing.markdown.section_splitter import chunk_markdown
from app.preprocessing.parsers.fallback import parse_with_fallback
from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import FaissVectorStore
from app.repositories.document_repository import DocumentRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.storage.file_store import save_markdown, save_parsed_json, save_raw

logger = logging.getLogger(__name__)


async def process_document(
    document_id: str,
    project_id: str,
    file_path: Path,
    filename: str,
    db: AsyncSession,
) -> None:
    doc_repo = DocumentRepository(db)
    job_repo = ProcessingJobRepository(db)

    job = await job_repo.create(document_id)

    try:
        await job_repo.update_status(job.id, "processing", current_step="parsing")
        await doc_repo.update_status(document_id, "processing")

        parsed = parse_with_fallback(file_path)

        save_raw(project_id, document_id, filename, file_path.read_bytes())
        md_path = save_markdown(project_id, document_id, parsed.markdown)
        json_path = save_parsed_json(project_id, document_id, parsed.structured_data)

        await doc_repo.update_status(
            document_id,
            "parsed",
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
            markdown_path=str(md_path),
            parsed_json_path=str(json_path),
        )

        await job_repo.update_status(job.id, "parsed", current_step="chunking")

        chunks = chunk_markdown(
            parsed.markdown,
            document_id=document_id,
        )

        await doc_repo.update_status(document_id, "chunked")
        await job_repo.update_status(job.id, "chunked", current_step="embedding")

        embedding_service = EmbeddingService()
        texts = [c["text"] for c in chunks]
        embeddings = embedding_service.embed_chunks(texts)

        vector_store = FaissVectorStore()
        vector_store.add_chunks(
            chunk_ids=[c.get("document_id", "") for c in chunks],
            embeddings=embeddings,
            metadata=chunks,
        )

        await doc_repo.update_status(document_id, "completed")
        await job_repo.update_status(job.id, "completed", current_step="done")

        logger.info("Document %s processed successfully", document_id)

    except Exception as e:
        logger.error("Processing failed for %s: %s", document_id, e)
        await doc_repo.update_status(document_id, "failed", error_message=str(e))
        await job_repo.update_status(job.id, "failed", error_message=str(e))
