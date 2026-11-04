"""Text normalization for extracted CCTP text.

Ported from the original prototype and fixed: punctuation spacing no longer
breaks decimals ('1,3' stays '1,3') or standard references ('NF EN 14351-1').
"""

from __future__ import annotations

import re
import unicodedata

_REPLACEMENTS = {
    "•": "-",
    "·": "-",
    "‐": "-",
    "‑": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "«": '"',
    "»": '"',
    " ": " ",
    " ": " ",
    "­": "",
}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")


def clean_text(text: str) -> str:
    """Normalize Unicode and whitespace while keeping line structure."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub(" ", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # words split across lines
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Missing space after ; : ! ? before a letter (not after . or , to keep decimals and refs).
    text = re.sub(r"([;:!?])(?=[A-Za-zÀ-ÿ])", r"\1 ", text)
    return text.strip()


def normalize_for_match(text: str) -> str:
    """Aggressive normalization used to compare a quote with its source."""
    text = clean_text(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w*/.,%-]+", " ", text)
    return " ".join(text.split())
