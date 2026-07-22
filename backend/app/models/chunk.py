"""Chunk ORM model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.json_text import JSONText

if TYPE_CHECKING:
    from app.models.answer import AnswerCitation
    from app.models.document import Document


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    heading_path_json: Mapped[JSONText] = mapped_column(JSONText, default=list)
    source_block_ids_json: Mapped[JSONText] = mapped_column(JSONText, default=list)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[JSONText] = mapped_column(JSONText, default=dict)

    document: Mapped[Document] = relationship("Document", back_populates="chunks")
    answer_citations: Mapped[list[AnswerCitation]] = relationship(
        "AnswerCitation", back_populates="chunk", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Chunk {self.chunk_index} of {self.document_id}>"
