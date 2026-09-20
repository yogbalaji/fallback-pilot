"""Actions the agent prepares but will not perform.

The agent drafts replies. It never sends them. Anything that would leave the
machine or reach another person stops here, in a queue, until a human approves
it - and the approval is recorded.

This is the boundary that makes an autonomous agent safe to run unattended:
it can read, analyse and prepare freely, but the irreversible step is always
someone else's decision.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

QUEUE_FILE = "agent_approvals.json"

PENDING = "pending"
APPROVED = "approved"
DISCARDED = "discarded"


@dataclass
class Approval:
    id: str
    action: str             # what would happen if approved
    subject: str
    body: str
    created: str
    topic: str = ""
    status: str = PENDING
    decided: str = ""
    decided_by: str = ""
    sources: list = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ApprovalQueue:
    """Nothing in here has happened. Everything in here is waiting on a person."""

    def __init__(self, root: str | Path):
        self.path = Path(root) / QUEUE_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError:
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, action: str, subject: str, body: str, topic: str = "",
            sources: list | None = None) -> Approval:
        item = Approval(
            id=uuid.uuid4().hex[:8],
            action=action,
            subject=subject,
            body=body,
            topic=topic,
            created=datetime.now().isoformat(timespec="seconds"),
            sources=sources or [],
        )
        items = self._load()
        items.append(item.to_dict())
        self._save(items)
        return item

    def pending(self) -> list[dict]:
        return [i for i in self._load() if i.get("status") == PENDING]

    def all(self) -> list[dict]:
        return list(reversed(self._load()))

    def decide(self, item_id: str, status: str, by: str = "user", note: str = "") -> dict | None:
        items = self._load()
        for item in items:
            if item["id"] == item_id:
                item["status"] = status
                item["decided"] = datetime.now().isoformat(timespec="seconds")
                item["decided_by"] = by
                if note:
                    item["note"] = note
                self._save(items)
                return item
        return None
