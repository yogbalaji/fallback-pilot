import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fallback_pilot.availability import Availability, Tier  # noqa: E402
from fallback_pilot.brief import generate, generate_extractive, to_markdown  # noqa: E402
from fallback_pilot.brief.generate import _citations, _split_sections  # noqa: E402
from fallback_pilot.ingest import ingest_paths  # noqa: E402
from fallback_pilot.llm.base import Backend  # noqa: E402
from fallback_pilot.retrieve.hybrid import HybridRetriever  # noqa: E402

DEMO = ROOT / "demo_data"

AV = Availability(network=False, local_model=True, cloud_ai_permitted=False,
                  tier=Tier.OFFLINE_MODEL)
AV_DEGRADED = Availability(network=False, local_model=False,
                           cloud_ai_permitted=False, tier=Tier.DEGRADED)


def _hits(query="renewal blocker", k=4):
    chunks, _ = ingest_paths([str(DEMO)])
    r = HybridRetriever(chunks, embedder=None)
    r.prepare()
    return r.search(query, top_k=k, per_source=1)


class FakeModel(Backend):
    """Stands in for a local model so brief logic is testable without one."""
    name = "fake"
    model = "fake-1b"

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def available(self):
        return True

    def complete(self, messages, *, max_tokens, temperature):
        self.calls.append(messages)
        return self.reply


GOOD = """## Situation
The renewal is blocked on security evidence [1]. The deadline is 12 September [2].

## Open actions
- Produce the SOC 2 evidence pack [1]

## Blockers and risks
- Dana will not approve without it [2]

## Recommended next step
Send the SOC 2 pack before 12 September [1].
"""


def test_sections_are_parsed():
    s = _split_sections(GOOD)
    assert "blocked on security" in s["Situation"]
    assert "SOC 2" in s["Open actions"]
    assert "Dana" in s["Blockers and risks"]
    assert s["Recommended next step"]


def test_sections_tolerate_bold_headings():
    """Small models drift on heading format; parsing must not be brittle."""
    s = _split_sections("**Situation**\nThings are late.\n\n**Open Actions**\n- Do it")
    assert "late" in s["Situation"]
    assert "Do it" in s["Open actions"]


def test_unstructured_output_is_not_discarded():
    s = _split_sections("The renewal is blocked and nobody used a heading.")
    assert "blocked" in s["Situation"]


def test_citation_parsing():
    assert _citations("a [1] b [2,3] c [10]") == {1, 2, 3, 10}
    assert _citations("no citations here") == set()


def test_invented_citations_are_flagged():
    """A model citing a source it was never given must not pass silently."""
    hits = _hits(k=3)
    brief = generate("renewal", hits, FakeModel("Claim [1] and claim [99]."),
                     AV, with_draft=False)
    assert 99 in brief.invented
    assert brief.grounded is False
    assert any("99" in n for n in brief.notes)


def test_valid_citations_are_accepted():
    hits = _hits(k=3)
    brief = generate("renewal", hits, FakeModel(GOOD), AV, with_draft=False)
    assert brief.invented == set()
    assert brief.grounded is True
    assert brief.cited <= {1, 2, 3}


def test_missing_citations_are_reported():
    hits = _hits(k=3)
    brief = generate("renewal", hits, FakeModel("A brief with no sources at all."),
                     AV, with_draft=False)
    assert any("no citations" in n.lower() for n in brief.notes)


def test_sources_are_numbered_in_the_prompt():
    hits = _hits(k=3)
    model = FakeModel(GOOD)
    generate("renewal", hits, model, AV, with_draft=False)
    prompt = model.calls[0][1].content
    assert "[1]" in prompt and "[3]" in prompt


def test_draft_failure_does_not_lose_the_brief():
    class DraftBreaks(FakeModel):
        def complete(self, messages, *, max_tokens, temperature):
            self.calls.append(messages)
            if len(self.calls) > 1:
                raise ConnectionError("model died mid-draft")
            return GOOD

    brief = generate("renewal", _hits(k=3), DraftBreaks(GOOD), AV)
    assert brief.sections["Situation"], "the brief must survive a draft failure"
    assert brief.draft == ""
    # Both the first attempt and the compact retry are reported, by name.
    assert any("failed" in n.lower() for n in brief.notes)
    assert any("ConnectionError" in n for n in brief.notes)


def test_extractive_brief_needs_no_model():
    brief = generate_extractive("renewal", _hits(k=4), AV_DEGRADED)
    assert brief.tier == int(Tier.DEGRADED)
    assert brief.sections["Situation"]
    assert brief.sources
    assert brief.grounded


def test_extractive_brief_skips_email_headers():
    brief = generate_extractive("renewal", _hits("customer escalation", 4), AV_DEGRADED)
    assert "From:" not in brief.sections["Situation"]


def test_markdown_lists_every_source():
    brief = generate("renewal", _hits(k=3), FakeModel(GOOD), AV, with_draft=False)
    md = to_markdown(brief)
    assert "## Sources" in md
    assert all(c.split(" - ")[0] in md for c in brief.sources)
    assert "No data left this machine" in md


def test_brief_draws_on_several_files():
    """A brief built from one file is a summary, not a brief."""
    hits = _hits("Northwind renewal", k=6)
    assert len({h.chunk.source for h in hits}) >= 4


def test_gather_pulls_the_facts_a_brief_needs():
    """One query is not enough. Measured: 4/5 facts single-query, 5/5 multi."""
    import re
    from fallback_pilot.brief import gather
    chunks, _ = ingest_paths([str(DEMO)])
    r = HybridRetriever(chunks, embedder=None)
    r.prepare()
    hits = gather(r, "Northwind renewal - what do I need to know before the call")
    blob = " ".join(h.chunk.text for h in hits).lower()
    for name, pattern in {
        "SOC 2": r"soc\s*2",
        "the real deadline": r"12\s+september",
        "the pricing floor": r"1\.18",
        "the discount ask": r"15\s*%",
        "the blocker's name": r"\bdana\b",
    }.items():
        assert re.search(pattern, blob), f"{name} never reached the model"


def test_gather_spans_most_of_the_corpus():
    from fallback_pilot.brief import gather
    chunks, _ = ingest_paths([str(DEMO)])
    r = HybridRetriever(chunks, embedder=None)
    r.prepare()
    hits = gather(r, "Northwind renewal")
    assert len({h.chunk.source for h in hits}) >= 5


def test_trailing_commentary_is_stripped():
    """Observed: a model appended 'This email adheres to the guidelines...'."""
    from fallback_pilot.brief.generate import _clean_draft
    out = _clean_draft(
        "Subject: Renewal update\n\nWe will send the pack by Friday.\n\n"
        "Best regards,\nSam\n\n---\n\nThis email adheres to the guidelines."
    )
    assert "adheres to the guidelines" not in out
    assert "send the pack" in out


def test_uncited_brief_triggers_one_retry():
    class TwoTries(FakeModel):
        def complete(self, messages, *, max_tokens, temperature):
            self.calls.append(messages)
            return "No citations at all." if len(self.calls) == 1 else GOOD

    model = TwoTries("")
    brief = generate("renewal", _hits(k=3), model, AV, with_draft=False)
    assert len(model.calls) == 2, "an uncited brief must be challenged once"
    assert brief.cited
    assert any("asked the model again" in n for n in brief.notes)


def test_prompt_shows_the_required_shape():
    """Structure must be shown, but as a skeleton with nothing copyable."""
    model = FakeModel(GOOD)
    generate("renewal", _hits(k=3), model, AV, with_draft=False)
    prompt = model.calls[0][1].content
    assert "## Situation" in prompt
    assert "<action>" in prompt, "the shape must be a skeleton, not a sample brief"


LEAKED = """## Situation
<where things stand, from the sources> [1].

## Open actions
- <action>, owner <name from a source>, due <date> [2]
"""


def test_template_leak_is_detected():
    """phi-4-mini reproduced the prompt skeleton as though it were fact."""
    brief = generate("renewal", _hits(k=3), FakeModel(LEAKED), AV, with_draft=False)
    assert brief.template_leak
    assert brief.grounded is False
    assert any("reproduced the prompt template" in n for n in brief.notes)


def test_real_output_is_not_flagged_as_leak():
    brief = generate("renewal", _hits(k=3), FakeModel(GOOD), AV, with_draft=False)
    assert brief.template_leak is False
    assert brief.grounded is True


def test_prompt_example_carries_no_copyable_facts():
    """The skeleton must contain no names, dates or amounts to steal."""
    import re
    from fallback_pilot.brief import prompts
    assert "Sam Doe" not in prompts.EXAMPLE
    assert not re.search(r"\b\d{1,2}\s+(January|March|May|June|August)\b", prompts.EXAMPLE)
    assert not re.search(r"\b\d+%", prompts.EXAMPLE)
    assert "<action>" in prompts.EXAMPLE


def test_draft_strips_citation_lines():
    """Observed: phi-4-mini appended '[2] Email from dana...' to the email."""
    from fallback_pilot.brief.generate import _clean_draft
    out = _clean_draft(
        "Subject: Update\n\nWe will send the pack.\n\nBest regards,\nSam\n"
        "[2] Email from dana.kowalski@northwindtraders.com (part 4)"
    )
    assert "[2]" not in out
    assert "send the pack" in out


def test_gather_gives_every_file_a_slot_before_any_gets_two():
    """Duplicate chunks from one file pushed the real deadline out entirely."""
    from collections import Counter
    from fallback_pilot.brief import gather
    chunks, _ = ingest_paths([str(DEMO)])
    r = HybridRetriever(chunks, embedder=None)
    r.prepare()
    hits = gather(r, "Northwind renewal - what do I need to know before the call")
    counts = Counter(h.chunk.source for h in hits)
    assert len(counts) == 7, "every demo file must contribute"
    assert max(counts.values()) <= 2


def test_draft_has_no_source_markers_anywhere():
    """Observed: qwen2.5-7b ended its email with 'Thank you. [4]'."""
    from fallback_pilot.brief.generate import _clean_draft
    out = _clean_draft("Subject: Update\n\nWe will send it by Friday [4]. Thank you. [2,3]")
    assert "[" not in out
    assert "by Friday" in out


def test_streaming_assembles_the_same_text():
    class Streamer(FakeModel):
        def stream(self, messages, *, max_tokens, temperature):
            self.calls.append(messages)
            for piece in self.reply.split(" "):
                yield piece + " "

    seen = []
    brief = generate("renewal", _hits(k=3), Streamer(GOOD), AV,
                     with_draft=False, on_token=seen.append)
    assert seen, "tokens must reach the caller as they arrive"
    assert "SOC 2" in brief.sections["Open actions"]


def test_backend_without_streaming_still_works():
    brief = generate("renewal", _hits(k=3), FakeModel(GOOD), AV,
                     with_draft=False, on_token=lambda p: None)
    assert brief.sections["Situation"]


def test_every_file_reaches_the_brief_even_when_facets_overlap():
    """Observed: with embeddings on, the pool collapsed to 5 of 7 files and
    the file holding the real deadline vanished."""
    from collections import Counter
    from fallback_pilot.brief import gather
    chunks, _ = ingest_paths([str(DEMO)])
    r = HybridRetriever(chunks, embedder=None)
    r.prepare()
    hits = gather(r, "Northwind renewal - what do I need to know before the call")
    counts = Counter(h.chunk.source for h in hits)
    assert len(counts) == 7, f"only {len(counts)} of 7 files contributed"


def test_coverage_holds_when_retrieval_returns_almost_nothing():
    """The top-up pass must work even if the facets find one file."""
    from fallback_pilot.brief import gather

    chunks, _ = ingest_paths([str(DEMO)])
    r = HybridRetriever(chunks, embedder=None)
    r.prepare()
    real_search = r.search
    r.search = lambda q, top_k=5, per_source=None: real_search(q, 1, 1)[:1]
    hits = gather(r, "renewal")
    assert len({h.chunk.source for h in hits}) >= 5


def test_blockers_prompt_forbids_repeating_actions():
    from fallback_pilot.brief import prompts
    assert "Do NOT repeat the Open actions" in prompts.BRIEF_INSTRUCTION


def test_render_skips_the_panel_when_already_streamed():
    from io import StringIO
    from rich.console import Console
    from fallback_pilot.brief import print_brief
    brief = generate("renewal", _hits(k=3), FakeModel(GOOD), AV, with_draft=False)
    buf = StringIO()
    print_brief(brief, Console(file=buf, width=100), already_shown=True)
    out = buf.getvalue()
    assert "Continuity Brief -" not in out, "body must not print twice"
    assert "Sources" in out
