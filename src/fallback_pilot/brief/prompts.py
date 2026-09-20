"""Prompt templates for the Continuity Brief.

Written for SMALL models, and rewritten after watching a 0.5B model produce a
fluent, entirely invented brief. Four things changed as a result, and each one
is here because the failure it prevents was observed, not imagined:

1. A worked example. Small models copy structure far more reliably than they
   follow described structure. This is the single biggest lever.
2. Citations stated as a hard requirement with a visible format, not a polite
   request. The model that ignored 'cite the source number' produced 0 of 6.
3. An explicit ban on the specific failure seen: attributing a proposal or
   opinion to a person the sources never said proposed anything.
4. Tight length limits. Given room to ramble, a small model fills it by
   inventing.

The example is a SKELETON, not a sample brief. An earlier version used a
realistic worked example and phi-4-mini reproduced its contents as though they
were the user's facts - the most instructive failure of the project so far.

Fixed markdown headings rather than JSON throughout: a small model will emit
malformed JSON often enough to break a live demo, but rarely fails to echo a
heading it has just been shown.
"""
from __future__ import annotations

SYSTEM = """You are Fallback Pilot. You summarise ONLY what is in the numbered \
sources you are given.

Absolute rules:
- Every sentence you write must come from a numbered source.
- End every claim with its source number in brackets, like this [2].
- A claim with no bracket is not allowed.
- Never state a person's opinion, proposal or position unless a source says it.
- Never invent numbers, dates, percentages or names. Copy them exactly.
- If the sources do not cover something, write: Not stated in available files.
- Be terse. No preamble, no closing remarks, no explanation of your answer."""


# A worked example with realistic content is dangerous: phi-4-mini copied it
# verbatim - inventing "Sam Doe", "30 June" and a 20% discount that appear
# nowhere in the user's files - because plausible sentences are easier to
# reproduce than to adapt. Placeholders in angle brackets teach the same shape
# while being impossible to mistake for facts, and any that survive into the
# output are trivially detectable.
EXAMPLE = """Required output shape. The angle brackets are placeholders - never \
copy them, and never copy this wording. Replace everything with facts from the \
numbered sources.

## Situation
<where things stand, from the sources> [n]. <the hard deadline, if a source \
gives one> [n].

## Open actions
- <action>, owner <name from a source>, due <date from a source>, <status> [n]
- <action> [n]

## Blockers and risks
- <what is blocking, and who holds it> [n]
- <what happens if it is not resolved> [n]

## Recommended next step
<the single most useful action, and the reason> [n].

Every line ends with a real source number in square brackets."""

# If any of these reach the output, the model reproduced the example instead of
# reading the sources. Checked at generation time.
EXAMPLE_CANARIES = ("<where things stand", "<action>", "<name from a source>",
                    "<the hard deadline", "placeholder")

BRIEF_INSTRUCTION = """{sources}

{example}

Now write the brief for: {topic}

Use those four headings, in that order. Rules:
- Situation: at most 3 sentences.
- Open actions: at most 4 bullets. Give owner and date when a source states them.
- Blockers and risks: at most 4 bullets. Do NOT repeat the Open actions list. A
  blocker explains WHO is holding something up and WHAT happens if it stays
  unresolved - not just that a task is incomplete.
- Recommended next step: 1 or 2 sentences naming one action.
- Every bullet and every sentence ends with a source number in brackets.
- Use only the source numbers listed above.
- Draw on at least FOUR different sources. Emails and notes carry what people
  actually said and what they threatened to do; a spreadsheet does not."""


DRAFT_INSTRUCTION = """{sources}

Situation:
{situation}

Write an email that {intent}.

Format exactly:
Subject: <one line>

<body, under 120 words>

Rules:
- Only facts from the numbered sources above.
- Name one concrete next step, with a date if a source gives one.
- No brackets or source numbers in the email itself.
- Output the email only. No notes, no explanation, nothing after the sign-off."""


# Retry prompt for the draft, used when the first attempt comes back empty.
# Deliberately compact: no source block, no numbered extracts, just the facts
# the reply needs. A small model on an NPU has a limited context window, and a
# long prompt followed by a long brief is the most likely thing to exhaust it.
COMPACT_DRAFT = """Write a short email.

To: {recipient}
About: {topic}

What is true right now:
{situation}

Format exactly:
Subject: <one line>

<body, under 100 words>

State only what is written above. Name one concrete next step with a date if
one is given. No brackets, no source numbers, no commentary. Output the email
only."""


DEFAULT_INTENT = (
    "replies to the customer contact who is waiting on us, acknowledges the "
    "outstanding item they raised, and commits to a specific next step"
)

# Used when a first attempt comes back with no citations at all.
STRICTER_RETRY = """Your previous answer did not cite any sources, which is not \
allowed.

Rewrite it. Every single bullet and sentence must end with a source number in \
brackets, like [1] or [3]. Use only numbers from the list of sources. Change \
nothing else about the content."""


def format_sources(hits) -> str:
    lines = ["Numbered sources:", ""]
    for i, h in enumerate(hits, start=1):
        lines.append(f"[{i}] {h.chunk.citation}")
        lines.append(h.chunk.text.strip())
        lines.append("")
    return "\n".join(lines)
