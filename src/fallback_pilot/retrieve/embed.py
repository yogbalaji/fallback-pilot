"""Optional semantic layer, computed on-device.

Keyword search misses paraphrase: ask 'who is unhappy?' and BM25 cannot connect
it to 'I want to be direct... I will have to recommend we extend'. Embeddings
close that gap.

This stays strictly optional. If no embedding model is loaded the app returns
None and hybrid search silently uses keywords alone - the same degradation
principle as the rest of the project.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import requests

CACHE_FILE = "embeddings.json"


def _l2_normalise(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v] if norm else v


def cosine(a: list[float], b: list[float]) -> float:
    """Vectors are stored pre-normalised, so this is a plain dot product."""
    return sum(x * y for x, y in zip(a, b))


class EmbeddingClient:
    def __init__(self, endpoint: str, model: str, timeout: int = 120):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        """True only if an embedding model is actually loaded and responding."""
        try:
            return bool(self.embed(["ping"]))
        except Exception:
            return False

    def resolved_model(self) -> str:
        try:
            data = requests.get(f"{self.endpoint}/models", timeout=5).json()
        except Exception:
            return self.model
        ids = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
        if self.model in ids:
            return self.model
        for mid in ids:
            if self.model.lower() in mid.lower():
                return mid
        for mid in ids:
            if "embed" in mid.lower():
                return mid
        return self.model

    def embed(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
        model = self.resolved_model()
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            r = requests.post(
                f"{self.endpoint}/embeddings",
                headers={"Content-Type": "application/json"},
                data=json.dumps({"model": model, "input": batch}),
                timeout=self.timeout,
            )
            r.raise_for_status()
            body = r.json()
            rows = sorted(body.get("data", []), key=lambda d: d.get("index", 0))
            out.extend(_l2_normalise(row["embedding"]) for row in rows)
        return out


def _fingerprint(chunk_ids: list[str], model: str) -> str:
    h = hashlib.sha1(model.encode())
    for cid in chunk_ids:
        h.update(cid.encode())
    return h.hexdigest()[:16]


def load_cache(index_root: str | Path, chunk_ids: list[str], model: str) -> list[list[float]] | None:
    """Reuse vectors only if the corpus and model are byte-for-byte the same."""
    path = Path(index_root) / CACHE_FILE
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if blob.get("fingerprint") != _fingerprint(chunk_ids, model):
        return None
    vectors = blob.get("vectors")
    return vectors if isinstance(vectors, list) and len(vectors) == len(chunk_ids) else None


def save_cache(
    index_root: str | Path, chunk_ids: list[str], model: str, vectors: list[list[float]]
) -> Path:
    d = Path(index_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / CACHE_FILE
    path.write_text(
        json.dumps(
            {
                "fingerprint": _fingerprint(chunk_ids, model),
                "model": model,
                "dimensions": len(vectors[0]) if vectors else 0,
                "vectors": vectors,
            }
        ),
        encoding="utf-8",
    )
    return path
