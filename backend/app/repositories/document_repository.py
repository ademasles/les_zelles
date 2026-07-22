"""Document repository."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        project_id: str,
        filename: str,
        content_type: str = "",
        storage_path: str | None = None,
    ) -> Document:
        doc = Document(
            project_id=project_id,
            filename=filename,
            content_type=content_type,
            storage_path=storage_path,
            status="uploaded",
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get(self, document_id: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_by_project(self, project_id: str) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        document_id: str,
        status: str,
        error_message: str | None = None,
        parser_name: str | None = None,
        parser_version: str | None = None,
        markdown_path: str | None = None,
        parsed_json_path: str | None = None,
    ) -> Document | None:
        doc = await self.get(document_id)
        if doc is None:
            return None
        doc.status = status
        if error_message is not None:
            doc.error_message = error_message
        if parser_name is not None:
            doc.parser_name = parser_name
        if parser_version is not None:
            doc.parser_version = parser_version
        if markdown_path is not None:
            doc.markdown_path = markdown_path
        if parsed_json_path is not None:
            doc.parsed_json_path = parsed_json_path
        if status in ("completed", "failed"):
            doc.processed_at = datetime.now(UTC)
        await self.session.flush()
        return doc
