# database.py
"""Database module for managing projects, queries, and answers in the text analysis service.
Uses SQLAlchemy ORM with SQLite as the backend.
Includes models for:
- Project: document metadata and summary
- Query: user questions
- Answer: AI responses (including alternatives)
"""

# -----------------------------------------------------------------------------------------------
# IMPORTS
# -----------------------------------------------------------------------------------------------
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

from app.core.config import settings

# -----------------------------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------------------------
DATABASE_URL = settings.database_url

if DATABASE_URL.startswith("sqlite:///"):
    sqlite_path = Path(DATABASE_URL.removeprefix("sqlite:///"))
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------------------------------------------------------------------------
# MODELS
# -----------------------------------------------------------------------------------------------


class Project(Base):
    """Project containing uploaded document information and summary."""

    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)  # doc_id
    name = Column(String)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(UTC))
    summary = Column(Text)
    csv = Column(Text)

    # Relations
    queries = relationship("Query", back_populates="project", cascade="all, delete-orphan")

    def as_dict(self):
        """
        Convert project to dictionary for serialization.
        :return: Dictionary representation of the project.
        """

        return {
            "id": self.id,
            "name": self.name,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "summary": self.summary,
            "csv": self.csv,
        }


class Query(Base):
    """User-defined question for a project."""

    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    question = Column(Text, nullable=False)
    best_answer = Column(Text)

    # Relations
    project = relationship("Project", back_populates="queries")
    answers = relationship("Answer", back_populates="query", cascade="all, delete-orphan")


class Answer(Base):
    """Individual AI-generated answer (alternative) for a query."""

    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey("queries.id"), nullable=False)
    response = Column(Text, nullable=False)
    score = Column(Float)
    summary = Column(Text)
    doc_name = Column(String)
    page_number = Column(Integer)
    chunk_id = Column(Integer)
    excerpt = Column(Text)

    # Relation
    query = relationship("Query", back_populates="answers")


# -----------------------------------------------------------------------------------------------
# INITIALIZE
# -----------------------------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)
