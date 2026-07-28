"""API client for Streamlit frontend — centralized HTTP calls to the backend.

This is a standalone module. It does NOT import from the backend package.

Defaults to localhost for local dev. Override via BACKEND_URL env var.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

API_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")


def health() -> dict[str, str]:
    resp = requests.get(f"{API_URL}/api/health", timeout=5)
    resp.raise_for_status()
    return resp.json()


def upload_file(file_content: bytes, filename: str, doc_id: str) -> dict[str, Any]:
    resp = requests.post(
        f"{API_URL}/upload/",
        files={"file": (filename, file_content)},
        data={"doc_id": doc_id},
        timeout=3000,
    )
    resp.raise_for_status()
    return resp.json()


def run_queries(doc_id: str) -> dict[str, Any]:
    resp = requests.post(
        f"{API_URL}/queries/",
        data={"doc_id": doc_id},
        timeout=1200,
    )
    resp.raise_for_status()
    return resp.json()


def ask_question(doc_id: str, question: str) -> dict[str, Any]:
    resp = requests.post(
        f"{API_URL}/query/",
        data={"doc_id": doc_id, "question": question},
        timeout=1200,
    )
    resp.raise_for_status()
    return resp.json()


def save_project(doc_id: str, name: str, results_json: str) -> dict[str, Any]:
    resp = requests.post(
        f"{API_URL}/save/",
        data={"doc_id": doc_id, "name": name, "results": results_json},
        timeout=3000,
    )
    resp.raise_for_status()
    return resp.json()


def add_question_to_project(doc_id: str, question: str, result_json: str) -> dict[str, Any]:
    resp = requests.post(
        f"{API_URL}/project_queries/add",
        data={"doc_id": doc_id, "question": question, "result": result_json},
        timeout=3000,
    )
    resp.raise_for_status()
    return resp.json()


def list_projects() -> list[dict[str, Any]]:
    resp = requests.get(f"{API_URL}/projects/", timeout=3000)
    resp.raise_for_status()
    return resp.json()


def get_project_queries(doc_id: str) -> dict[str, Any]:
    resp = requests.get(f"{API_URL}/project_queries/{doc_id}", timeout=3000)
    resp.raise_for_status()
    return resp.json()


def get_summary(doc_id: str) -> dict[str, Any]:
    resp = requests.get(f"{API_URL}/summary/", params={"doc_id": doc_id}, timeout=3000)
    resp.raise_for_status()
    return resp.json()


def submit_feedback(question: str, response: str, score: float) -> dict[str, Any]:
    resp = requests.post(
        f"{API_URL}/feedback/",
        json={"question": question, "response": response, "score": score},
        timeout=3000,
    )
    resp.raise_for_status()
    return resp.json()
