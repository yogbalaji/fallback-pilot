import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fallback_pilot.ingest import ingest_paths  # noqa: E402
from fallback_pilot.ingest.chunker import Chunk  # noqa: E402
from fallback_pilot.retrieve.bm25 import BM25Index  # noqa: E402
from fallback_pilot.retrieve.embed import cosine  # noqa: E402
from fallback_pilot.retrieve.hybrid import HybridRetriever  # noqa: E402
from fallback_pilot.retrieve.tokenize import tokenize  # noqa: E402

DEMO = ROOT / "demo_data"


def _chunks():
    chunks, _ = ingest_paths([str(DEMO)])
    return chunks


def test_tokenizer_drops_stopwords_and_plurals():
    toks = tokenize("The renewals are blocked by the security reviews")
    assert "the" not in toks and "are" not in toks
    assert "renewal" in toks and "review" in toks


def test_tokenizer_keeps_domain_terms_intact():
    toks = tokenize("SOC 2 Type II and the DPA redlines, due 2026-09-05")
    assert "soc" in toks and "dpa" in toks
    assert any("2026-09-05" in t for t in toks)


def test_bm25_ranks_the_blocker_first():
    chunks = _chunks()
    idx = BM25Index(chunks)
    top = idx.search("what is blocking the renewal", top_k=1)
    assert top, "a corpus this size must always return something"
    assert "SOC 2" in chunks[top[0][0]].text


def test_bm25_returns_nothing_for_absent_terms():
    idx = BM25Index(_chunks())
    assert idx.search("quantum entanglement propulsion", top_k=3) == []


def test_bm25_handles_empty_corpus():
    idx = BM25Index([])
    assert idx.search("anything") == []


def test_retrieval_works_with_no_embedder():
    """The whole point: search must not depend on a model being present."""
    r = HybridRetriever(_chunks(), embedder=None)
    note = r.prepare()
    assert r.semantic_ready is False
    assert "no embedding model" in note
    hits = r.search("what is the walk-away price", top_k=3)
    assert hits and any("1.18M" in h.chunk.text for h in hits)


def test_broken_embedder_degrades_instead_of_raising():
    class Broken:
        model = "broken"
        def embed(self, texts, **kw):
            raise ConnectionError("runtime is down")

    r = HybridRetriever(_chunks(), embedder=Broken())
    note = r.prepare()
    assert r.semantic_ready is False
    assert "keywords only" in note
    assert r.search("renewal blocker", top_k=3), "must still return keyword hits"


def test_hit_explains_why_it_matched():
    r = HybridRetriever(_chunks(), embedder=None)
    r.prepare()
    assert r.search("security evidence", top_k=1)[0].why == "keyword"


def test_cosine_of_identical_vectors_is_one():
    v = [0.6, 0.8]
    assert abs(cosine(v, v) - 1.0) < 1e-9


def test_citation_survives_retrieval():
    r = HybridRetriever(_chunks(), embedder=None)
    r.prepare()
    hit = r.search("speaker notes about the pricing floor", top_k=1)[0]
    assert hit.chunk.citation
    assert " - " in hit.chunk.citation


def test_location_is_searchable():
    """A chunk's heading is part of what it is about."""
    chunks = [
        Chunk("c1", "Nothing useful here at all in this text.", "a.docx", "a",
              "under 'Termination and Renewal'", "paragraph", 0),
        Chunk("c2", "Some other unrelated body content entirely.", "b.docx", "b",
              "under 'Introduction'", "paragraph", 1),
    ]
    top = BM25Index(chunks).search("termination", top_k=1)
    assert top and top[0][0] == 0
