import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fallback_pilot import config as cfgmod  # noqa: E402
from fallback_pilot.agent import signals as sig  # noqa: E402
from fallback_pilot.agent.approvals import APPROVED, PENDING, ApprovalQueue  # noqa: E402
from fallback_pilot.agent.journal import Journal  # noqa: E402
from fallback_pilot.agent.runner import Agent, AgentState  # noqa: E402

DEMO = ROOT / "demo_data"


# --------------------------------------------------------------- triggers

def test_calendar_is_parsed_from_local_ics():
    """A cloud calendar would be unreachable exactly when this matters."""
    events = sig.read_calendar([str(DEMO)])
    assert events, "demo calendar should parse - run scripts/set_demo_meeting.py"
    assert any("Northwind" in e["summary"] for e in events)
    assert all(isinstance(e["start"], datetime) for e in events)


def test_meeting_attendees_are_extracted():
    events = sig.read_calendar([str(DEMO)])
    call = next(e for e in events if "Northwind" in e["summary"])
    assert any("northwindtraders" in a for a in call.get("attendees", []))


def test_only_meetings_inside_the_lead_window_fire():
    now = datetime.now()
    signals = sig.meeting_signals([str(DEMO)], lead_minutes=1, now=now + timedelta(days=400))
    assert signals == [], "a meeting long past must not trigger anything"


def test_closer_meetings_are_more_urgent():
    a = sig.Signal(kind="meeting", topic="soon", reason="", urgency=1)
    b = sig.Signal(kind="meeting", topic="later", reason="", urgency=3)
    assert sorted([b, a], key=lambda s: s.urgency)[0].topic == "soon"


def test_file_change_is_detected(tmp_path):
    (tmp_path / "a.md").write_text("one", encoding="utf-8")
    signal, first = sig.file_signal([str(tmp_path)], None)
    assert signal is None, "the first observation is a baseline, not a change"

    signal, second = sig.file_signal([str(tmp_path)], first)
    assert signal is None and second == first, "nothing changed"

    (tmp_path / "b.md").write_text("two", encoding="utf-8")
    signal, third = sig.file_signal([str(tmp_path)], first)
    assert signal is not None and third != first


def test_losing_capability_is_the_most_urgent_signal():
    worse = sig.tier_signal(1, 3, "Degraded")
    better = sig.tier_signal(3, 1, "Local model")
    assert worse.urgency < better.urgency, "a drop must outrank a recovery"
    assert worse.detail["worsened"] is True
    assert "while it still can" in worse.reason


def test_no_tier_signal_when_nothing_changed():
    assert sig.tier_signal(2, 2, "Offline") is None
    assert sig.tier_signal(None, 2, "Offline") is None


# --------------------------------------------------------------- decisions

def _agent(tmp_path):
    cfg = cfgmod.load()
    cfg["context"] = dict(cfg["context"], index_dir=str(tmp_path))
    return Agent(cfg)


def _ctx(tier=1):
    class Av:
        label = "test"
    av = Av()
    av.tier = tier
    return {"availability": av, "endpoint": None, "fingerprint": "fp1"}


def test_agent_does_nothing_when_nothing_happened(tmp_path):
    agent = _agent(tmp_path)
    signal, why = agent.decide([], _ctx())
    assert signal is None
    assert "nothing changed" in why


def test_paused_agent_refuses_to_act(tmp_path):
    agent = _agent(tmp_path)
    agent.pause(True)
    signal, why = agent.decide([sig.Signal("meeting", "x", "y", 1)], _ctx())
    assert signal is None and "paused" in why


def test_agent_skips_work_it_already_did(tmp_path):
    agent = _agent(tmp_path)
    meeting = sig.Signal("meeting", "Renewal", "starts soon", 1, detail={"uid": "u1"})
    agent.state.handled[meeting.key] = "fp1"
    signal, why = agent.decide([meeting], _ctx())
    assert signal is None
    assert "already been handled" in why


def test_agent_redoes_work_when_the_sources_changed(tmp_path):
    """Same meeting, different files - the brief is stale and must be redone."""
    agent = _agent(tmp_path)
    meeting = sig.Signal("meeting", "Renewal", "starts soon", 1, detail={"uid": "u1"})
    agent.state.handled[meeting.key] = "OLD-FINGERPRINT"
    signal, why = agent.decide([meeting], _ctx())
    assert signal is not None
    assert "files changed" in why


def test_losing_the_network_brings_work_forward(tmp_path):
    """The window to prepare is closing, so schedule stops mattering."""
    agent = _agent(tmp_path)
    meeting = sig.Signal("meeting", "Renewal", "in 90 min", 3, detail={"uid": "u1"})
    drop = sig.tier_signal(1, 2, "Offline")
    signal, why = agent.decide([meeting, drop], _ctx(tier=2))
    assert signal is not None
    assert "capability" in why.lower() or "dropping" in why.lower()


def test_a_contextless_signal_is_pointed_at_the_nearest_meeting(tmp_path):
    agent = _agent(tmp_path)
    near = sig.Signal("meeting", "Renewal call", "soon", 2,
                      detail={"uid": "u1", "minutes_away": 20})
    far = sig.Signal("meeting", "Pipeline review", "later", 3,
                     detail={"uid": "u2", "minutes_away": 200})
    drop = sig.tier_signal(1, 3, "Degraded")
    signal, _ = agent.decide([drop, near, far], _ctx(tier=3))
    assert signal.topic == "Renewal call", "should prepare for the nearest work"


def test_a_bare_signal_with_no_meetings_is_ignored(tmp_path):
    """A file change with nothing upcoming is not worth waking up for."""
    agent = _agent(tmp_path)
    signal, why = agent.decide([sig.Signal("files_changed", "", "files moved", 4)], _ctx())
    assert signal is None


# ------------------------------------------------------------- persistence

def test_agent_remembers_across_restarts(tmp_path):
    first = _agent(tmp_path)
    first.state.handled["meeting:u1"] = "fp1"
    first.state.save(first.root)

    second = _agent(tmp_path)
    assert second.state.handled.get("meeting:u1") == "fp1", (
        "an agent that forgets will redo everything after a restart"
    )


def test_user_can_force_the_agent_to_redo_work(tmp_path):
    agent = _agent(tmp_path)
    agent.state.handled["meeting:u1"] = "fp1"
    agent.forget("meeting:u1")
    assert "meeting:u1" not in agent.state.handled


# ---------------------------------------------------------------- oversight

def test_journal_records_why_not_just_what(tmp_path):
    journal = Journal(tmp_path)
    journal.record("decided", "prepare a brief", trigger="meeting",
                   reasoning="meeting in 20 min and no brief exists", tier=2)
    entry = journal.recent()[0]
    assert entry["reasoning"], "an autonomous action must record its reasoning"
    assert entry["trigger"] == "meeting"
    assert entry["tier"] == 2


def test_journal_is_append_only_and_newest_first(tmp_path):
    journal = Journal(tmp_path)
    for i in range(3):
        journal.record("generated", f"brief {i}")
    entries = journal.recent()
    assert len(entries) == 3
    assert entries[0]["summary"] == "brief 2"


def test_queued_replies_are_never_sent(tmp_path):
    """The agent prepares. A person decides. That boundary is the safety story."""
    queue = ApprovalQueue(tmp_path)
    item = queue.add(action="Send this reply to dana@example.com",
                     subject="Renewal", body="We will send the pack.")
    assert item.status == PENDING
    assert len(queue.pending()) == 1


def test_approval_is_recorded_with_who_and_when(tmp_path):
    queue = ApprovalQueue(tmp_path)
    item = queue.add(action="Send reply", subject="s", body="b")
    decided = queue.decide(item.id, APPROVED, by="user")
    assert decided["status"] == APPROVED
    assert decided["decided"] and decided["decided_by"] == "user"
    assert queue.pending() == []
    assert len(queue.all()) == 1, "history must survive the decision"


def test_discarded_items_leave_the_queue_but_stay_in_history(tmp_path):
    queue = ApprovalQueue(tmp_path)
    item = queue.add(action="Send reply", subject="s", body="b")
    queue.decide(item.id, "discarded")
    assert queue.pending() == []
    assert queue.all()[0]["status"] == "discarded"


def test_deciding_an_unknown_id_is_safe(tmp_path):
    assert ApprovalQueue(tmp_path).decide("nope", APPROVED) is None


# ------------------------------------------------- who is waiting on a reply

def test_agent_identifies_who_is_actually_waiting():
    """A colleague's handover mentions deadlines, but they are not waiting.
    The customer chasing for the third time is."""
    from fallback_pilot.ingest import ingest_paths
    from fallback_pilot.retrieve.hybrid import HybridRetriever

    cfg = cfgmod.load()
    agent = Agent(cfg)
    chunks, _ = ingest_paths([str(DEMO)])
    retriever = HybridRetriever(chunks, embedder=None)
    retriever.prepare()

    who = agent._someone_waiting(retriever)
    assert "dana" in who.lower(), f"expected the escalating customer, got {who!r}"
    assert "priya" not in who.lower(), "the colleague on leave is not waiting"


def test_no_draft_is_prepared_when_nobody_is_waiting():
    from fallback_pilot.ingest.chunker import Chunk
    from fallback_pilot.retrieve.hybrid import HybridRetriever

    quiet = [Chunk("c1", "Routine status update, nothing outstanding.", "a.eml", "a",
                   "email from bob@example.com", "email", 0, {"from": "bob@example.com"})]
    retriever = HybridRetriever(quiet, embedder=None)
    retriever.prepare()
    assert Agent(cfgmod.load())._someone_waiting(retriever) == ""


def test_agent_queues_a_reply_when_a_model_is_available(tmp_path):
    """The full path: brief generated -> someone is waiting -> reply queued.

    Cannot be exercised without a model, so the model is faked. This is the
    path that produces the approval card the oversight story depends on.
    """
    import fallback_pilot.agent.runner as runner
    from fallback_pilot.availability import Tier

    class FakeModel:
        name, model = "fake", "phi-4-mini"

        def available(self):
            return True

        def complete(self, messages, *, max_tokens, temperature):
            if "Write an email" in messages[-1].content:
                return "Subject: Renewal\n\nDear Dana,\n\nWe will send the pack.\n\nRegards,"
            return "## Situation\nBlocked on security evidence [1].\n"

    class FakeAv:
        tier, label = Tier.LOCAL_MODEL, "Local model"
        network = local_model = True

    original = runner.FoundryLocalBackend
    runner.FoundryLocalBackend = lambda *a, **k: FakeModel()
    try:
        cfg = cfgmod.load()
        cfg["context"] = dict(cfg["context"], index_dir=str(tmp_path))
        agent = Agent(cfg)
        found, ctx = agent.observe()
        ctx["availability"], ctx["endpoint"] = FakeAv(), "http://localhost:1/v1"
        meeting = next(s for s in found if s.kind == "meeting")

        agent.act(meeting, "test", ctx)

        pending = agent.approvals.pending()
        assert len(pending) == 1, "a reply should be waiting for approval"
        assert "dana" in pending[0]["action"].lower()
        assert pending[0]["status"] == "pending", "it must NOT be sent"
    finally:
        runner.FoundryLocalBackend = original


def test_watch_once_does_not_claim_to_be_polling():
    """It printed 'Checking every 30s. Ctrl+C to stop' during a single cycle,
    which reads as idle - and a user killed a brief mid-generation because
    of it."""
    source = (ROOT / "src" / "fallback_pilot" / "cli.py").read_text(encoding="utf-8")
    assert "do not interrupt it" in source
    assert "this takes 60-90s" in source


def test_empty_first_draft_is_retried_compactly(tmp_path):
    """Observed on real hardware: phi-4-mini produced a good brief then an
    empty draft, and no approval was queued. A small model's context is full
    by then, so the retry drops the source block."""
    import fallback_pilot.agent.runner as runner
    from fallback_pilot.availability import Tier

    class PickyModel:
        name, model = "fake", "phi-4-mini"

        def available(self):
            return True

        def complete(self, messages, *, max_tokens, temperature):
            user = messages[-1].content
            if "Write a short email" in user:
                return "Subject: Renewal\n\nDear Dana,\n\nPack by 5 September.\n\nRegards,"
            if "Write an email that" in user:
                return ""
            return "## Situation\nBlocked [1].\n"

    class FakeAv:
        tier, label = Tier.LOCAL_MODEL, "Local model"
        network = local_model = True

    original = runner.FoundryLocalBackend
    runner.FoundryLocalBackend = lambda *a, **k: PickyModel()
    try:
        cfg = cfgmod.load()
        cfg["context"] = dict(cfg["context"], index_dir=str(tmp_path))
        agent = Agent(cfg)
        found, ctx = agent.observe()
        ctx["availability"], ctx["endpoint"] = FakeAv(), "http://localhost:1/v1"
        agent.act(next(s for s in found if s.kind == "meeting"), "test", ctx)
        assert len(agent.approvals.pending()) == 1, "the retry should have produced a draft"
    finally:
        runner.FoundryLocalBackend = original


def test_agent_explains_why_nothing_was_queued(tmp_path):
    """Silence is the bug. If no approval appears, the log must say why."""
    import fallback_pilot.agent.runner as runner
    from fallback_pilot.availability import Tier

    class SilentModel:
        name, model = "fake", "phi-4-mini"

        def available(self):
            return True

        def complete(self, messages, *, max_tokens, temperature):
            if "email" in messages[-1].content.lower():
                return ""
            return "## Situation\nBlocked [1].\n"

    class FakeAv:
        tier, label = Tier.LOCAL_MODEL, "Local model"
        network = local_model = True

    original = runner.FoundryLocalBackend
    runner.FoundryLocalBackend = lambda *a, **k: SilentModel()
    try:
        cfg = cfgmod.load()
        cfg["context"] = dict(cfg["context"], index_dir=str(tmp_path))
        agent = Agent(cfg)
        found, ctx = agent.observe()
        ctx["availability"], ctx["endpoint"] = FakeAv(), "http://localhost:1/v1"
        agent.act(next(s for s in found if s.kind == "meeting"), "test", ctx)

        summaries = " ".join(e["summary"] for e in agent.journal.recent(10))
        assert "no reply could be drafted" in summaries
        assert "empty draft" in summaries
    finally:
        runner.FoundryLocalBackend = original
