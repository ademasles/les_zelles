"""SQLAlchemy ORM models for Analyse-DCE.

Import all models here so SQLAlchemy metadata discovers them.
"""

from __future__ import annotations

from app.models.answer import Answer, AnswerCitation
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.json_text import JSONText
from app.models.page import Page
from app.models.processing_job import ProcessingJob
from app.models.project import Project
from app.models.question import Question

__all__ = [
    "JSONText",
    "Project",
    "Document",
    "ProcessingJob",
    "Page",
    "Chunk",
    "Question",
    "Answer",
    "AnswerCitation",
    "Feedback",
]
