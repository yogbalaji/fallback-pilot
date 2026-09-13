"""Tier 3 brief: no language model at all.

When nothing can generate prose, the retrieved chunks are still the right
chunks. Presenting them grouped and attributed is far more useful than an
error message, and it keeps the promise the product name makes.
"""
from __future__ import annotations

import re

from ..availability import Availability
from .generate import Brief

ACTION_HINTS = ("owner", "due", "not started", "in progress", "action", "todo", "open since")
BLOCKER_HINTS = ("block", "risk", "requires", "will not", "cannot", "must", "before",
                 "outstanding", "deadline", "escalat", "below floor")


HEADER_LINE = re.compile(r"^(from|to|date|subject|email|columns)\s*:", re.I)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [
        p.strip() for p in parts
        if len(p.strip()) > 30 and not HEADER_LINE.match(p.strip())
    ]


def generate_extractive(topic: str, hits: list, availability: Availability) -> Brief:
    actions: list[str] = []
    blockers: list[str] = []
    situation: list[str] = []

    for i, h in enumerate(hits, start=1):
        for sentence in _sentences(h.chunk.text):
            low = sentence.lower()
            line = f"{sentence} [{i}]"
            if any(k in low for k in ACTION_HINTS) and len(actions) < 6:
                actions.append(f"- {line}")
            elif any(k in low for k in BLOCKER_HINTS) and len(blockers) < 6:
                blockers.append(f"- {line}")
            elif len(situation) < 3:
                situation.append(line)

    sections = {
        "Situation": " ".join(situation) or "See the extracts below.",
        "Open actions": "\n".join(actions) or "- None identified in the available files.",
        "Blockers and risks": "\n".join(blockers) or "- None identified in the available files.",
        "Recommended next step": (
            "No model was available, so this brief is extracted verbatim from your "
            "files rather than written. Start with the first blocker above - it "
            "carries the nearest deadline."
        ),
    }

    return Brief(
        topic=topic,
        sections=sections,
        draft="",
        sources=[h.chunk.citation for h in hits],
        cited=set(range(1, len(hits) + 1)),
        tier=int(availability.tier),
        tier_label=availability.label,
        backend="extractive",
        seconds=0.0,
        notes=["No language model available - every line above is quoted "
               "directly from your files, not generated."],
    )
