"""BM25 keyword ranking, pure standard library.

This is the retrieval floor. It needs no model, no network and no packages, so
search keeps working in exactly the conditions the project is about. On a
corpus of local work documents it is also genuinely strong: the terms that
matter - names, dates, SOC 2, DPA, renewal - are rare words, and rare-word
matching is precisely what BM25 rewards.
"""
from __future__ import annotations

import math
from collections import Counter

from ..ingest.chunker import Chunk
from .tokenize import tokenize

K1 = 1.5   # term-frequency saturation
B = 0.75   # length normalisation


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.docs: list[Counter] = []
        self.lengths: list[int] = []
        df: Counter = Counter()

        for c in chunks:
            # The heading a chunk sits under is part of what it is about.
            toks = tokenize(f"{c.location} {c.text}")
            tf = Counter(toks)
            self.docs.append(tf)
            self.lengths.append(len(toks))
            df.update(tf.keys())

        self.n = len(chunks)
        self.avg_len = (sum(self.lengths) / self.n) if self.n else 0.0
        self.idf = {
            term: math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def score(self, query: str) -> list[float]:
        q_terms = tokenize(query)
        scores = [0.0] * self.n
        if not q_terms or not self.n:
            return scores

        for term in q_terms:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self.docs):
                f = tf.get(term, 0)
                if not f:
                    continue
                norm = 1 - B + B * (self.lengths[i] / self.avg_len or 1)
                scores[i] += idf * (f * (K1 + 1)) / (f + K1 * norm)
        return scores

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        scores = self.score(query)
        ranked = sorted(range(self.n), key=lambda i: scores[i], reverse=True)
        return [(i, scores[i]) for i in ranked[:top_k] if scores[i] > 0]
