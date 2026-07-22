"""Answer and AnswerCitation ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.feedback import Feedback
    from app.models.question import Question


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id"), nullable=False, index=True
    )
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    question: Mapped[Question] = relationship("Question", back_populates="answers")
    citations: Mapped[list[AnswerCitation]] = relationship(
        "AnswerCitation", back_populates="answer", cascade="all, delete-orphan"
    )
    feedbacks: Mapped[list[Feedback]] = relationship(
        "Feedback", back_populates="answer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Answer {self.id[:8]}...>"


class AnswerCitation(Base):
    __tablename__ = "answer_citations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    answer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("answers.id"), nullable=False, index=True
    )
    chunk_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("chunks.id"), nullable=True
    )
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    answer: Mapped[Answer] = relationship("Answer", back_populates="citations")
    chunk: Mapped[Chunk | None] = relationship(
        "Chunk", back_populates="answer_citations"
    )

    def __repr__(self) -> str:
        return f"<AnswerCitation for {self.answer_id[:8]}...>"
