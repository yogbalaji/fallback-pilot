"""Fallback Pilot CLI.

    fallback-pilot doctor
    fallback-pilot ingest
    fallback-pilot search "what is blocking the renewal"
    fallback-pilot brief "Northwind renewal" --out brief.md
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import config as cfgmod
from .availability import Tier, assess
from .ingest import ingest_paths, load_chunks, save_chunks
from .llm import ExtractiveBackend, FoundryLocalBackend, Message, discover_endpoint
from .brief import gather, generate, generate_extractive, print_brief, to_markdown
from .retrieve import build_retriever

console = Console()


def _pick_backend(cfg: dict):
    endpoint = discover_endpoint(cfg)
    av = assess(cfg, endpoint)
    if av.tier == Tier.DEGRADED:
        return ExtractiveBackend(), av
    return FoundryLocalBackend(endpoint, cfg["model"]["alias"], cfg["runtime"]["timeout_seconds"]), av


def cmd_doctor(cfg: dict) -> int:
    endpoint = discover_endpoint(cfg)
    av = assess(cfg, endpoint)

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_row("Network", "[green]up[/]" if av.network else "[yellow]down[/]")
    t.add_row("Local model", "[green]serving[/]" if av.local_model else "[red]not found[/]")
    t.add_row("Endpoint", av.endpoint or "[dim]none discovered[/]")
    t.add_row("Cloud AI", "permitted" if av.cloud_ai_permitted else "withheld")
    t.add_row("Active tier", f"[bold]{int(av.tier)} - {av.label}[/]")
    console.print(Panel(t, title="Fallback Pilot - device readiness", border_style="cyan"))

    for n in av.notes:
        console.print(f"  [dim]note:[/] {n}")
    if not av.local_model:
        console.print(
            "\n[yellow]Start the runtime first:[/]\n"
            "  foundry server start --port 39839 --idle-timeout 0\n"
            f"  foundry model load {cfg['model']['alias']}"
        )
    return 0


def cmd_ingest(cfg: dict, paths: list[str]) -> int:
    sources = paths or cfg["context"]["sources"]
    if not sources:
        console.print("[yellow]No sources configured.[/] Add folders under 'context.sources' in config.yaml.")
        return 1

    index_root = cfg["context"].get("index_dir", "index")
    console.print(f"[dim]Reading from: {', '.join(sources)}[/]\n")

    started = time.perf_counter()
    chunks, report = ingest_paths(list(sources), root=index_root)
    elapsed = time.perf_counter() - started

    if not report:
        console.print("[yellow]No supported files found.[/] Looked for .docx .pptx .xlsx .pdf .txt .md .eml")
        return 1

    t = Table(box=None, padding=(0, 2))
    t.add_column("File"); t.add_column("Blocks", justify="right"); t.add_column("Status")
    for r in report:
        colour = {"ok": "green", "skipped": "yellow", "empty": "dim"}.get(r["status"], "red")
        note = f" [dim]{r['reason']}[/]" if r["reason"] else ""
        t.add_row(r["name"], str(r["blocks"]), f"[{colour}]{r['status']}[/]{note}")
    console.print(t)

    path = save_chunks(chunks, index_root)
    ok = sum(1 for r in report if r["status"] == "ok")
    console.print(
        f"\n[green]{len(chunks)} chunks[/] from [green]{ok}[/] files in {elapsed:.2f}s"
    )
    console.print(f"[dim]Stored at {path} - plain text, open it and look.[/]")
    console.print("[dim]Nothing left this device.[/]")
    return 0


def cmd_sources(cfg: dict) -> int:
    chunks = load_chunks(cfg["context"].get("index_dir", "index"))
    if not chunks:
        console.print("[yellow]Nothing ingested yet.[/] Run: fallback-pilot ingest")
        return 1

    by_file: dict[str, int] = {}
    for c in chunks:
        by_file[c.citation.split(" - ")[0]] = by_file.get(c.citation.split(" - ")[0], 0) + 1

    t = Table(box=None, padding=(0, 2))
    t.add_column("File"); t.add_column("Chunks", justify="right")
    for name, n in sorted(by_file.items(), key=lambda kv: -kv[1]):
        t.add_row(name, str(n))
    console.print(Panel(t, title=f"Local context - {len(chunks)} chunks", border_style="cyan"))
    return 0


def cmd_search(cfg: dict, query: str, top_k, rebuild: bool) -> int:
    chunks = load_chunks(cfg["context"].get("index_dir", "index"))
    if not chunks:
        console.print("[yellow]Nothing ingested yet.[/] Run: fallback-pilot ingest")
        return 1

    endpoint = discover_endpoint(cfg)
    retriever = build_retriever(cfg, chunks, endpoint)

    started = time.perf_counter()
    note = retriever.prepare(force=rebuild)
    prep = time.perf_counter() - started

    mode = "keyword + meaning" if retriever.semantic_ready else "keyword only"
    console.print(f"[dim]{len(chunks)} chunks - {mode} - {note} ({prep:.2f}s)[/]\n")

    started = time.perf_counter()
    hits = retriever.search(query, top_k=top_k or cfg["retrieval"]["top_k"])
    elapsed = time.perf_counter() - started

    if not hits:
        console.print("[yellow]Nothing matched.[/] Try different words.")
        return 1

    for i, h in enumerate(hits, 1):
        console.print(f"[bold cyan]{i}.[/] [dim]{h.chunk.citation}[/]  [dim]({h.why})[/]")
        text = " ".join(h.chunk.text.split())
        console.print(f"   {text[:220]}{'...' if len(text) > 220 else ''}\n")

    console.print(f"[dim]{elapsed*1000:.0f}ms on this device - nothing left the machine.[/]")
    return 0


def cmd_probe(cfg: dict) -> int:
    """Show every raw signal the tier decision is made from.

    When the badge shows the wrong tier, the useful question is which probe
    disagreed with reality. This prints them all rather than the conclusion.
    """
    import socket

    import requests

    from .availability import _route_exists

    av_cfg = cfg["availability"]
    host = av_cfg["network_probe_host"]
    port = av_cfg["network_probe_port"]
    timeout = av_cfg["probe_timeout_seconds"]

    t = Table(show_header=False, box=None, padding=(0, 2))

    started = time.perf_counter()
    route = _route_exists(host, port, timeout)
    t.add_row("Route to internet", f"{route}", f"[dim]{time.perf_counter()-started:.2f}s[/]")

    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            connect = True
    except OSError as exc:
        connect = f"no ({type(exc).__name__})"
    t.add_row(f"TCP to {host}:{port}", f"{connect}",
              f"[dim]{time.perf_counter()-started:.2f}s[/]")

    endpoint = discover_endpoint(cfg)
    t.add_row("Runtime endpoint", endpoint or "[red]not found[/]", "")

    listed, count = "n/a", 0
    if endpoint:
        try:
            r = requests.get(f"{endpoint.rstrip('/')}/models", timeout=3)
            body = r.json() if r.status_code == 200 else {}
            models = body.get("data") if isinstance(body, dict) else body
            count = len(models or [])
            listed = f"HTTP {r.status_code}, {count} model(s)"
            if count:
                names = [m.get("id", "?") for m in (models or [])[:4] if isinstance(m, dict)]
                listed += f" - {', '.join(names)}"
        except Exception as exc:
            listed = f"failed ({type(exc).__name__})"
    t.add_row("Models endpoint", listed, "")

    av = assess(cfg, endpoint)
    t.add_row("", "", "")
    t.add_row("[bold]Decision[/]", f"[bold]tier {int(av.tier)} - {av.label}[/]", "")
    console.print(Panel(t, title="Probe results", border_style="cyan"))

    console.print("\n[dim]What each tier needs:[/]")
    console.print("[dim]  tier 1  network yes + models listed[/]")
    console.print("[dim]  tier 2  network no  + models listed[/]")
    console.print("[dim]  tier 3  no models listed (runtime down, or all unloaded)[/]")
    if count == 0 and endpoint:
        console.print("\n[yellow]The runtime is up but lists no models.[/] "
                      "That is tier 3, correctly.")
    return 0


def cmd_ui(cfg: dict, port: int, no_browser: bool) -> int:
    from .web import serve
    chunks = load_chunks(cfg["context"].get("index_dir", "index"))
    if not chunks:
        console.print("[yellow]Nothing ingested yet.[/] Run: fallback-pilot ingest")
        return 1
    serve(port=port, open_browser=not no_browser)
    return 0


def cmd_brief(cfg: dict, topic: str, out, no_draft: bool, model, quiet: bool) -> int:
    chunks = load_chunks(cfg["context"].get("index_dir", "index"))
    if not chunks:
        console.print("[yellow]Nothing ingested yet.[/] Run: fallback-pilot ingest")
        return 1

    endpoint = discover_endpoint(cfg)
    av = assess(cfg, endpoint)

    retriever = build_retriever(cfg, chunks, endpoint)
    retriever.prepare()
    mode = "keyword + meaning" if retriever.semantic_ready else "keyword only"
    console.print(f"[dim]tier {int(av.tier)} - {av.label} - retrieval: {mode}[/]\n")

    hits = gather(retriever, topic, cfg["retrieval"].get("brief_chunks", 8))
    if not hits:
        console.print("[yellow]No local context matched that topic.[/]")
        return 1

    streamed_any = False
    if av.tier == Tier.DEGRADED:
        brief = generate_extractive(topic, hits, av)
    else:
        backend = FoundryLocalBackend(
            endpoint, model or cfg["model"]["alias"], cfg["runtime"]["timeout_seconds"]
        )
        streamed = {"any": False}

        def show(piece: str) -> None:
            if not streamed["any"]:
                console.print("[dim]writing...[/]\n")
                streamed["any"] = True
            sys.stdout.write(piece)
            sys.stdout.flush()

        try:
            brief = generate(
                topic, hits, backend, av,
                max_tokens=cfg["model"]["max_tokens"],
                temperature=cfg["model"]["temperature"],
                with_draft=not no_draft,
                on_token=None if quiet else show,
            )
            if streamed["any"]:
                console.print()
            streamed_any = streamed["any"]
        except Exception as exc:
            console.print(f"[yellow]Model unavailable ({type(exc).__name__}) - "
                          "falling back to an extracted brief.[/]\n")
            brief = generate_extractive(topic, hits, av)

    print_brief(brief, console, already_shown=streamed_any)

    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_markdown(brief), encoding="utf-8")
        console.print(f"\n[green]Saved[/] {path}")
    return 0


def cmd_ask(cfg: dict, prompt: str) -> int:
    backend, av = _pick_backend(cfg)
    console.print(f"[dim]tier {int(av.tier)} - {av.label} - via {backend.name}[/]\n")

    messages = [
        Message("system", "You are Fallback Pilot. Answer only from what you are given. Be brief and concrete."),
        Message("user", prompt),
    ]
    started = time.perf_counter()
    try:
        answer = backend.complete(
            messages,
            max_tokens=cfg["model"]["max_tokens"],
            temperature=cfg["model"]["temperature"],
        )
    except Exception as exc:
        console.print(f"[red]Backend failed:[/] {exc}")
        console.print("[dim]Dropping to extractive fallback...[/]")
        answer = ExtractiveBackend().complete(messages, max_tokens=0, temperature=0)
    elapsed = time.perf_counter() - started

    console.print(Panel(answer, border_style="green"))
    console.print(f"[dim]{elapsed:.2f}s on this device - nothing left the machine.[/]")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fallback-pilot")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="show what this device can currently do")
    sub.add_parser("probe", help="show the raw signals behind the tier decision")
    ing = sub.add_parser("ingest", help="read local Office files into the index")
    ing.add_argument("paths", nargs="*", help="files or folders (defaults to config)")
    sub.add_parser("sources", help="show what is currently in the index")
    se = sub.add_parser("search", help="find the most relevant local context")
    se.add_argument("query")
    se.add_argument("--top", type=int, default=None, help="how many results")
    se.add_argument("--rebuild", action="store_true", help="recompute embeddings")
    br = sub.add_parser("brief", help="build a continuity brief from local context")
    br.add_argument("topic", help="what the brief should be about")
    br.add_argument("--out", default=None, help="also save as markdown, e.g. brief.md")
    br.add_argument("--no-draft", action="store_true", help="skip the draft message")
    br.add_argument("--model", default=None, help="override the model for this run")
    br.add_argument("--quiet", action="store_true",
                    help="wait for the finished brief instead of streaming it")
    ui = sub.add_parser("ui", help="open the local web interface")
    ui.add_argument("--port", type=int, default=8756)
    ui.add_argument("--no-browser", action="store_true", help="do not open a browser")
    a = sub.add_parser("ask", help="send one prompt through the fallback ladder")
    a.add_argument("prompt")

    args = p.parse_args(argv)
    cfg = cfgmod.load(args.config)

    if args.cmd == "doctor":
        return cmd_doctor(cfg)
    if args.cmd == "ingest":
        return cmd_ingest(cfg, args.paths)
    if args.cmd == "sources":
        return cmd_sources(cfg)
    if args.cmd == "search":
        return cmd_search(cfg, args.query, args.top, args.rebuild)
    if args.cmd == "probe":
        return cmd_probe(cfg)
    if args.cmd == "ui":
        return cmd_ui(cfg, args.port, args.no_browser)
    if args.cmd == "brief":
        return cmd_brief(cfg, args.topic, args.out, args.no_draft, args.model, args.quiet)
    if args.cmd == "ask":
        return cmd_ask(cfg, args.prompt)
    return 1


if __name__ == "__main__":
    sys.exit(main())
