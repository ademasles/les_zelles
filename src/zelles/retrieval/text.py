"""French-aware tokenization for lexical search."""

from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    [
        "a",
        "au",
        "aux",
        "avec",
        "ce",
        "ces",
        "dans",
        "de",
        "des",
        "du",
        "elle",
        "en",
        "et",
        "eux",
        "il",
        "je",
        "la",
        "le",
        "les",
        "leur",
        "lui",
        "ma",
        "mais",
        "me",
        "même",
        "mes",
        "moi",
        "mon",
        "ne",
        "nos",
        "notre",
        "nous",
        "on",
        "ou",
        "par",
        "pas",
        "pour",
        "qu",
        "que",
        "qui",
        "sa",
        "se",
        "ses",
        "son",
        "sur",
        "ta",
        "te",
        "tes",
        "toi",
        "ton",
        "tu",
        "un",
        "une",
        "vos",
        "votre",
        "vous",
        "c",
        "d",
        "j",
        "l",
        "m",
        "n",
        "s",
        "t",
        "y",
        "été",
        "être",
        "est",
        "sont",
        "sera",
        "seront",
        "ainsi",
        "afin",
        "selon",
        "tout",
        "tous",
        "toute",
        "toutes",
        "the",
        "of",
        "and",
        "or",
        "to",
        "in",
        "for",
    ]
)
_TOKEN = re.compile(r"[a-z0-9]+(?:[*/.,][a-z0-9]+)*")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def stem(token: str) -> str:
    """Very light French stemmer: plural and common suffixes only."""
    if len(token) <= 3 or token[0].isdigit():
        return token
    for suffix in (
        "ements",
        "ement",
        "ations",
        "ation",
        "iques",
        "ique",
        "eaux",
        "aux",
        "es",
        "s",
        "x",
        "e",
    ):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN.findall(fold(text)):
        if raw in STOPWORDS:
            continue
        tokens.append(stem(raw))
        if any(ch in raw for ch in "*/.,"):  # also index the parts of "a*3", "4/16/4"
            tokens.extend(p for p in re.split(r"[*/.,]", raw) if p and p not in STOPWORDS)
    return tokens
