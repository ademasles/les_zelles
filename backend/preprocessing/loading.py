# loading.py
"""Load queries from a JSON file.
This module provides a function to load queries from a JSON file and return them as a dictionary.
It uses the `json` library to read the file and parse its content.
"""
# SPDX-FileCopyrightText: 2025 Anton Demasles <

#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
from typing import Dict, Any, Union, List
import json
from pathlib import Path

#-----------------------------------------------------------------------------------------------
# FUNCTIONS
#-----------------------------------------------------------------------------------------------
def load_queries(path: Union[str, Path] = "queries.json") -> Dict[str, Union[str, List[str], Dict[str, Any]]]:
    """
    Load queries from a JSON file.
    :param path: Path to the JSON file containing queries.
    :return: Dictionary with queries.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path.resolve()}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


