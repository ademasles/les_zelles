"""FastAPI dependency providers."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.rag.retriever import Retriever


def get_retriever(request: Request) -> Retriever:
    """FastAPI dependency to get the singleton Retriever instance."""
    return request.app.state.retriever
