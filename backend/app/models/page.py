"""Page ORM model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.json_text import JSONText

if TYPE_CHECKING:
    from app.models.document import Document


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[JSONText] = mapped_column(JSONText, default=dict)

    document: Mapped[Document] = relationship("Document", back_populates="pages")

    def __repr__(self) -> str:
        return f"<Page {self.page_number} of {self.document_id}>"
