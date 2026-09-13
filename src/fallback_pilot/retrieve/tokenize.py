"""Shared tokenizer.

Kept in one place because the index and the query must tokenize identically -
a mismatch here is silent and produces mysteriously empty results.
"""
from __future__ import annotations

import re

# Words that appear everywhere and carry no retrieval signal. Deliberately
# short: over-pruning hurts more than it helps on a 30-document corpus.
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "have", "has", "had", "having", "of", "in", "on", "at",
    "to", "for", "with", "by", "from", "as", "into", "about", "over", "under",
    "it", "its", "we", "our", "us", "you", "your", "they", "them", "their",
    "he", "she", "his", "her", "i", "me", "my", "will", "would", "should",
    "could", "can", "may", "might", "must", "shall", "not", "no", "so", "up",
    "out", "there", "here", "what", "which", "who", "whom", "when", "where",
    "how", "why", "all", "any", "both", "each", "more", "most", "other", "some",
    "such", "only", "own", "same", "very", "just", "also", "s", "t",
}


def _singular(word: str) -> str:
    """Crude but predictable stemming.

    A real stemmer would over-reach on short domain words ('status' -> 'statu'),
    so this only strips obvious plurals.
    """
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") and not word.endswith(("ses", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    raw = re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", (text or "").lower())
    out: list[str] = []
    for tok in raw:
        if len(tok) < 2:
            continue
        if not keep_stopwords and tok in STOPWORDS:
            continue
        out.append(_singular(tok))
    return out
