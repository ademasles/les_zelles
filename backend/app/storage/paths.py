from pathlib import Path
from app.core.config import settings
import os

def _get_base_path(project_id: str, document_id: str) -> Path:
    base = settings.storage_dir / "projects" / project_id / "documents" / document_id
    base_resolved = base.resolve()

    # Path traversal protection
    storage_root = settings.storage_dir.resolve()
    if not str(base_resolved).startswith(str(storage_root)):
        raise ValueError("Path traversal detected")

    return base_resolved

def get_raw_path(project_id: str, document_id: str, filename: str) -> Path:
    base = _get_base_path(project_id, document_id)
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = (raw_dir / filename).resolve()
    if not str(file_path).startswith(str(raw_dir)):
        raise ValueError("Path traversal detected in filename")
    return file_path

def get_parsed_markdown_path(project_id: str, document_id: str) -> Path:
    base = _get_base_path(project_id, document_id)
    parsed_dir = base / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    return parsed_dir / "document.md"

def get_parsed_json_path(project_id: str, document_id: str) -> Path:
    base = _get_base_path(project_id, document_id)
    parsed_dir = base / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    return parsed_dir / "document.json"
