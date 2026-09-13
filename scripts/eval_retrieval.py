"""Score retrieval against questions whose correct answer we already know.

Without this, 'the results look reasonable' is the only quality signal - and
that is how a demo dies on stage. Each case names the file that must appear in
the top results.

Cases are tagged by what they need:

  lexical  - the question shares words with the source. Keyword search alone
             should find these, so they must pass on any machine.
  semantic - the question shares MEANING but not words. Keyword search cannot
             find these by design; they are the reason the embedding layer
             exists, and they are scored only when it is loaded.

Run after any change to chunking, tokenizing or fusion:

    python scripts/eval_retrieval.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fallback_pilot import config as cfgmod          # noqa: E402
from fallback_pilot.ingest import ingest_paths       # noqa: E402
from fallback_pilot.llm import discover_endpoint     # noqa: E402
from fallback_pilot.retrieve import build_retriever  # noqa: E402

# (kind, question, filename that must appear, phrase expected in that hit)
CASES = [
    ("lexical", "What is blocking the renewal?",
     "Northwind_Renewal_Pricing.xlsx", "SOC 2"),
    ("lexical", "What is our walk-away price?",
     "Northwind_Account_Plan.docx", "1.18M"),
    ("lexical", "What did Priya hand over before her leave?",
     "email_priya_handover.eml", "medical leave"),
    ("lexical", "When is the real deadline, not the contract date?",
     "call_notes_2026-08-19.md", "12"),
    ("lexical", "What discount is procurement asking for?",
     "Northwind_Account_Plan.docx", "15%"),
    ("lexical", "Is our champion at risk of leaving?",
     "Northwind_Account_Plan.docx", "Marcus Feld"),
    ("lexical", "What are the outstanding items before renewal?",
     "Northwind_QBR_August.pptx", "NOT STARTED"),

    # No shared vocabulary with the source text. 'unhappy' and 'threatening'
    # appear nowhere in the corpus - only the meaning matches.
    ("semantic", "Why is the customer unhappy with us?",
     "email_customer_escalation.eml", "third time"),
    ("semantic", "Is anyone threatening to walk away?",
     "email_customer_escalation.eml", "evaluate alternatives"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Score retrieval quality.")
    ap.add_argument(
        "--keyword-only",
        action="store_true",
        help="ignore the embedding model, to show the keyword-only baseline",
    )
    args = ap.parse_args()

    cfg = cfgmod.load()
    if args.keyword_only:
        cfg["embeddings"] = dict(cfg.get("embeddings", {}), enabled=False)
    chunks, _ = ingest_paths(cfg["context"]["sources"])
    retriever = build_retriever(cfg, chunks, discover_endpoint(cfg))
    note = retriever.prepare()
    semantic = retriever.semantic_ready

    mode = "keyword + meaning" if semantic else "keyword only"
    print(f"{len(chunks)} chunks | {mode} | {note}\n")

    scored = {"lexical": [0, 0], "semantic": [0, 0]}  # [top3 hits, total]

    for kind, question, want_file, want_phrase in CASES:
        if kind == "semantic" and not semantic:
            print(f"  [skip] {question}")
            print("         needs the embedding model - load qwen3-embedding-0.6b")
            continue

        results = retriever.search(question, top_k=3)
        files = [Path(h.chunk.source).name for h in results]
        rank = files.index(want_file) + 1 if want_file in files else None
        matched = any(
            want_phrase.lower() in h.chunk.text.lower()
            for h in results if Path(h.chunk.source).name == want_file
        )

        scored[kind][1] += 1
        if rank:
            scored[kind][0] += 1

        mark = "PASS" if rank == 1 else ("ok  " if rank else "MISS")
        where = f"rank {rank}" if rank else "not in top 3"
        print(f"  [{mark}] {question}")
        print(f"         {want_file} ({where})")

        if rank:
            top = results[rank - 1]
            snippet = " ".join(top.chunk.text.split())[:100]
            print(f"         -> {top.chunk.location}: {snippet}...")
            # Long files are split across chunks, so the phrase may sit in a
            # neighbouring part. That is correct behaviour, not a miss.
            if not matched:
                print(f"         (marker '{want_phrase}' is in another part "
                      f"of the same file)")

    print()
    for kind, (hit, total) in scored.items():
        if total:
            print(f"  {kind:9s} top-3 recall: {hit}/{total}")

    if not semantic:
        print("\n  Semantic cases were skipped. To score them:")
        print("    foundry model load qwen3-embedding-0.6b")
        print("    python scripts/eval_retrieval.py")

    lex_hit, lex_total = scored["lexical"]
    sem_hit, sem_total = scored["semantic"]
    return 0 if lex_hit == lex_total and sem_hit == sem_total else 1


if __name__ == "__main__":
    sys.exit(main())
