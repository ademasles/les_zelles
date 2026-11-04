"""Okapi BM25 over chunks. Pure Python, no index server, fast for one CCTP."""

from __future__ import annotations

import math
from collections import Counter

from zelles.retrieval.text import tokenize


class BM25:
    def __init__(self, documents: list[str], *, k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in documents]
        self.lengths = [sum(c.values()) for c in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        df: Counter[str] = Counter()
        for counts in self.docs:
            df.update(counts.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out: list[float] = []
        for counts, length in zip(self.docs, self.lengths, strict=True):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1.0))
            for term in terms:
                tf = counts.get(term)
                if tf:
                    score += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / (tf + norm)
            out.append(score)
        return out
