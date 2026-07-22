"""API client for Streamlit frontend — centralized HTTP calls to the backend."""

from __future__ import annotations

import json
from typing import Any

import requests

from app.core.config import settings


def _api_url() -> str:
    return settings.backend_api_url


def health() -> dict[str, str]:
    resp = requests.get(f"{_api_url()}/api/health", timeout=5)
    resp.raise_for_status()
    return resp.json()


def create_project(name: str) -> dict[str, str]:
    resp = requests.post(
        f"{_api_url()}/projects/",
        json={"name": name},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def list_projects() -> list[dict[str, Any]]:
    resp = requests.get(f"{_api_url()}/projects/", timeout=10)
    resp.raise_for_status()
    return resp.json()


def upload_document(
    project_id: str,
    file_path: str,
    file_content: bytes,
    filename: str,
) -> dict[str, Any]:
    resp = requests.post(
        f"{_api_url()}/projects/{project_id}/documents/upload",
        files={"file": (filename, file_content)},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_document_status(document_id: str) -> dict[str, Any]:
    resp = requests.get(
        f"{_api_url()}/documents/{document_id}/status",
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def ask_question(project_id: str, question: str) -> dict[str, Any]:
    resp = requests.post(
        f"{_api_url()}/projects/{project_id}/questions",
        json={"question_text": question},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def get_document_summary(document_id: str) -> dict[str, Any]:
    resp = requests.get(
        f"{_api_url()}/documents/{document_id}/summary",
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def get_answer_evidence(answer_id: str) -> dict[str, Any]:
    resp = requests.get(
        f"{_api_url()}/answers/{answer_id}/evidence",
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def submit_feedback(answer_id: str, rating: float) -> dict[str, Any]:
    resp = requests.post(
        f"{_api_url()}/feedback",
        json={"answer_id": answer_id, "rating": rating},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
