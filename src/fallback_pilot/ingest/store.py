"""Persist chunks locally as JSONL.

Plain text on purpose: a user can open the file and see exactly what was read
from their documents. For a tool whose pitch is privacy, that inspectability
matters more than a few milliseconds of load time.
"""
from __future__ import annotations

import json
from pathlib import Path

from .chunker import Chunk

DEFAULT_DIR = Path("index")
CHUNK_FILE = "chunks.jsonl"


def index_dir(root: str | Path | None = None) -> Path:
    return Path(root) if root else DEFAULT_DIR


def save_chunks(chunks: list[Chunk], root: str | Path | None = None) -> Path:
    d = index_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / CHUNK_FILE
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    return path


def load_chunks(root: str | Path | None = None) -> list[Chunk]:
    path = index_dir(root) / CHUNK_FILE
    if not path.exists():
        return []
    out: list[Chunk] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(Chunk.from_dict(json.loads(line)))
    return out
