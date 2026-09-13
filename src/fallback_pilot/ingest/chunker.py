"""Split blocks into retrieval-sized chunks without losing where they came from.

Every chunk keeps a human-readable citation. When the brief later claims the
renewal is blocked, the user has to be able to see which file and which section
said so - an unattributable brief is worse than no brief.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from .readers import Block

TARGET_CHARS = 1200
OVERLAP_CHARS = 150
MIN_CHARS = 60


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    title: str
    location: str
    kind: str
    ordinal: int
    meta: dict = field(default_factory=dict)

    @property
    def citation(self) -> str:
        from pathlib import Path
        name = Path(self.source).name
        return f"{name} - {self.location}" if self.location else name

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Chunk":
        return cls(**d)


def _split_long(text: str) -> list[str]:
    """Prefer paragraph breaks, then sentence ends, then a hard cut."""
    if len(text) <= TARGET_CHARS:
        return [text]

    pieces: list[str] = []
    remaining = text
    while len(remaining) > TARGET_CHARS:
        window = remaining[:TARGET_CHARS]
        cut = window.rfind("\n\n")
        if cut < MIN_CHARS:
            cut = max(window.rfind(". "), window.rfind(".\n"))
            cut = cut + 1 if cut >= MIN_CHARS else -1
        if cut < MIN_CHARS:
            cut = window.rfind("\n")
        if cut < MIN_CHARS:
            cut = TARGET_CHARS
        pieces.append(remaining[:cut].strip())
        remaining = remaining[max(0, cut - OVERLAP_CHARS):].strip()
    if remaining:
        pieces.append(remaining)
    return [p for p in pieces if p]


def chunk_blocks(blocks: list[Block]) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordinal = 0

    for b in blocks:
        if b.kind in ("skipped", "error") or not b.text.strip():
            continue

        # A heading on its own carries no information; it is already attached
        # to the blocks beneath it as their location.
        if b.kind == "heading" and len(b.text) < MIN_CHARS:
            continue

        for piece in _split_long(b.text.strip()):
            if len(piece) < MIN_CHARS and b.kind not in ("sheet", "table"):
                continue
            digest = hashlib.sha1(
                f"{b.source}|{b.location}|{piece}".encode("utf-8")
            ).hexdigest()[:12]
            chunks.append(
                Chunk(
                    id=digest,
                    text=piece,
                    source=b.source,
                    title=b.title,
                    location=b.location,
                    kind=b.kind,
                    ordinal=ordinal,
                    meta=dict(b.meta),
                )
            )
            ordinal += 1

    # Identical boilerplate across files adds nothing but noise.
    seen: set[str] = set()
    deduped: list[Chunk] = []
    for c in chunks:
        key = re.sub(r"\s+", " ", c.text.lower())[:400]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped
