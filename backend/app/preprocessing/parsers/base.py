"""Parser interface and parsed document data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedBlock:
    id: str
    text: str
    block_type: str = "unknown"
    page_number: int | None = None
    heading_path: list[str] = field(default_factory=list)
    bbox: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedPage:
    page_number: int
    text: str
    markdown: str | None = None
    blocks: list[ParsedBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedTable:
    id: str
    markdown: str
    page_number: int | None = None
    bbox: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    source_path: Path
    parser_name: str
    parser_version: str | None = None
    markdown: str = ""
    structured_data: dict[str, Any] = field(default_factory=dict)
    pages: list[ParsedPage] = field(default_factory=list)
    blocks: list[ParsedBlock] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parsing_stats: dict[str, Any] = field(default_factory=dict)


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDocument:
        ...
