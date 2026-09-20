"""Things that happen without anyone asking.

Fallback Pilot's agent does not wait to be prompted. It watches three kinds of
signal and starts work on its own:

* a meeting approaching in the local calendar
* a file appearing or changing in a watched folder
* the capability tier changing - most importantly, connectivity disappearing

The third one carries the product's whole argument. When the network drops, the
window to prepare is closing, so the agent prepares *then* rather than waiting
for someone to realise they need it.

Everything here reads local state only. No polling of a cloud service, because
the agent has to keep working when there is no cloud to poll.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

CAL_SUFFIXES = {".ics"}


@dataclass
class Signal:
    """One observed event that might deserve work."""

    kind: str           # meeting | files_changed | tier_changed
    topic: str          # what a brief about this would be about
    reason: str         # human-readable, shown in the activity log
    urgency: int = 5    # 1 highest - used to order competing signals
    at: datetime = field(default_factory=datetime.now)
    detail: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Identity for deduplication - same meeting should not re-fire."""
        return f"{self.kind}:{self.detail.get('uid') or self.topic}"


# ----------------------------------------------------------------- calendar

def _ics_unfold(text: str) -> list[str]:
    """ICS wraps long lines with a leading space. Join them back first."""
    out: list[str] = []
    for line in text.splitlines():
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _ics_time(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M%SZ", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def read_calendar(paths: list[str]) -> list[dict]:
    """Parse local .ics files with the standard library.

    No calendar SDK and no mailbox connection: a cloud calendar would be
    unreachable in exactly the conditions this product is built for. An .ics
    file on disk is readable offline, and every calendar app can export one.
    """
    events: list[dict] = []
    for raw in paths:
        base = Path(raw).expanduser()
        candidates = (
            [base] if base.is_file()
            else [p for p in base.glob("**/*") if p.suffix.lower() in CAL_SUFFIXES]
            if base.is_dir() else []
        )
        for path in candidates:
            try:
                lines = _ics_unfold(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue

            current: dict | None = None
            for line in lines:
                if line.startswith("BEGIN:VEVENT"):
                    current = {"source": str(path)}
                elif line.startswith("END:VEVENT"):
                    if current and current.get("start") and current.get("summary"):
                        events.append(current)
                    current = None
                elif current is not None:
                    name, _, value = line.partition(":")
                    field_name = name.split(";")[0].upper()
                    if field_name == "SUMMARY":
                        current["summary"] = value.strip()
                    elif field_name == "DTSTART":
                        current["start"] = _ics_time(value)
                    elif field_name == "UID":
                        current["uid"] = value.strip()
                    elif field_name == "ATTENDEE":
                        found = re.search(r"mailto:([^;:\s]+)", value, re.I)
                        if found:
                            current.setdefault("attendees", []).append(found.group(1))
                    elif field_name == "DESCRIPTION":
                        current["description"] = value.strip()
    return [e for e in events if e.get("start")]


def meeting_signals(paths: list[str], lead_minutes: int, now: datetime | None = None) -> list[Signal]:
    now = now or datetime.now()
    horizon = now + timedelta(minutes=lead_minutes)
    out: list[Signal] = []

    for event in read_calendar(paths):
        start = event["start"]
        if not (now <= start <= horizon):
            continue
        minutes = int((start - now).total_seconds() // 60)
        # The closer the meeting, the more this matters.
        urgency = 1 if minutes <= 15 else 2 if minutes <= 60 else 3
        out.append(
            Signal(
                kind="meeting",
                topic=event["summary"],
                reason=f"'{event['summary']}' starts in {minutes} min",
                urgency=urgency,
                detail={
                    "uid": event.get("uid", event["summary"]),
                    "starts": start.isoformat(timespec="minutes"),
                    "minutes_away": minutes,
                    "attendees": event.get("attendees", []),
                },
            )
        )
    return out


# -------------------------------------------------------------------- files

def folder_fingerprint(paths: list[str]) -> str:
    """Cheap signature of a folder's contents: name, size and mtime."""
    import hashlib

    digest = hashlib.sha1()
    for raw in sorted(paths):
        base = Path(raw).expanduser()
        if not base.exists():
            continue
        files = [base] if base.is_file() else sorted(
            p for p in base.glob("**/*") if p.is_file() and not p.name.startswith("~$")
        )
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            digest.update(f"{path.name}|{stat.st_size}|{int(stat.st_mtime)}".encode())
    return digest.hexdigest()[:16]


def file_signal(paths: list[str], previous: str | None) -> tuple[Signal | None, str]:
    current = folder_fingerprint(paths)
    if previous is None or previous == current:
        return None, current
    return (
        Signal(
            kind="files_changed",
            topic="",  # filled in by the runner from what is already known
            reason="watched files changed on disk",
            urgency=4,
            detail={"fingerprint": current},
        ),
        current,
    )


# --------------------------------------------------------------------- tier

def tier_signal(previous: int | None, current: int, label: str) -> Signal | None:
    """Fire when capability changes.

    A drop matters far more than a recovery: losing the network means the
    window for preparing anything is closing, so the agent treats it as the
    most urgent signal it can receive.
    """
    if previous is None or previous == current:
        return None

    worsened = current > previous
    return Signal(
        kind="tier_changed",
        topic="",
        reason=(f"capability dropped to tier {current} ({label}) - "
                "preparing while it still can"
                if worsened else
                f"capability recovered to tier {current} ({label})"),
        urgency=1 if worsened else 6,
        detail={"from": previous, "to": current, "worsened": worsened},
    )
