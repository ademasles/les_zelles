from __future__ import annotations

import asyncio
import importlib
import sys
import types


def _install_optional_dependency_stubs() -> None:
    fitz_module = types.ModuleType("fitz")
    docx_module = types.ModuleType("docx")
    docx_module.Document = lambda *args, **kwargs: types.SimpleNamespace(paragraphs=[])

    pil_module = types.ModuleType("PIL")
    pil_module.__path__ = []
    pil_image_module = types.ModuleType("PIL.Image")
    pil_module.Image = pil_image_module

    pytesseract_module = types.ModuleType("pytesseract")
    pytesseract_module.image_to_string = lambda *args, **kwargs: ""

    sys.modules.setdefault("fitz", fitz_module)
    sys.modules.setdefault("docx", docx_module)
    sys.modules.setdefault("PIL", pil_module)
    sys.modules.setdefault("PIL.Image", pil_image_module)
    sys.modules.setdefault("pytesseract", pytesseract_module)


def test_extract_text_from_file_falls_back_to_utf8_text():
    _install_optional_dependency_stubs()

    extraction = importlib.import_module("preprocessing.extraction")
    result = asyncio.run(extraction.extract_text_from_file(b"Bonjour le monde", "note.txt"))

    assert result == [{"doc_name": "note.txt", "page_number": None, "text": "Bonjour le monde"}]
