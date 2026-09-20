from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULTS: dict[str, Any] = {
    "model": {"alias": "phi-4-mini", "max_tokens": 600, "temperature": 0.2},
    "runtime": {"endpoint": "", "candidate_ports": [5273, 5272, 8080, 51234], "timeout_seconds": 60},
    "availability": {
        "network_probe_host": "1.1.1.1",
        "network_probe_port": 443,
        "probe_timeout_seconds": 1.2,
        "allow_paid_cloud_ai": False,
    },
    "context": {"sources": ["demo_data"], "index_dir": "index"},
    "embeddings": {"enabled": True, "alias": "qwen3-embedding-0.6b"},
    "retrieval": {"top_k": 6, "max_per_source": 1, "brief_chunks": 8},
    "agent": {
        "enabled": True,
        "lead_minutes": 120,
        "interval_seconds": 30,
        "calendar_sources": ["demo_data"],
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else project_root() / "config.yaml"
    user: dict[str, Any] = {}
    if cfg_path.exists():
        user = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return _merge(_DEFAULTS, user)
