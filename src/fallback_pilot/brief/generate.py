"""Turn retrieved local context into a Continuity Brief.

The whole point of the project arrives here: everything upstream was gathering
evidence, and this is where it becomes something a person can act on before
walking into a meeting.

Grounding is enforced structurally rather than hoped for. Sources are numbered,
the model is told to cite them, and every citation it emits is checked against
the list it was actually given. A number it invented gets reported, not printed
as if it were real.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..availability import Availability
from ..llm.base import Backend, Message
from . import prompts

HEADINGS = ["Situation", "Open actions", "Blockers and risks", "Recommended next step"]


@dataclass
class Brief:
    """A brief plus everything needed to judge whether to trust it."""
    topic: str
    sections: dict[str, str]
    draft: str
    sources: list[str]
    cited: set[int] = field(default_factory=set)
    invented: set[int] = field(default_factory=set)
    tier: int = 0
    tier_label: str = ""
    backend: str = ""
    model: str = ""
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return not self.invented and not self.template_leak

    @property
    def template_leak(self) -> bool:
        return any("reproduced the prompt template" in n for n in self.notes)

    @property
    def coverage(self) -> float:
        """What fraction of the retrieved sources the brief actually used."""
        return len(self.cited) / len(self.sources) if self.sources else 0.0

    @property
    def body(self) -> str:
        out = []
        for h in HEADINGS:
            if self.sections.get(h):
                out.append(f"## {h}\n{self.sections[h].strip()}")
        return "\n\n".join(out)


def _split_sections(text: str) -> dict[str, str]:
    """Parse the model's markdown back into sections.

    Small models drift on heading wording ('Open Actions', '**Situation**',
    '3. Blockers'), so match loosely on the distinctive word rather than
    demanding an exact string.
    """
    sections: dict[str, str] = {h: "" for h in HEADINGS}
    keys = {
        "situation": "Situation",
        "open action": "Open actions",
        "action": "Open actions",
        "blocker": "Blockers and risks",
        "risk": "Blockers and risks",
        "next step": "Recommended next step",
        "recommend": "Recommended next step",
    }

    current: str | None = None
    buffer: list[str] = []

    def flush():
        if current and buffer:
            existing = sections.get(current, "")
            joined = "\n".join(buffer).strip()
            sections[current] = f"{existing}\n{joined}".strip() if existing else joined

    for line in text.splitlines():
        stripped = line.strip()
        is_heading = bool(re.match(r"^(#{1,4}\s+|\*\*.+\*\*\s*$|\d+[.)]\s+\w)", stripped))
        if is_heading:
            plain = re.sub(r"^#{1,4}\s*|\*\*|^\d+[.)]\s*|:$", "", stripped).strip().lower()
            matched = next((v for k, v in keys.items() if k in plain), None)
            if matched:
                flush()
                current, buffer = matched, []
                continue
        if current:
            buffer.append(line)
    flush()

    # If the model ignored headings entirely, keep the text rather than
    # showing the user an empty brief.
    if not any(sections.values()):
        sections["Situation"] = text.strip()
    return sections


COMMENTARY = re.compile(
    r"^\s*(-{3,}|\*{3,}|note:|this (email|draft|brief)\b|i hope|let me know if)",
    re.I,
)


def _leaked_example(text: str) -> bool:
    """Did the model reproduce the prompt skeleton instead of the sources?"""
    low = text.lower()
    return any(c.lower() in low for c in prompts.EXAMPLE_CANARIES)


def _clean_draft(text: str) -> str:
    """Drop anything the model appended after the email itself."""
    lines = text.strip().splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if COMMENTARY.match(line) and out:
            break
        # A bare "[2] Email from ..." line is a citation, not part of the email.
        if re.match(r"^\[\d+[\d,\s]*\]", stripped):
            continue
        out.append(line)
    # Strip inline markers too: an email that says "by Friday [4]" reads as a
    # machine artefact to whoever receives it.
    cleaned = re.sub(r"\s*\[\d+[\d,\s]*\]", "", "\n".join(out))
    return cleaned.strip()


def _citations(text: str) -> set[int]:
    found: set[int] = set()
    for match in re.findall(r"\[([0-9,\s]+)\]", text):
        for part in match.split(","):
            part = part.strip()
            if part.isdigit():
                found.add(int(part))
    return found


def generate(
    topic: str,
    hits: list,
    backend: Backend,
    availability: Availability,
    *,
    max_tokens: int = 900,
    temperature: float = 0.2,
    intent: str | None = None,
    with_draft: bool = True,
    on_token=None,
    recipient: str = "",
) -> Brief:
    started = time.perf_counter()
    source_block = prompts.format_sources(hits)
    citations = [h.chunk.citation for h in hits]
    notes: list[str] = []

    ask = [
        Message("system", prompts.SYSTEM),
        Message("user", prompts.BRIEF_INSTRUCTION.format(
            sources=source_block, example=prompts.EXAMPLE, topic=topic)),
    ]

    if on_token and hasattr(backend, "stream"):
        pieces = []
        for piece in backend.stream(ask, max_tokens=max_tokens, temperature=temperature):
            pieces.append(piece)
            on_token(piece)
        body = "".join(pieces)
    else:
        body = backend.complete(ask, max_tokens=max_tokens, temperature=temperature)

    # An uncited brief is unusable, so spend one more call trying to fix it
    # rather than presenting claims the user cannot check.
    if not _citations(body):
        try:
            body = backend.complete(
                ask + [Message("assistant", body),
                       Message("user", prompts.STRICTER_RETRY)],
                max_tokens=max_tokens,
                temperature=max(temperature, 0.1),
            )
            notes.append("First attempt had no citations; asked the model again.")
        except Exception:
            pass

    sections = _split_sections(body)

    draft = ""
    if with_draft:
        try:
            draft_ask = [
                Message("system", prompts.SYSTEM),
                Message("user", prompts.DRAFT_INSTRUCTION.format(
                    sources=source_block,
                    situation=sections.get("Situation", "").strip() or topic,
                    intent=intent or prompts.DEFAULT_INTENT,
                )),
            ]
            if on_token and hasattr(backend, "stream"):
                on_token("\n\n## Draft message\n\n")
                pieces = []
                for piece in backend.stream(draft_ask, max_tokens=350,
                                            temperature=temperature):
                    pieces.append(piece)
                    on_token(piece)
                draft = _clean_draft("".join(pieces))
            else:
                draft = _clean_draft(backend.complete(
                    draft_ask, max_tokens=350, temperature=temperature))
        except Exception as exc:
            notes.append(f"Draft message failed: {type(exc).__name__} - {exc}")

        # A small model that has just written a long brief can return nothing
        # at all for the second call - its context is full. Retry once with a
        # compact prompt carrying only the facts the reply actually needs.
        if not draft:
            try:
                compact = prompts.COMPACT_DRAFT.format(
                    recipient=recipient or "the person waiting on a reply",
                    topic=topic,
                    situation=sections.get("Situation", "").strip() or topic,
                )
                draft = _clean_draft(backend.complete(
                    [Message("system", prompts.SYSTEM), Message("user", compact)],
                    max_tokens=300, temperature=temperature,
                ))
                if draft:
                    notes.append("Draft written on a second, shorter attempt.")
            except Exception as exc:
                notes.append(f"Draft retry failed: {type(exc).__name__} - {exc}")

        if not draft and not any("failed" in n for n in notes):
            notes.append("Model returned an empty draft twice.")

    cited = _citations(body) | _citations(draft)
    valid = {n for n in cited if 1 <= n <= len(hits)}
    invented = cited - valid
    if invented:
        notes.append(
            f"Model cited source(s) {sorted(invented)} that were not provided - "
            "treat those claims as unverified."
        )
    if not cited:
        notes.append("Model produced no citations - claims are not traceable.")
    if _leaked_example(body):
        notes.append(
            "Model reproduced the prompt template instead of reading your files. "
            "Treat this brief as unusable and try a larger model."
        )

    return Brief(
        topic=topic,
        sections=sections,
        draft=draft.strip(),
        sources=citations,
        cited=valid,
        invented=invented,
        tier=int(availability.tier),
        tier_label=availability.label,
        backend=backend.name,
        model=getattr(backend, "model", ""),
        seconds=time.perf_counter() - started,
        notes=notes,
    )
