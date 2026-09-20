"""An append-only record of everything the agent did while nobody was watching.

An agent that acts on its own is only acceptable if a person can afterwards see
exactly what it did and why. Every entry names the signal that triggered the
work, the decision taken, the reasoning, and the outcome - so the log answers
"why did it do that?", not merely "what happened?".

Plain JSONL on disk: readable in Notepad, diffable in git, and requiring no
tooling to audit.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

JOURNAL_FILE = "agent_activity.jsonl"


@dataclass
class Entry:
    at: str
    event: str              # triggered | decided | skipped | generated | queued | failed
    summary: str
    trigger: str = ""
    reasoning: str = ""
    tier: int | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Journal:
    def __init__(self, root: str | Path):
        self.path = Path(root) / JOURNAL_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, summary: str, **kw) -> Entry:
        entry = Entry(
            at=datetime.now().isoformat(timespec="seconds"),
            event=event,
            summary=summary,
            trigger=kw.pop("trigger", ""),
            reasoning=kw.pop("reasoning", ""),
            tier=kw.pop("tier", None),
            detail=kw.pop("detail", {}),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return entry

    def recent(self, limit: int = 40) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return list(reversed(out))   # newest first, for display
