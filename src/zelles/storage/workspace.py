"""The workspace: analysed documents on disk plus their metadata in the database.

Layout, per document (content-addressed id, so no user input reaches a path)::

    data/documents/<id>/original.<ext>
    data/documents/<id>/rendition.pdf      # for page images and highlights
    data/documents/<id>/document.json      # parsed blocks with boxes
    data/documents/<id>/chunks.json
    data/documents/<id>/vectors.npy        # only with an embedding model
    data/documents/<id>/sheet.json
    data/documents/<id>/graph.json
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import TypeAdapter
from sqlalchemy import select

from zelles.config import Settings
from zelles.domain.documents import Chunk, ParsedDocument
from zelles.domain.spec import SpecSheet
from zelles.graph.knowledge import KnowledgeGraph
from zelles.llm.base import Embedder
from zelles.pipeline import Analysis
from zelles.retrieval.index import DocumentIndex
from zelles.storage.db import DocumentRow, make_engine, migrate, session_factory

_ID = re.compile(r"^[0-9a-f]{16}$")
_CHUNKS = TypeAdapter(list[Chunk])


class DocumentNotFoundError(KeyError):
    pass


@dataclass
class LoadedDocument:
    """A stored analysis, ready for search, Q&A and tools (implements DocContext)."""

    document_id: str
    document: ParsedDocument
    chunks: list[Chunk]
    index: DocumentIndex
    sheet: SpecSheet
    graph: KnowledgeGraph


class Workspace:
    def __init__(
        self, settings: Settings, *, embedder: Embedder | None = None, cache_size: int = 16
    ) -> None:
        self.settings = settings
        self.root = settings.data_dir / "documents"
        self.root.mkdir(parents=True, exist_ok=True)
        url = settings.resolved_database_url
        migrate(url)
        self.engine = make_engine(url)
        self.sessions = session_factory(self.engine)
        self.embedder = embedder
        self._cache: OrderedDict[str, LoadedDocument] = OrderedDict()
        self._cache_size = cache_size

    # ------------------------------------------------------------------ paths
    def path(self, document_id: str) -> Path:
        if not _ID.match(document_id):
            raise DocumentNotFoundError(document_id)
        return self.root / document_id

    def exists(self, document_id: str) -> bool:
        try:
            return (self.path(document_id) / "sheet.json").exists()
        except DocumentNotFoundError:
            return False

    def rendition(self, document_id: str) -> Path | None:
        path = self.path(document_id) / "rendition.pdf"
        return path if path.exists() else None

    # ------------------------------------------------------------------ write
    def register(self, document_id: str, filename: str, media_type: str, data: bytes) -> None:
        folder = self.path(document_id)
        folder.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower() or ".bin"
        (folder / f"original{suffix}").write_bytes(data)
        with self.sessions.begin() as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                session.add(
                    DocumentRow(
                        id=document_id,
                        filename=filename,
                        media_type=media_type,
                        size_bytes=len(data),
                        status="pending",
                    )
                )
            else:
                row.filename, row.status = filename, "pending"

    def save(self, analysis: Analysis) -> None:
        folder = self.path(analysis.document_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "document.json").write_text(analysis.document.model_dump_json())
        (folder / "chunks.json").write_bytes(_CHUNKS.dump_json(analysis.chunks))
        if analysis.index.vectors is not None:
            np.save(folder / "vectors.npy", analysis.index.vectors)
        if analysis.rendition_pdf:
            (folder / "rendition.pdf").write_bytes(analysis.rendition_pdf)
        (folder / "sheet.json").write_text(analysis.sheet.model_dump_json(indent=2))
        (folder / "graph.json").write_text(analysis.graph.model_dump_json())
        with self.sessions.begin() as session:
            row = session.get(DocumentRow, analysis.document_id)
            if row is None:
                row = DocumentRow(
                    id=analysis.document_id,
                    filename=analysis.sheet.filename,
                    media_type=analysis.document.media_type,
                    size_bytes=0,
                )
                session.add(row)
            row.page_count = analysis.document.page_count
            row.model = analysis.sheet.model
            row.requirement_count = len(analysis.sheet.requirements)
            row.cost_usd = analysis.sheet.usage.cost_usd
            row.status = "ready"
        self._cache.pop(analysis.document_id, None)

    def mark_failed(self, document_id: str) -> None:
        with self.sessions.begin() as session:
            row = session.get(DocumentRow, document_id)
            if row is not None:
                row.status = "failed"

    # ------------------------------------------------------------------ read
    def list_documents(self) -> list[dict[str, Any]]:
        with self.sessions() as session:
            rows = session.scalars(
                select(DocumentRow).order_by(DocumentRow.created_at.desc())
            ).all()
            return [
                {
                    "id": r.id,
                    "filename": r.filename,
                    "status": r.status,
                    "pages": r.page_count,
                    "model": r.model,
                    "requirements": r.requirement_count,
                    "cost_usd": r.cost_usd,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    def sheet(self, document_id: str) -> SpecSheet:
        path = self.path(document_id) / "sheet.json"
        if not path.exists():
            raise DocumentNotFoundError(document_id)
        return SpecSheet.model_validate_json(path.read_text())

    async def load(self, document_id: str) -> LoadedDocument:
        if document_id in self._cache:
            self._cache.move_to_end(document_id)
            return self._cache[document_id]
        folder = self.path(document_id)
        if not (folder / "sheet.json").exists():
            raise DocumentNotFoundError(document_id)

        def _read() -> tuple[ParsedDocument, list[Chunk], SpecSheet, KnowledgeGraph, Any]:
            vectors_path = folder / "vectors.npy"
            return (
                ParsedDocument.model_validate_json((folder / "document.json").read_text()),
                _CHUNKS.validate_json((folder / "chunks.json").read_bytes()),
                SpecSheet.model_validate_json((folder / "sheet.json").read_text()),
                KnowledgeGraph.model_validate_json((folder / "graph.json").read_text()),
                np.load(vectors_path) if vectors_path.exists() else None,
            )

        document, chunks, sheet, graph, vectors = await asyncio.to_thread(_read)
        embedder = self.embedder if vectors is not None else None
        loaded = LoadedDocument(
            document_id, document, chunks, DocumentIndex(chunks, vectors, embedder), sheet, graph
        )
        self._cache[document_id] = loaded
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return loaded

    def write_json(self, document_id: str, name: str, payload: Any) -> None:
        (self.path(document_id) / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )
