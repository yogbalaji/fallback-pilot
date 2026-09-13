"""Run the same brief through several local models and compare them.

Model choice is the biggest single lever on how the brief reads, and 'it felt
better' is not a defensible reason to pick one. This measures what can be
measured - speed, grounding, structure, specificity - and prints the briefs
side by side so you can judge the prose yourself.

    foundry model load phi-4-mini
    foundry model load qwen2.5-7b
    python scripts/compare_models.py phi-4-mini qwen2.5-7b

Any model you name must already be loaded, or the run will be slow while it
downloads.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fallback_pilot import config as cfgmod              # noqa: E402
from fallback_pilot.availability import assess           # noqa: E402
from fallback_pilot.brief import gather, generate, to_markdown  # noqa: E402
from fallback_pilot.ingest import load_chunks            # noqa: E402
from fallback_pilot.llm import FoundryLocalBackend, discover_endpoint  # noqa: E402
from fallback_pilot.retrieve import build_retriever      # noqa: E402

DEFAULT_TOPIC = "Northwind renewal - what do I need to know before the call"

# Facts that a good brief about this scenario should surface. Not a grade for
# writing quality - a check that the specifics survived the summarisation.
KEY_FACTS = {
    "SOC 2": r"soc\s*2",
    "the real deadline (12 Sept)": r"\b12\s+september|sept(ember)?\s+12",
    "the pricing floor": r"1\.18|1,180,000|1180000",
    "the discount ask": r"15\s*%|15 percent",
    "Dana (the blocker)": r"\bdana\b",
}


def score(brief) -> dict:
    text = (brief.body + " " + brief.draft).lower()
    found = [name for name, pattern in KEY_FACTS.items() if re.search(pattern, text)]
    filled = [h for h in ["Situation", "Open actions", "Blockers and risks",
                          "Recommended next step"] if brief.sections.get(h, "").strip()]
    return {
        "seconds": brief.seconds,
        "words": len(brief.body.split()),
        "sections": len(filled),
        "facts": found,
        "cited": len(brief.cited),
        "sources": len(brief.sources),
        "invented": sorted(brief.invented),
        "has_draft": bool(brief.draft),
        "leaked": brief.template_leak,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+", help="model aliases to compare")
    ap.add_argument("--topic", default=DEFAULT_TOPIC)
    ap.add_argument("--save", default="docs/model_comparison.md")
    args = ap.parse_args()

    cfg = cfgmod.load()
    chunks = load_chunks(cfg["context"].get("index_dir", "index"))
    if not chunks:
        print("Nothing ingested. Run: fallback-pilot ingest")
        return 1

    endpoint = discover_endpoint(cfg)
    av = assess(cfg, endpoint)
    if not endpoint:
        print("No local runtime found. Start it first:")
        print("  foundry server start --port 39839 --idle-timeout 0")
        return 1

    retriever = build_retriever(cfg, chunks, endpoint)
    retriever.prepare()
    hits = gather(retriever, args.topic, cfg["retrieval"].get("brief_chunks", 8))
    print(f"Topic: {args.topic}")
    print(f"Same {len(hits)} sources for every model.\n")

    results, briefs = {}, {}
    for alias in args.models:
        print(f"  {alias} ...", end=" ", flush=True)
        backend = FoundryLocalBackend(endpoint, alias, cfg["runtime"]["timeout_seconds"])
        try:
            brief = generate(
                args.topic, hits, backend, av,
                max_tokens=cfg["model"]["max_tokens"],
                temperature=cfg["model"]["temperature"],
            )
        except Exception as exc:
            print(f"failed - {type(exc).__name__}: {exc}")
            continue
        results[alias] = score(brief)
        briefs[alias] = brief
        print(f"{brief.seconds:.1f}s")

    if not results:
        print("\nNo model produced a brief.")
        return 1

    print(f"\n{'model':<28} {'sec':>6} {'words':>6} {'sec/4':>6} "
          f"{'facts':>7} {'cited':>7}")
    print("-" * 68)
    for alias, r in results.items():
        print(f"{alias:<28} {r['seconds']:>6.1f} {r['words']:>6} "
              f"{r['sections']:>5}/4 {len(r['facts']):>5}/{len(KEY_FACTS)} "
              f"{r['cited']:>4}/{r['sources']}")

    print("\nKey facts each model kept:")
    for alias, r in results.items():
        missing = [k for k in KEY_FACTS if k not in r["facts"]]
        print(f"  {alias}")
        print(f"    kept:   {', '.join(r['facts']) or 'none'}")
        if missing:
            print(f"    LOST:   {', '.join(missing)}")
        if r["invented"]:
            print(f"    INVENTED citations: {r['invented']}")
        if r["leaked"]:
            print("    COPIED THE PROMPT TEMPLATE - brief is fabricated")

    out = Path(args.save)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = [f"# Model comparison\n", f"Topic: {args.topic}\n",
           f"Identical {len(hits)} sources for every model.\n",
           "| model | seconds | words | sections | key facts | citations | verdict |",
           "|---|---|---|---|---|---|---|"]
    for alias, r in results.items():
        doc.append(
            f"| {alias} | {r['seconds']:.1f} | {r['words']} | {r['sections']}/4 "
            f"| {len(r['facts'])}/{len(KEY_FACTS)} | {r['cited']}/{r['sources']} "
            f"| {'FABRICATED' if r['leaked'] else 'ok'} |"
        )
    for alias, brief in briefs.items():
        doc += [f"\n\n---\n\n# {alias}\n", to_markdown(brief)]
    out.write_text("\n".join(doc), encoding="utf-8")
    print(f"\nFull briefs written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
