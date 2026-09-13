"""Hybrid retrieval: keywords always, embeddings when available.

The two methods fail in different directions. BM25 misses paraphrase; embeddings
drift on rare literals like 'SOC 2' or a specific date. Fusing them covers both,
and because the keyword half needs nothing at all, retrieval degrades on the
same ladder as the rest of the app.

Ranks are fused rather than scores. BM25 scores are unbounded while cosine
similarity sits in [-1, 1], so averaging the raw numbers would let one side
dominate for reasons unrelated to relevance.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..ingest.chunker import Chunk
from .bm25 import BM25Index
from .embed import EmbeddingClient, cosine, load_cache, save_cache

RRF_K = 60  # rank-fusion damping; standard value, keeps top ranks from swamping


@dataclass
class Hit:
    chunk: Chunk
    score: float
    keyword_rank: int | None = None
    semantic_rank: int | None = None

    @property
    def why(self) -> str:
        if self.keyword_rank is not None and self.semantic_rank is not None:
            return "keyword + meaning"
        if self.semantic_rank is not None:
            return "meaning"
        return "keyword"


class HybridRetriever:
    def __init__(
        self,
        chunks: list[Chunk],
        embedder: EmbeddingClient | None = None,
        index_root: str = "index",
    ):
        self.chunks = chunks
        self.bm25 = BM25Index(chunks)
        self.embedder = embedder
        self.index_root = index_root
        self.vectors: list[list[float]] | None = None
        self.semantic_note = "not enabled"

    def prepare(self, force: bool = False) -> str:
        """Load or compute chunk vectors. Never fatal - returns a status note."""
        if not self.embedder:
            self.semantic_note = "no embedding model configured"
            return self.semantic_note

        ids = [c.id for c in self.chunks]
        model = self.embedder.model

        if not force:
            cached = load_cache(self.index_root, ids, model)
            if cached:
                self.vectors = cached
                self.semantic_note = f"loaded {len(cached)} cached vectors"
                return self.semantic_note

        try:
            self.vectors = self.embedder.embed([c.text for c in self.chunks])
            save_cache(self.index_root, ids, model, self.vectors)
            self.semantic_note = f"embedded {len(self.vectors)} chunks on-device"
        except Exception as exc:
            self.vectors = None
            self.semantic_note = f"unavailable ({type(exc).__name__}) - keywords only"
        return self.semantic_note

    @property
    def semantic_ready(self) -> bool:
        return bool(self.vectors)

    def search(self, query: str, top_k: int = 5, per_source: int | None = None) -> list[Hit]:
        keyword = self.bm25.search(query, top_k=max(top_k * 3, 15))
        kw_rank = {ci: r for r, (ci, _) in enumerate(keyword, start=1)}

        sem_rank: dict[int, int] = {}
        if self.semantic_ready and self.embedder:
            try:
                qv = self.embedder.embed([query])[0]
                sims = [(i, cosine(qv, v)) for i, v in enumerate(self.vectors)]
                sims.sort(key=lambda t: t[1], reverse=True)
                sem_rank = {
                    ci: r for r, (ci, _) in enumerate(sims[: max(top_k * 3, 15)], start=1)
                }
            except Exception:
                sem_rank = {}

        fused: dict[int, float] = {}
        for ci, r in kw_rank.items():
            fused[ci] = fused.get(ci, 0.0) + 1.0 / (RRF_K + r)
        for ci, r in sem_rank.items():
            fused[ci] = fused.get(ci, 0.0) + 1.0 / (RRF_K + r)

        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)

        if per_source is None:
            selected = ordered[:top_k]
        else:
            selected, used = [], {}
            overflow = []
            for ci, score in ordered:
                src = self.chunks[ci].source
                if used.get(src, 0) < per_source:
                    used[src] = used.get(src, 0) + 1
                    selected.append((ci, score))
                else:
                    overflow.append((ci, score))
                if len(selected) == top_k:
                    break
            # If diversity alone could not fill the quota, top up by score.
            for item in overflow:
                if len(selected) >= top_k:
                    break
                selected.append(item)

        return [
            Hit(self.chunks[ci], score, kw_rank.get(ci), sem_rank.get(ci))
            for ci, score in selected
        ]
