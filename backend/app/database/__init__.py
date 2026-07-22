"""Database package for Analyse-DCE backend."""

from __future__ import annotations

# Import all models so SQLAlchemy metadata discovers them for table creation.
import app.models  # noqa: F401
from app.database.base import Base
from app.database.session import get_db, init_db

__all__ = [
    "Base",
    "get_db",
    "init_db",
]
