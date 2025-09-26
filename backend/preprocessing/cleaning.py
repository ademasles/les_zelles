# cleaning.py
"""Cleaning module for text normalization and standardization.
This module provides functions to clean and normalize text extracted from various sources.
It includes functions to remove invisible characters, normalize line endings, and apply common typographic replacements.
It also handles Unicode normalization and standard text cleaning.
"""
# SPDX-FileCopyrightText: 2025 Anton Demasles <

#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
import re
import unicodedata
from typing import List, Dict, Union

#-----------------------------------------------------------------------------------------------
# FUNCTIONS
#-----------------------------------------------------------------------------------------------
def clean_text(text: str) -> str:
    """
    Clean and normalize text by applying various transformations /
    - Unicode normalization
    - Common typographic replacements
    - Standard text cleaning (removing invisible characters, normalizing line endings, etc.)
        
    :param text: The text to clean.
    :return: The cleaned text.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Unicode normalisation
    text = unicodedata.normalize("NFKC", text)

    # 2. Remplacements typographiques courants
    replacements = {
        "•": "-",
        "·": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "’": "'",
        "“": '"',
        "”": '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace("\u00A0", " ")  # espace insécable → espace normal


    # 3. Nettoyage standard
    text = re.sub(r"[\x00-\x1F\x7F]", " ", text)            # caractères invisibles
    text = re.sub(r"\r", "\n", text)                        # CR → LF
    text = re.sub(r"[ \t]{2,}", " ", text)                  # espaces multiples → un espace
    text = re.sub(r"\n{2,}", "\n\n", text)                  # max 2 retours ligne
    text = re.sub(r" +\n", "\n", text)                      # pas d'espaces en fin de ligne
    text = re.sub(r"([.,;:!?])(?=[A-Za-z])", r"\1 ", text)  # pas d'espace avant ponctuation
    text = re.sub(r"([.,;:!?])(?=\w)", r"\1 ", text)        # espace après ponctuation si manquant

    return text.strip()

#-----------------------------------------------------------------------------------------------
def clean_pages(pages: List[Dict[str, Union[str, int]]]) -> List[Dict[str, Union[str, int]]]:
    """
    Clean the text in each page of the extracted text.
    :param pages: List of dictionaries with document name, page number, and extracted text.
    :return: List of dictionaries with cleaned text.
    """
    for page in pages:
        page["text"] = clean_text(page["text"])
    return pages
