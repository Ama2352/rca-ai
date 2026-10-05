"""Small exact port of the frozen standard-library BM25 index."""

from __future__ import annotations

import math
import re
from collections import Counter


K1 = 1.5
B = 0.75
_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Match the frozen lowercased Unicode word-token behavior."""

    return _TOKEN.findall(text.lower())


class BM25Index:
    """Rank keyed text documents with the frozen BM25 parameters and tie-break."""

    def __init__(self, documents: dict[str, str], k1: float = K1, b: float = B):
        if any(not isinstance(value, str) for value in documents.values()):
            raise TypeError("BM25 documents must be retrieval-text strings only")
        if not 0 <= b <= 1 or k1 <= 0:
            raise ValueError("BM25 requires k1 > 0 and 0 <= b <= 1")
        self.k1 = k1
        self.b = b
        self.term_freq = {key: Counter(tokenize(text)) for key, text in documents.items()}
        self.length = {key: sum(counts.values()) for key, counts in self.term_freq.items()}
        self.avgdl = sum(self.length.values()) / len(self.length) if self.length else 0.0
        self.n = len(documents)
        self.df = Counter(term for counts in self.term_freq.values() for term in counts)

    def rank(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        if not isinstance(query, str):
            raise TypeError("query must be retrieval text only")
        scores: dict[str, float] = {}
        for key, counts in self.term_freq.items():
            length_norm = (
                self.k1 * (1 - self.b + self.b * self.length[key] / self.avgdl)
                if self.avgdl else 0
            )
            score = 0.0
            for term in tokenize(query):
                frequency = counts.get(term, 0)
                if frequency:
                    document_frequency = self.df[term]
                    inverse_document_frequency = math.log(
                        1 + (self.n - document_frequency + 0.5) / (document_frequency + 0.5)
                    )
                    score += inverse_document_frequency * frequency * (self.k1 + 1) / (frequency + length_norm)
            scores[key] = score
        return sorted(scores.items(), key=lambda row: (-row[1], row[0]))[:k]
