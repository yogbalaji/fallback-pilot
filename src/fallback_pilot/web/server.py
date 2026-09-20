"""A local web interface for Fallback Pilot.

Built on the standard library alone - no Flask, no build step, no node_modules.
Two reasons, both of which matter more than convenience:

* The demo switches the network off. Anything fetched at runtime from a CDN
  would fail at precisely the moment the product is meant to prove itself.
* A judge cloning the repo should be able to run this after `pip install -e .`
  with nothing else installed.

Everything is served from localhost and nothing is ever sent outbound.
"""
from __future__ import annotations

import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import config as cfgmod
from ..availability import Tier, assess
from ..agent import Agent, ApprovalQueue, Journal
from ..brief import gather, generate, generate_extractive
from ..ingest import load_chunks
from ..llm import FoundryLocalBackend, discover_endpoint
from ..retrieve import build_retriever

HERE = Path(__file__).resolve().parent


class Disconnected(Exception):
    """The browser closed the connection while we were streaming to it."""


class State:
    """Shared, lazily-built state.

    The retriever is cached because embedding 40 chunks takes a few seconds and
    doing it per request would make the interface feel slower than the CLI it
    is meant to showcase.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.chunks = load_chunks(cfg["context"].get("index_dir", "index"))
        self._retriever = None
        self._endpoint = discover_endpoint(cfg)
        self._lock = threading.Lock()
        self._status = {"tier": 3, "label": "checking", "network": False,
                        "model": False, "files": self.files()}
        index_root = cfg["context"].get("index_dir", "index")
        self.journal = Journal(index_root)
        self.approvals = ApprovalQueue(index_root)
        self.agent = Agent(cfg)
        self._agent_thread = None
        # Probing takes a second or so - a real TCP connection, deliberately.
        # Running it on the request thread would make the browser wait, so it
        # runs here instead and requests read the last known answer.
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self) -> None:
        while True:
            try:
                endpoint = discover_endpoint(self.cfg)
                av = assess(self.cfg, endpoint)
                self._endpoint = endpoint
                self._status = {
                    "tier": int(av.tier), "label": av.label,
                    "network": av.network, "model": av.local_model,
                    "files": self.files(),
                }
            except Exception:
                pass  # a transient probe failure must not kill the watcher
            time.sleep(1.5)

    def status(self) -> dict:
        return dict(self._status)

    def endpoint(self) -> str | None:
        return self._endpoint

    def retriever(self):
        with self._lock:
            if self._retriever is None:
                self._retriever = build_retriever(self.cfg, self.chunks, self.endpoint())
                self._retriever.prepare()
            return self._retriever

    def files(self) -> int:
        return len({c.source for c in self.chunks})


class Handler(BaseHTTPRequestHandler):
    state: State = None  # set by serve()

    def log_message(self, *args):
        pass  # keep the terminal clean during a demo

    # ------------------------------------------------------------------ utils

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The browser navigated away or refreshed mid-request. Routine, and
            # a stack trace on the terminal during a demo looks like a crash.
            pass

    def _event(self, payload: dict) -> None:
        """Push one server-sent event. Raises Disconnected if the client left."""
        try:
            self.wfile.write(f"data:{json.dumps(payload)}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise Disconnected from None

    # -------------------------------------------------------------- endpoints

    def do_GET(self):
        route = urlparse(self.path)
        if route.path in ("/", "/index.html"):
            return self._send(200, (HERE / "app.html").read_bytes(), "text/html; charset=utf-8")
        if route.path == "/api/status":
            return self._status()
        if route.path == "/api/brief":
            topic = (parse_qs(route.query).get("topic") or [""])[0].strip()
            return self._brief(topic)
        if route.path == "/api/agent":
            return self._agent_state()
        if route.path == "/api/agent/decide":
            args = parse_qs(route.query)
            return self._decide(
                (args.get("id") or [""])[0], (args.get("action") or [""])[0]
            )
        if route.path == "/api/agent/pause":
            paused = (parse_qs(route.query).get("paused") or ["true"])[0] == "true"
            self.state.agent.pause(paused)
            return self._send(200, json.dumps({"paused": paused}).encode(),
                              "application/json")
        if route.path == "/api/agent/run":
            return self._run_agent_once()
        self._send(404, b"not found", "text/plain")

    def _agent_state(self):
        s = self.state
        self._send(200, json.dumps({
            "paused": s.agent.state.paused,
            "activity": s.journal.recent(25),
            "approvals": s.approvals.pending(),
        }).encode(), "application/json")

    def _decide(self, item_id: str, action: str):
        if action not in ("approved", "discarded"):
            return self._send(400, b'{"error":"bad action"}', "application/json")
        item = self.state.approvals.decide(item_id, action)
        self.state.journal.record(
            "decided",
            f"you {action} the prepared reply"
            + (" - copy it into your mail client to send" if action == "approved" else ""),
            trigger="user",
            detail={"approval_id": item_id},
        )
        self._send(200, json.dumps({"ok": bool(item), "item": item}).encode(),
                   "application/json")

    def _run_agent_once(self):
        """Override: make the agent look again right now."""
        result = self.state.agent.cycle()
        self._send(200, json.dumps(result).encode(), "application/json")

    def _status(self):
        self._send(200, json.dumps(self.state.status()).encode(), "application/json")

    def _brief(self, topic: str):
        try:
            self._stream_brief(topic)
        except Disconnected:
            pass  # user refreshed or closed the tab; nothing to report

    def _stream_brief(self, topic: str):
        s = self.state
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        if not topic:
            return self._event({"type": "error", "text": "Type a topic first."})
        if not s.chunks:
            return self._event({"type": "error",
                                "text": "Nothing ingested yet. Run: fallback-pilot ingest"})

        endpoint = s.endpoint()
        av = assess(s.cfg, endpoint)

        started = time.perf_counter()
        hits = gather(s.retriever(), topic, s.cfg["retrieval"].get("brief_chunks", 8))
        retrieve_ms = int((time.perf_counter() - started) * 1000)

        citations = [h.chunk.citation for h in hits]
        self._event({"type": "retrieved", "ms": retrieve_ms, "sources": citations})

        if not hits:
            return self._event({"type": "error", "text": "No local context matched."})

        try:
            if av.tier == Tier.DEGRADED:
                brief = generate_extractive(topic, hits, av)
                self._event({"type": "token", "text": brief.body})
            else:
                backend = FoundryLocalBackend(
                    endpoint, s.cfg["model"]["alias"], s.cfg["runtime"]["timeout_seconds"]
                )
                brief = generate(
                    topic, hits, backend, av,
                    max_tokens=s.cfg["model"]["max_tokens"],
                    temperature=s.cfg["model"]["temperature"],
                    on_token=lambda t: self._event({"type": "token", "text": t}),
                )
        except Exception as exc:
            # Falling back here is the product behaving correctly, so say so
            # rather than showing a stack trace.
            self._event({"type": "token",
                         "text": f"\n\n_Model unavailable ({type(exc).__name__}). "
                                 "Falling back to an extracted brief._\n\n"})
            brief = generate_extractive(topic, hits, av)
            self._event({"type": "token", "text": brief.body})

        self._event({
            "type": "done",
            "seconds": brief.seconds,
            "sources": brief.sources,
            "cited": sorted(brief.cited),
            "grounded": brief.grounded,
            "tier": brief.tier,
            "notes": brief.notes,
        })


def serve(port: int = 8756, open_browser: bool = True) -> None:
    cfg = cfgmod.load()
    Handler.state = State(cfg)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"

    print(f"Fallback Pilot is running at {url}")
    print("Bound to localhost only. Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        httpd.shutdown()
