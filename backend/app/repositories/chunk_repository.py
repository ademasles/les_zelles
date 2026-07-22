"""Chunk repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_chunks(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            self.session.add(chunk)
        await self.session.flush()

    async def get_by_document(self, document_id: str) -> list[Chunk]:
        result = await self.session.execute(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )
        return list(result.scalars().all())

    async def delete_by_document(self, document_id: str) -> None:
        chunks = await self.get_by_document(document_id)
        for chunk in chunks:
            await self.session.delete(chunk)
        await self.session.flush()
