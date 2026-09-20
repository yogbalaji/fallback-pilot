"""The agent loop: observe, decide, act, record.

No fixed sequence. Each cycle the agent looks at what it can currently observe -
the calendar, the files on disk, the capability tier, and what it has already
done - and works out what, if anything, is worth doing now. The same signal
produces different behaviour depending on the state around it:

* a meeting 10 minutes away outranks one 3 hours away
* a brief already written is not rewritten unless its sources changed
* losing the network promotes everything, because the window is closing
* at tier 3 the agent still produces a brief, extractively, and says so
* a draft reply is only prepared when someone is actually waiting on one

The loop is deliberately readable: for an agent that runs unattended, being
able to follow its reasoning matters more than being clever.
"""
from __future__ import annotations

import time
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ..availability import Tier, assess
from ..brief import gather, generate, generate_extractive, to_markdown
from ..ingest import ingest_paths, load_chunks, save_chunks
from ..llm import FoundryLocalBackend, discover_endpoint
from ..retrieve import build_retriever
from .approvals import ApprovalQueue
from .journal import Journal
from . import signals as sig

# Who is actually waiting on a reply from us?
#
# Weighted, because a flat keyword list gets this wrong. A colleague's handover
# note mentions deadlines and chasing, but that person is not waiting on an
# answer - they have gone. The phrases that genuinely mean "I asked you and you
# have not replied" score far higher than words that merely co-occur with them.
WAITING_HINTS = {
    "following up": 5,
    "third time": 5,
    "still do not have": 5,
    "still have not": 5,
    "please advise": 4,
    "i would rather not": 3,
    "evaluate alternatives": 3,
    "before i": 2,
    "waiting": 2,
    "escalat": 2,
    "chase": 1,
    "deadline": 1,
}
# Below this, treat it as ambient urgency rather than a person awaiting a reply.
WAITING_THRESHOLD = 5


STATE_FILE = "agent_state.json"


@dataclass
class AgentState:
    """Everything the agent remembers between cycles.

    Persisted to disk, because an agent that forgets what it has done will redo
    it after every restart - regenerating the same brief, re-queueing the same
    reply. Memory is what separates an agent from a command run repeatedly.
    """

    last_tier: int | None = None
    last_fingerprint: str | None = None
    handled: dict = field(default_factory=dict)   # signal key -> fingerprint acted on
    paused: bool = False

    @classmethod
    def load(cls, root: Path) -> "AgentState":
        path = Path(root) / STATE_FILE
        if not path.exists():
            return cls()
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError):
            return cls()

    def save(self, root: Path) -> None:
        path = Path(root) / STATE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


class Agent:
    def __init__(self, cfg: dict, on_event=None, on_token=None):
        self.cfg = cfg
        self.root = Path(cfg["context"].get("index_dir", "index"))
        self.journal = Journal(self.root)
        self.approvals = ApprovalQueue(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state = AgentState.load(self.root)
        self.on_event = on_event or (lambda *a, **k: None)
        self.on_token = on_token
        self._retriever = None
        self._retriever_fp = None

    # ------------------------------------------------------------- observing

    def observe(self) -> tuple[list[sig.Signal], dict]:
        """Gather every signal available right now, plus the context to judge them."""
        agent_cfg = self.cfg.get("agent", {})
        sources = self.cfg["context"]["sources"]

        endpoint = discover_endpoint(self.cfg)
        av = assess(self.cfg, endpoint)

        found: list[sig.Signal] = []

        # 1. Capability change. Checked first because it re-prioritises the rest.
        tier_sig = sig.tier_signal(self.state.last_tier, int(av.tier), av.label)
        if tier_sig:
            found.append(tier_sig)
        self.state.last_tier = int(av.tier)

        # 2. Meetings coming up in the local calendar.
        cal_paths = agent_cfg.get("calendar_sources") or sources
        found.extend(sig.meeting_signals(cal_paths, agent_cfg.get("lead_minutes", 120)))

        # 3. Files appearing or changing on disk.
        file_sig, fingerprint = sig.file_signal(sources, self.state.last_fingerprint)
        self.state.last_fingerprint = fingerprint
        if file_sig:
            found.append(file_sig)

        return found, {"availability": av, "endpoint": endpoint, "fingerprint": fingerprint}

    # -------------------------------------------------------------- deciding

    def decide(self, found: list[sig.Signal], context: dict) -> tuple[sig.Signal | None, str]:
        """Pick the one thing most worth doing, and say why.

        Returns (signal, reasoning). A None signal means 'nothing worth doing',
        which is itself a decision worth recording.
        """
        if self.state.paused:
            return None, "agent is paused by the user"
        if not found:
            return None, "nothing changed since the last check"

        av = context["availability"]
        fingerprint = context["fingerprint"]

        # Losing capability promotes every pending meeting: the chance to
        # prepare is disappearing, so prepare now rather than on schedule.
        dropping = any(s.kind == "tier_changed" and s.detail.get("worsened") for s in found)

        ranked = sorted(found, key=lambda s: (s.urgency, s.at))
        for signal in ranked:
            # A bare tier or file signal has no topic of its own. It matters
            # because of what it implies for upcoming work, so re-point it at
            # the nearest meeting; with none, there is nothing to prepare for.
            if not signal.topic:
                meetings = [s for s in found if s.kind == "meeting"]
                if not meetings:
                    continue
                nearest = min(meetings, key=lambda s: s.detail.get("minutes_away", 9999))
                signal = sig.Signal(
                    kind=signal.kind,
                    topic=nearest.topic,
                    reason=f"{signal.reason}; nearest work is '{nearest.topic}'",
                    urgency=signal.urgency,
                    detail={**signal.detail, "uid": nearest.detail.get("uid")},
                )

            already = self.state.handled.get(signal.key)
            if already == fingerprint and not dropping:
                continue  # done, and nothing has changed since

            if already and already != fingerprint:
                return signal, ("a brief for this already exists, but the underlying "
                                "files changed - refreshing it")
            if dropping and signal.kind != "tier_changed":
                return signal, ("capability is dropping, so this was brought forward "
                                "rather than waiting for its schedule")
            if signal.kind == "meeting":
                minutes = signal.detail.get("minutes_away", "?")
                return signal, (f"meeting in {minutes} min and no brief exists yet"
                                + (f"; running at tier {int(av.tier)}" if av.tier else ""))
            return signal, signal.reason

        return None, "every signal has already been handled and nothing has changed"

    # ----------------------------------------------------------------- acting

    def _retriever_for(self, endpoint, fingerprint):
        """Rebuild the index only when the files behind it actually changed."""
        if self._retriever is not None and self._retriever_fp == fingerprint:
            return self._retriever
        chunks, _ = ingest_paths(self.cfg["context"]["sources"])
        save_chunks(chunks, self.root)
        retriever = build_retriever(self.cfg, chunks, endpoint)
        retriever.prepare()
        self._retriever, self._retriever_fp = retriever, fingerprint
        return retriever

    def _someone_waiting(self, retriever) -> str:
        """Who is waiting on a reply from us?

        Scans the whole corpus rather than the chunks gathered for the brief.
        These are different questions: the brief answers "what do I need to
        know", while this asks "is anyone expecting something from me". The
        sentence that proves someone is waiting often sits in a part of an
        email the brief had no reason to retrieve.

        Returns an address only when the evidence is strong - preparing a draft
        for the wrong person is worse than preparing none, so "nobody" is a
        perfectly good answer.
        """
        scores: dict[str, int] = {}
        for chunk in retriever.chunks:
            sender = chunk.meta.get("from", "")
            if not sender:
                continue
            low = chunk.text.lower()
            score = sum(weight for phrase, weight in WAITING_HINTS.items() if phrase in low)
            if score:
                scores[sender] = scores.get(sender, 0) + score

        if not scores:
            return ""
        sender, score = max(scores.items(), key=lambda kv: kv[1])
        return sender if score >= WAITING_THRESHOLD else ""

    def act(self, signal: sig.Signal, reasoning: str, context: dict) -> dict:
        av = context["availability"]
        endpoint = context["endpoint"]
        fingerprint = context["fingerprint"]

        self.journal.record(
            "triggered", signal.reason, trigger=signal.kind, tier=int(av.tier),
            detail=signal.detail,
        )
        self.on_event("triggered", signal.reason)
        self.journal.record("decided", f"prepare a brief on '{signal.topic}'",
                            trigger=signal.kind, reasoning=reasoning, tier=int(av.tier))
        self.on_event("decided", reasoning)

        retriever = self._retriever_for(endpoint, fingerprint)
        hits = gather(retriever, signal.topic, self.cfg["retrieval"].get("brief_chunks", 8))
        if not hits:
            self.journal.record("skipped", "no local context matched", trigger=signal.kind)
            return {"ok": False}

        files = len({h.chunk.source for h in hits})
        self.on_event("reading", f"gathered {len(hits)} extracts from {files} files")

        waiting_on = self._someone_waiting(retriever)
        if waiting_on:
            self.on_event("reading", f"{waiting_on} appears to be waiting on a reply")

        try:
            if av.tier == Tier.DEGRADED:
                brief = generate_extractive(signal.topic, hits, av)
            else:
                backend = FoundryLocalBackend(
                    endpoint, self.cfg["model"]["alias"], self.cfg["runtime"]["timeout_seconds"]
                )
                brief = generate(
                    signal.topic, hits, backend, av,
                    max_tokens=self.cfg["model"]["max_tokens"],
                    temperature=self.cfg["model"]["temperature"],
                    with_draft=bool(waiting_on),
                    on_token=self.on_token,
                    recipient=waiting_on,
                )
        except Exception as exc:
            self.journal.record("failed", f"{type(exc).__name__} - fell back to extraction",
                                trigger=signal.kind, tier=int(av.tier))
            brief = generate_extractive(signal.topic, hits, av)

        out_dir = self.root / "briefs"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in " -_" else "" for c in signal.topic)[:60].strip()
        path = out_dir / f"{datetime.now():%Y%m%d-%H%M}-{safe or 'brief'}.md"
        path.write_text(to_markdown(brief), encoding="utf-8")

        self.journal.record(
            "generated",
            f"brief on '{signal.topic}' - {len(brief.cited)} of {len(brief.sources)} sources cited",
            trigger=signal.kind, tier=int(av.tier),
            detail={"file": str(path), "seconds": round(brief.seconds, 1),
                    "grounded": brief.grounded},
        )
        self.on_event("generated", f"brief ready: {path.name}")

        # Anything the model reported about itself belongs in the log. An agent
        # that silently produces nothing is impossible to trust or debug.
        for note in brief.notes:
            self.journal.record("skipped", note, trigger=signal.kind, tier=int(av.tier))

        if waiting_on and not brief.draft:
            self.journal.record(
                "skipped",
                f"{waiting_on} is waiting, but no reply could be drafted - "
                "nothing queued for approval",
                trigger=signal.kind, tier=int(av.tier),
                reasoning="the model returned an empty draft; see the notes above",
            )
            self.on_event("skipped", "no reply could be drafted - see activity log")
        elif not waiting_on:
            self.journal.record(
                "skipped", "nobody appears to be waiting on a reply - no draft prepared",
                trigger=signal.kind, tier=int(av.tier),
            )

        # A reply is prepared, never sent. It waits for a person.
        if brief.draft and waiting_on:
            subject = ""
            body = brief.draft
            if body.lower().startswith("subject:"):
                first, _, rest = body.partition("\n")
                subject = first.split(":", 1)[1].strip()
                body = rest.strip()
            item = self.approvals.add(
                action=f"Send this reply to {waiting_on}",
                subject=subject or signal.topic,
                body=body,
                topic=signal.topic,
                sources=brief.sources,
            )
            self.journal.record(
                "queued", f"reply to {waiting_on} is waiting for your approval - not sent",
                trigger=signal.kind, tier=int(av.tier), detail={"approval_id": item.id},
            )
            self.on_event("queued", f"a reply to {waiting_on} needs your approval")

        self.state.handled[signal.key] = fingerprint
        return {"ok": True, "brief": brief, "path": str(path)}

    # ------------------------------------------------------------------ loop

    def cycle(self) -> dict:
        found, context = self.observe()
        signal, reasoning = self.decide(found, context)
        if signal is None:
            self.state.save(self.root)
            return {"acted": False, "reason": reasoning,
                    "tier": int(context["availability"].tier)}
        result = self.act(signal, reasoning, context)
        self.state.save(self.root)
        return {"acted": result.get("ok", False), "topic": signal.topic,
                "trigger": signal.kind, "reason": reasoning,
                "tier": int(context["availability"].tier), "path": result.get("path")}

    def pause(self, paused: bool = True) -> None:
        """A person taking control back. Recorded, like everything else."""
        self.state.paused = paused
        self.state.save(self.root)
        self.journal.record("decided", "paused by user" if paused else "resumed by user",
                            trigger="user")

    def forget(self, key: str | None = None) -> None:
        """Override: make the agent redo work it thinks is already done."""
        if key:
            self.state.handled.pop(key, None)
        else:
            self.state.handled.clear()
        self.state.save(self.root)
        self.journal.record("decided", f"user cleared memory for {key or 'everything'}",
                            trigger="user")

    def run(self, interval: int = 30, once: bool = False):
        self.journal.record("triggered", "agent started watching",
                            trigger="startup",
                            reasoning="watching calendar, files and capability tier")
        while True:
            yield self.cycle()
            if once:
                return
            time.sleep(interval)
