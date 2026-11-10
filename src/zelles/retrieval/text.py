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


# Wording variants that do not change a requirement, shared by the scorer and
# the sheet's near-duplicate merge.
_ACRONYM = re.compile(r"\b((?:[a-z]+\.)+[a-z]+)\b\.?")  # "d.t.u." / "cer.f.f" -> "dtu" / "cerff"
_NF_PREFIX = re.compile(r"\bnf\s*\.\s*(?=[a-z])|\bnf(?=[abepsx]\s*\d)")  # "nf.p", "nfp 20"
_NUMERO = re.compile(r"\bn\s*[°º]\s*")  # "n°39", "n° 39"
_FIRST = re.compile(r"\b1er\b")  # "1er août" = "1 août"
_DIGIT_SEP = re.compile(r"(?<=\d)(?:\s*[.\-]\s*|,|\s+)(?=\d)")  # "20.501" = "20-501" = "20 501"
_UNIT_GLUE = re.compile(r"(?<=\d)(?=[a-z])")  # "37dB" = "37 dB"
_PLURAL = re.compile(r"\b([a-z]{4,})s\b")  # "thermolaqués" = "thermolaqué"
_FEMININE = re.compile(r"\b([a-z]{3,}e)e\b")  # "teintée" = "teinté" (accents already folded)
_LETTER_DOT_DIGIT = re.compile(r"(?<=[a-z])\.(?=\d)")  # "NV.65" = "NV 65"
_LETTER_DIGIT = re.compile(r"\b([a-z])(?=\d)")  # "P20-302" = "P 20-302"
# Spelling variants of one word, not synonyms: the requirement must be the same.
_VARIANTS = {"limitateur": "limiteur"}
_VARIANT = re.compile(r"\b(" + "|".join(_VARIANTS) + r")\b")


def comparable(text: str) -> str:
    """Normalise wording variants that do not change the requirement.

    Accents and case are folded, hyphens and stars become spaces ("warm-edge" =
    "warm edge"), dotted acronyms and "n°" are dropped ("D.T.U. n°39" = "DTU 39"),
    "1er" is "1", a dot between a code and its number is a space ("NV.65" =
    "NV 65") and a lone letter is split from its number ("P20" = "P 20"), spelling variants are unified ("limitateur" = "limiteur"), a unit may be glued to its number ("37dB" = "37 dB"), a
    plural "s" and a participle's feminine "e" are dropped ("teintées" = "teinté"),
    and digit groups compare equal whatever the separator ("NF P 20-501"
    contains "20.501").
    """
    text = fold(text)
    text = _ACRONYM.sub(lambda m: m.group(1).replace(".", "") + " ", text)
    text = _NF_PREFIX.sub("nf ", text)
    text = _NUMERO.sub("", text)
    text = _LETTER_DOT_DIGIT.sub(" ", text)
    text = _LETTER_DIGIT.sub(r"\1 ", text)
    text = _VARIANT.sub(lambda m: _VARIANTS[m.group(1)], text)
    text = _FIRST.sub("1", text)
    text = _UNIT_GLUE.sub(" ", text)
    text = _PLURAL.sub(r"\1", text)
    text = _FEMININE.sub(r"\1", text)
    text = " ".join(text.replace("*", " * ").replace("-", " ").split())
    return _DIGIT_SEP.sub(".", text)
