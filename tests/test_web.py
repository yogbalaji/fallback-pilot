import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fallback_pilot import config as cfgmod  # noqa: E402
from fallback_pilot.availability import probe_network  # noqa: E402


def test_network_probe_is_fast_regardless_of_outcome():
    """A DNS lookup with the network off blocked for ten seconds. The tier
    badge has to flip the moment Wi-Fi drops, so this must never block."""
    for host in ("1.1.1.1", "203.0.113.7", "www.example.invalid", ""):
        started = time.perf_counter()
        probe_network(host, 53, 0.4)
        assert time.perf_counter() - started < 1.0, f"{host!r} was slow"


def test_network_probe_returns_a_bool():
    assert isinstance(probe_network("1.1.1.1", 53, 0.4), bool)


def test_config_probe_host_is_an_ip_not_a_hostname():
    import socket
    host = cfgmod.load()["availability"]["network_probe_host"]
    socket.inet_aton(host)  # raises if it is a hostname


def test_ui_page_has_no_external_resources():
    """The demo switches the network off. Anything loaded from a CDN would
    fail at exactly the wrong moment."""
    import re
    html = (ROOT / "src" / "fallback_pilot" / "web" / "app.html").read_text(encoding="utf-8")
    # Comments explain why there is no CDN; only real markup counts.
    markup = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    assert not re.search(r"""(src|href)\s*=\s*["']https?://""", markup)
    assert not re.search(r"""@import|url\(\s*["']?https?://""", markup)
    assert "fonts.googleapis" not in markup


def test_ui_page_ships_with_the_package():
    import tomllib
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["fallback_pilot"]
    assert any("html" in p for p in patterns)


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_server_answers_status_and_streams_a_brief():
    from fallback_pilot.web.server import Handler, State
    from http.server import ThreadingHTTPServer

    # Build the index if it is missing, so the test does not depend on whether
    # someone happened to run `ingest` first.
    cfg = cfgmod.load()
    index_root = ROOT / cfg["context"].get("index_dir", "index")
    if not (index_root / "chunks.jsonl").exists():
        from fallback_pilot.ingest import ingest_paths, save_chunks
        chunks, _ = ingest_paths([str(ROOT / "demo_data")])
        save_chunks(chunks, index_root)

    Handler.state = State(cfg)
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        started = time.perf_counter()
        status = json.loads(urllib.request.urlopen(base + "/api/status", timeout=5).read())
        assert time.perf_counter() - started < 2.0, "status must not block the poll loop"
        assert status["tier"] in (0, 1, 2, 3)
        assert isinstance(status["network"], bool)

        page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert "Fallback" in page

        events, buf = [], ""
        stream = urllib.request.urlopen(base + "/api/brief?topic=renewal", timeout=60)
        for raw in stream:
            buf += raw.decode()
            while "\n\n" in buf:
                part, buf = buf.split("\n\n", 1)
                if part.startswith("data:"):
                    events.append(json.loads(part[5:]))

        kinds = [e["type"] for e in events]
        assert "retrieved" in kinds, "the UI needs sources before generation starts"
        assert "done" in kinds
        done = next(e for e in events if e["type"] == "done")
        assert done["sources"] and done["cited"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_server_binds_to_localhost_only():
    """This reads the user's files. It must not be reachable from the network."""
    source = (ROOT / "src" / "fallback_pilot" / "web" / "server.py").read_text(encoding="utf-8")
    assert '("127.0.0.1", port)' in source
    assert '"0.0.0.0"' not in source


def test_network_probe_requires_a_real_connection_not_just_a_route():
    """Windows keeps routes alive through WSL / Hyper-V / VPN adapters after
    the Wi-Fi is off, so a routing-table hit alone must not mean 'online'."""
    import fallback_pilot.availability as av

    original = av._route_exists
    try:
        av._route_exists = lambda ip, port, timeout: True   # pretend a route exists
        # 203.0.113.0/24 is TEST-NET-3: reserved, never routable to a listener.
        assert av.probe_network("203.0.113.7", 443, 0.3) is False
    finally:
        av._route_exists = original


def test_no_route_short_circuits_without_connecting():
    import fallback_pilot.availability as av

    original = av._route_exists
    calls = []
    try:
        av._route_exists = lambda ip, port, timeout: False
        started = time.perf_counter()
        assert av.probe_network("1.1.1.1", 443, 5.0) is False
        assert time.perf_counter() - started < 0.5, "must not attempt a connection"
    finally:
        av._route_exists = original


def test_model_probe_needs_a_non_empty_model_list():
    """Foundry keeps serving /models after everything is unloaded, so HTTP 200
    alone left the app stuck on tier 1 with no model loaded."""
    import fallback_pilot.availability as av

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    original = av.requests.get
    try:
        av.requests.get = lambda *a, **k: FakeResponse({"data": []})
        assert av.probe_local_model("http://localhost:1/v1") is False

        av.requests.get = lambda *a, **k: FakeResponse({"data": [{"id": "phi-4-mini"}]})
        assert av.probe_local_model("http://localhost:1/v1") is True
    finally:
        av.requests.get = original


def test_model_probe_survives_a_non_json_reply():
    import fallback_pilot.availability as av

    class Broken:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    original = av.requests.get
    try:
        av.requests.get = lambda *a, **k: Broken()
        assert av.probe_local_model("http://localhost:1/v1") is False
    finally:
        av.requests.get = original


def test_status_endpoint_never_blocks_on_a_probe():
    """The badge polls every two seconds; a 1.2s probe must not run inline."""
    from fallback_pilot.web.server import State

    state = State(cfgmod.load())
    for _ in range(5):
        started = time.perf_counter()
        state.status()
        assert time.perf_counter() - started < 0.05
