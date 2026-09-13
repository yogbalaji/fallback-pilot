import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fallback_pilot.availability import Tier, assess  # noqa: E402

BASE = {
    "availability": {
        "network_probe_host": "127.0.0.1",
        "network_probe_port": 9,
        "probe_timeout_seconds": 0.1,
        "allow_paid_cloud_ai": False,
    }
}


def test_no_endpoint_means_degraded():
    av = assess(BASE, None)
    assert av.tier == Tier.DEGRADED
    assert av.local_model is False


def test_extractive_always_available():
    from fallback_pilot.llm import ExtractiveBackend
    assert ExtractiveBackend().available() is True


def test_extractive_produces_bullets():
    from fallback_pilot.llm import ExtractiveBackend, Message
    text = (
        "The renewal decision is blocked on the security review. "
        "Priya owns the security review and is on leave until Thursday. "
        "The customer asked for pricing before the quarter closes. "
        "Legal has already approved the master agreement terms."
    )
    out = ExtractiveBackend(max_sentences=2).complete(
        [Message("user", text)], max_tokens=0, temperature=0
    )
    assert "Degraded mode" in out
    assert out.count("- ") >= 2
