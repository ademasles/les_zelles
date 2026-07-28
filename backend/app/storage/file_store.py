from pathlib import Path
from typing import Any
import json
from app.storage.paths import get_raw_path, get_parsed_markdown_path, get_parsed_json_path

def save_raw(project_id: str, document_id: str, filename: str, content: bytes) -> Path:
    file_path = get_raw_path(project_id, document_id, filename)
    file_path.write_bytes(content)
    return file_path

def save_markdown(project_id: str, document_id: str, content: str) -> Path:
    file_path = get_parsed_markdown_path(project_id, document_id)
    file_path.write_text(content, encoding="utf-8")
    return file_path

def save_parsed_json(project_id: str, document_id: str, content: dict[str, Any]) -> Path:
    file_path = get_parsed_json_path(project_id, document_id)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    return file_path
