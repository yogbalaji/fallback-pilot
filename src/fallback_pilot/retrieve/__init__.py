from .bm25 import BM25Index
from .embed import EmbeddingClient
from .hybrid import Hit, HybridRetriever
from .tokenize import tokenize

__all__ = ["BM25Index", "EmbeddingClient", "Hit", "HybridRetriever", "tokenize"]


def build_retriever(cfg: dict, chunks: list, endpoint: str | None = None):
    """Assemble a retriever from config, wiring embeddings only if configured."""
    index_root = cfg["context"].get("index_dir", "index")
    emb_cfg = cfg.get("embeddings", {})
    embedder = None
    if endpoint and emb_cfg.get("enabled", True):
        embedder = EmbeddingClient(
            endpoint,
            emb_cfg.get("alias", "qwen3-embedding-0.6b"),
            cfg["runtime"].get("timeout_seconds", 120),
        )
    return HybridRetriever(chunks, embedder, index_root)
