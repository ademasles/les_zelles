# extraction.py
"""Extract text from various file types including PDF, DOCX, and images using OCR.
This module provides functions to extract text from PDF files, DOCX files, and images.
It uses the `pymupdf` library for PDF handling, `python-docx` for DOCX files, and `pytesseract` for OCR on images.
"""
# SPDX-FileCopyrightText: 2025 Anton Demasles <

#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
import asyncio
import fitz  # pymupdf
from docx import Document
import pytesseract
from PIL import Image
import io
from typing import List, Dict, Union

#-----------------------------------------------------------------------------------------------
# FUNCTIONS
#-----------------------------------------------------------------------------------------------
async def extract_text_from_file(content: bytes, filename) -> List[Dict[str, Union[str, int]]]:
    """
    Extract text from a file based on its type.
    :param content: File content as bytes.
    :param filename: Name of the file to determine its type.
    :return: List of dictionaries with document name, page number, and extracted text.
    """

    loop = asyncio.get_event_loop()

    if filename.lower().endswith(".pdf"):
        return await loop.run_in_executor(None, extract_text_pdf, content, filename)
    elif filename.lower().endswith(".docx"):
        return await loop.run_in_executor(None, extract_text_docx, content, filename)
    elif filename.lower().endswith((".png", ".jpg", ".jpeg", ".tiff")):
        return await loop.run_in_executor(None, extract_text_image, content, filename)
    else:
        return [{
            "doc_name": filename,
            "page_number": None,
            "text": content.decode('utf-8')
        }]
#-----------------------------------------------------------------------------------------------

def extract_text_pdf(data: bytes, filename="unknown.pdf", use_ocr_fallback=False) -> List[Dict[str, Union[str, int]]]:
    """
    Extract text from a PDF file, optionally using OCR for pages without text.
    :param data: PDF file content as bytes.
    :param filename: Name of the PDF file.
    :param use_ocr_fallback: If True, use OCR to extract text from pages without text.
    :return: List of dictionaries with document name, page number, and extracted text.
    """
    results = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        for page_number, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if not text and use_ocr_fallback:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes()))
                text = pytesseract.image_to_string(img, lang='fra')

            results.append({
                "doc_name": filename,
                "page_number": page_number,
                "text": text
            })
    except Exception as e:
        results.append({
            "doc_name": filename,
            "page_number": None,
            "text": f"[Erreur lors de l'extraction : {str(e)}]"
        })

    return results

#-----------------------------------------------------------------------------------------------

def extract_text_docx(data, filename="unknown.docx"):
    """
    Extract text from a DOCX file.
    :param data: DOCX file content as bytes.
    :param filename: Name of the DOCX file.
    :return: List of dictionaries with document name, page number, and extracted text.
    """
    doc = Document(io.BytesIO(data))
    texts = [para.text for para in doc.paragraphs if para.text.strip()]
    full_text = "\n".join(texts)

    return [{
        "doc_name": filename,
        "page_number": None,
        "text": full_text
    }]

#-----------------------------------------------------------------------------------------------
def extract_text_image(data, filename="image.jpg"):
    """
    Extract text from an image file using OCR.
    :param data: Image file content as bytes.
    :param filename: Name of the image file.
    :return: List of dictionaries with document name, page number, and extracted text.
    """
    image = Image.open(io.BytesIO(data))
    text = pytesseract.image_to_string(image, lang='fra')

    return [{
        "doc_name": filename,
        "page_number": None,
        "text": text
    }]
