"""Talks to Foundry Local over its OpenAI-compatible REST endpoint.

Deliberately uses plain HTTP rather than a vendored SDK: the endpoint contract
is stable across SDK versions, and it keeps the demo machine's dependency
surface small. The SDK, when present, is used only to discover the port.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import requests

from .base import Backend, Message


def _endpoint_from_sdk() -> str | None:
    try:
        from foundry_local import FoundryLocalManager  # type: ignore
    except Exception:
        return None
    try:
        mgr = FoundryLocalManager()
        ep = getattr(mgr, "endpoint", None)
        return str(ep) if ep else None
    except Exception:
        return None


def _endpoint_from_cli() -> str | None:
    exe = shutil.which("foundry")
    if not exe:
        return None
    text = ""
    for args in (["server", "status"], ["status"]):
        try:
            out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=25)
            text = (out.stdout or "") + (out.stderr or "")
        except Exception:
            continue
        if "http" in text:
            break
    if "http" not in text:
        return None
    for token in text.replace(",", " ").split():
        if token.startswith("http://") or token.startswith("https://"):
            base = token.rstrip("/.")
            return base if base.endswith("/v1") else f"{base}/v1"
    return None


def _endpoint_from_probe(ports: list[int]) -> str | None:
    for port in ports:
        ep = f"http://localhost:{port}/v1"
        try:
            if requests.get(f"{ep}/models", timeout=1.5).status_code == 200:
                return ep
        except requests.RequestException:
            continue
    return None


def discover_endpoint(cfg: dict) -> str | None:
    """Configured value wins, then the SDK, then the CLI, then a port sweep."""
    configured = (cfg.get("runtime", {}).get("endpoint") or "").strip()
    if configured:
        return configured.rstrip("/")
    return (
        _endpoint_from_sdk()
        or _endpoint_from_cli()
        or _endpoint_from_probe(cfg["runtime"]["candidate_ports"])
    )


class FoundryLocalBackend(Backend):
    name = "foundry-local"

    def __init__(self, endpoint: str, model: str, timeout: int = 60):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            return requests.get(f"{self.endpoint}/models", timeout=2).status_code == 200
        except requests.RequestException:
            return False

    def resolved_model(self) -> str:
        """Foundry serves hardware-specific model ids; match our alias to one."""
        try:
            data = requests.get(f"{self.endpoint}/models", timeout=5).json()
        except Exception:
            return self.model
        ids = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
        if self.model in ids:
            return self.model
        for mid in ids:
            if self.model.lower() in mid.lower():
                return mid
        return ids[0] if ids else self.model

    def stream(self, messages: list[Message], *, max_tokens: int, temperature: float):
        """Yield tokens as they arrive.

        A brief takes tens of seconds on a laptop NPU. Watching it appear is a
        demo; watching a blank terminal for the same duration is a stall. The
        work is identical - only the waiting changes.
        """
        payload = {
            "model": self.resolved_model(),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        with requests.post(
            f"{self.endpoint}/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=self.timeout,
            stream=True,
        ) as r:
            r.raise_for_status()
            for raw in r.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                blob = raw[5:].strip()
                if blob == "[DONE]":
                    break
                try:
                    delta = json.loads(blob)["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError):
                    continue
                piece = delta.get("content")
                if piece:
                    yield piece

    def complete(self, messages: list[Message], *, max_tokens: int, temperature: float) -> str:
        payload = {
            "model": self.resolved_model(),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        r = requests.post(
            f"{self.endpoint}/chat/completions",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=self.timeout,
        )
        r.raise_for_status()
        body = r.json()
        return body["choices"][0]["message"]["content"].strip()
