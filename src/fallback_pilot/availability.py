"""The fallback ladder.

This is the part of Fallback Pilot that is actually novel, so it lives at the
centre of the app rather than being bolted on at the end. Everything else asks
this module 'what can I count on right now?' before it does any work.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from enum import IntEnum

import requests


class Tier(IntEnum):
    CLOUD_ASSISTED = 0   # network + sanctioned cloud AI reachable
    LOCAL_MODEL = 1      # network up, but core value must stay local
    OFFLINE_MODEL = 2    # no network at all; local model still serving
    DEGRADED = 3         # no model either; extractive fallback only


TIER_LABELS = {
    Tier.CLOUD_ASSISTED: "Cloud assisted",
    Tier.LOCAL_MODEL: "Local model (cloud AI withheld)",
    Tier.OFFLINE_MODEL: "Offline - local model",
    Tier.DEGRADED: "Degraded - no model, extractive only",
}


@dataclass
class Availability:
    network: bool
    local_model: bool
    cloud_ai_permitted: bool
    tier: Tier
    endpoint: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return TIER_LABELS[self.tier]


# Cloudflare's resolver, on 443 rather than 53: an anycast address that answers
# from almost anywhere, over a port a corporate firewall is unlikely to block.
ROUTE_PROBE_IP = "1.1.1.1"


def _route_exists(ip: str, port: int, timeout: float) -> bool:
    """Does the routing table have a path to this address?

    A UDP "connect" sends no packets - it only asks the OS which interface
    would carry the traffic - so this is a local lookup and costs microseconds.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        sock.connect((ip, port))
        local = sock.getsockname()[0]
        # 0.0.0.0 means no interface was selected; 169.254.x.x is a link-local
        # address, which means the adapter is up but got no DHCP lease.
        return local != "0.0.0.0" and not local.startswith("169.254.")
    except OSError:
        return False
    finally:
        sock.close()


def probe_network(host: str, port: int, timeout: float) -> bool:
    """Is there real connectivity?

    Two stages, because neither alone is trustworthy:

    1. Routing-table lookup. Instant, and a definitive NO when it fails.
    2. An actual TCP connection to an IP literal.

    Stage 2 is not optional on Windows. Virtual adapters - WSL, Hyper-V, a VPN
    client, Docker - keep a route alive after the Wi-Fi is switched off, so the
    routing table cheerfully reports a path to the internet that does not
    exist. An earlier version stopped at stage 1 and the tier badge never left
    tier 1 when the network went away.

    No hostname is ever resolved: a DNS lookup with the network down blocks for
    seconds, and this runs on a two-second poll.
    """
    target = host or ROUTE_PROBE_IP
    try:
        socket.inet_aton(target)
    except OSError:
        # A hostname was configured. Use the IP instead of resolving it, so an
        # old config.yaml cannot reintroduce the DNS stall.
        target = ROUTE_PROBE_IP
    port = port or 443

    if not _route_exists(target, port, timeout):
        return False

    try:
        with socket.create_connection((target, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_local_model(endpoint: str, timeout: float = 2.0) -> bool:
    """Is a model actually LOADED and ready to answer?

    Checking for HTTP 200 is not enough. Foundry Local's server keeps serving
    /models after every model has been unloaded, so a status code only tells
    you the daemon is alive - which is why unloading a model never moved the
    app to tier 3. The list has to be non-empty as well.
    """
    try:
        r = requests.get(f"{endpoint.rstrip('/')}/models", timeout=timeout)
        if r.status_code != 200:
            return False
        payload = r.json()
    except (requests.RequestException, ValueError):
        return False

    models = payload.get("data") if isinstance(payload, dict) else payload
    return bool(models)


def assess(cfg: dict, endpoint: str | None) -> Availability:
    av = cfg["availability"]
    notes: list[str] = []

    network = probe_network(
        av["network_probe_host"], av["network_probe_port"], av["probe_timeout_seconds"]
    )
    model_up = bool(endpoint) and probe_local_model(endpoint)
    cloud_ok = bool(av.get("allow_paid_cloud_ai")) and network

    if not model_up:
        tier = Tier.DEGRADED
        notes.append("No local model endpoint responding - using extractive fallback.")
    elif cloud_ok:
        tier = Tier.CLOUD_ASSISTED
    elif network:
        tier = Tier.LOCAL_MODEL
        notes.append("Network is up, but paid cloud AI is withheld by policy.")
    else:
        tier = Tier.OFFLINE_MODEL
        notes.append("No network. Everything below runs on this device.")

    return Availability(
        network=network,
        local_model=model_up,
        cloud_ai_permitted=cloud_ok,
        tier=tier,
        endpoint=endpoint,
        notes=notes,
    )
