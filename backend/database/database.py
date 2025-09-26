# database.py
"""Database module for managing projects, queries, and answers in the text analysis service.
Uses SQLAlchemy ORM with SQLite as the backend.
Includes models for:
- Project: document metadata and summary
- Query: user questions
- Answer: AI responses (including alternatives)
"""
# SPDX-FileCopyrightText: 2025 Anton Demasles <

# -----------------------------------------------------------------------------------------------
# IMPORTS
# -----------------------------------------------------------------------------------------------
from sqlalchemy import (
    create_engine, Column, String, Text, DateTime, ForeignKey, Float, Integer
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone

# -----------------------------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------------------------
DATABASE_URL = "sqlite:///./projects.db"

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
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
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
