"""Gather context for a brief by asking several focused questions.

One query for a whole brief under-performs badly. 'Northwind renewal' ranks
whatever mentions the account by name, so a walk-away price sitting in a
section that never repeats the account name simply never reaches the model -
and a fact the model never saw is a fact it will confabulate.

Coverage is then *guaranteed*, not hoped for. An earlier version merged the
facet results and trusted that breadth would follow. With semantic retrieval
enabled the facets overlapped heavily, the candidate pool collapsed to five
files, and the one file holding the real deadline never appeared. Selection
now explicitly tops up from any file that is still unrepresented.
"""
from __future__ import annotations

from .. import retrieve as _retrieve

# Phrased the way the documents phrase things, not the way a form would label
# them. "hard deadline date" matches source text; "Timeline" does not.
FACETS = [
    "what is blocking progress",
    "hard deadline date",
    "price floor discount",
    "who owns what action",
    "handover notes",
]

PER_FACET = 4
MAX_CHUNKS = 8


def _best_chunk_for(retriever, topic: str, source: str):
    """Highest-scoring chunk from one specific file, by keyword score.

    Uses BM25 directly rather than the hybrid path: this is a targeted lookup
    inside a known file, and it must work with no embedding model present.
    """
    scores = retriever.bm25.score(topic)
    best_i, best_score = None, 0.0
    for i, chunk in enumerate(retriever.chunks):
        if chunk.source == source and scores[i] > best_score:
            best_i, best_score = i, scores[i]
    if best_i is None:
        for i, chunk in enumerate(retriever.chunks):
            if chunk.source == source:
                best_i = i
                break
    if best_i is None:
        return None
    from ..retrieve.hybrid import Hit
    return Hit(retriever.chunks[best_i], best_score)


def gather(retriever, topic: str, max_chunks: int = MAX_CHUNKS) -> list:
    """Ask the topic plus each facet, then guarantee breadth across files."""
    seen: set[str] = set()
    ranked: list = []

    for query in [topic] + [f"{topic} {facet}" for facet in FACETS]:
        for hit in retriever.search(query, top_k=PER_FACET, per_source=1):
            if hit.chunk.id not in seen:
                seen.add(hit.chunk.id)
                ranked.append(hit)

    # Pass 1: one slot per file, in relevance order.
    first_pass, overflow, claimed = [], [], set()
    for hit in ranked:
        if hit.chunk.source in claimed:
            overflow.append(hit)
        else:
            claimed.add(hit.chunk.source)
            first_pass.append(hit)

    selected = first_pass[:max_chunks]

    # Pass 2: any file the facets never surfaced still gets its best chunk.
    # Without this, a whole document can vanish from the brief because the
    # facet queries happened to overlap.
    if len(selected) < max_chunks:
        missing = {c.source for c in retriever.chunks} - {h.chunk.source for h in selected}
        for source in sorted(missing):
            if len(selected) >= max_chunks:
                break
            hit = _best_chunk_for(retriever, topic, source)
            if hit and hit.chunk.id not in seen:
                seen.add(hit.chunk.id)
                selected.append(hit)

    # Pass 3: fill any remaining slots with second chunks from rich files.
    for hit in overflow:
        if len(selected) >= max_chunks:
            break
        selected.append(hit)

    return selected[:max_chunks]
