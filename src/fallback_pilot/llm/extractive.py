"""Tier 3: produce something useful with no language model at all.

Pure standard library on purpose. If the NPU is busy, the model failed to load,
or the machine is on its last 5% of battery, Fallback Pilot still returns a
brief instead of an error. That is the whole thesis of the project.
"""
from __future__ import annotations

import re
from collections import Counter

from .base import Backend, Message

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "was", "were",
    "are", "our", "you", "your", "will", "would", "should", "could", "they", "them",
    "but", "not", "all", "any", "can", "his", "her", "its", "into", "than", "then",
    "there", "their", "been", "also", "about", "which", "when", "what", "who",
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in parts if len(s.strip()) > 25]


class ExtractiveBackend(Backend):
    name = "extractive"

    def __init__(self, max_sentences: int = 6):
        self.max_sentences = max_sentences

    def available(self) -> bool:
        return True

    def complete(self, messages: list[Message], *, max_tokens: int, temperature: float) -> str:
        corpus = "\n".join(m.content for m in messages if m.role != "system")
        sents = _sentences(corpus)
        if not sents:
            return "No local context was available to summarize."

        words = [w for w in re.findall(r"[a-z']{3,}", corpus.lower()) if w not in _STOP]
        freq = Counter(words)

        def score(s: str) -> float:
            toks = [w for w in re.findall(r"[a-z']{3,}", s.lower()) if w not in _STOP]
            return sum(freq[w] for w in toks) / (len(toks) ** 0.5 or 1)

        ranked = sorted(range(len(sents)), key=lambda i: score(sents[i]), reverse=True)
        chosen = sorted(ranked[: self.max_sentences])
        bullets = "\n".join(f"- {sents[i]}" for i in chosen)
        return (
            "[Degraded mode - extracted from your local files, no model used]\n\n" + bullets
        )
