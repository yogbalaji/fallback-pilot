# Responsible AI, security and privacy

How Fallback Pilot addresses Microsoft's Responsible AI principles, and the
data-handling choices behind it.

---

## The shape of the system

An agent that starts work on its own, reads a person's work files, and drafts
replies on their behalf. Each of those carries risk. What follows is what the
system actually does about each one - mechanisms in the code, not intentions.

---

## Reliability and safety

**Grounding is enforced, not assumed.** Sources are numbered before generation
and every citation the model emits is checked against the list it was given. A
citation to a source that does not exist is reported as unverified rather than
printed as fact.

**Known failure modes are detected.** During development a 2B model reproduced
the prompt's own example as though it were the user's data. The prompt now
carries a placeholder skeleton containing no copyable facts, and the app
detects template leakage and marks the brief unusable if it occurs. A separate
check reports when a model returns no citations at all.

**Degradation is visible, never silent.** Four capability tiers, each labelled
in the interface. At the lowest tier no language model is used and the brief is
extracted verbatim from the user's files - stated plainly in the output.

**Quality is measured, not asserted.** `scripts/eval_retrieval.py` scores
retrieval against known answers. `scripts/compare_models.py` scores models on
identical sources. Both are in the repository and reproducible.

---

## Human oversight and accountability

**The agent cannot send anything.** It drafts replies; it never transmits. Every
outgoing message enters an approval queue and stays there until a person
approves or discards it. There is no configuration option to change this - the
capability does not exist in the code.

**Every autonomous action is logged with its reasoning.** `agent_activity.jsonl`
records what triggered each action, what the agent decided, why it decided it,
which tier it ran at, and what it produced. Readable in any text editor.

**A person can intervene at any time.** Pause and resume from the interface or
the command line. Clear the agent's memory to force work to be redone. Discard
anything it prepared. All overrides are themselves logged.

**Approvals are attributed.** Each decision records who made it and when.

---

## Privacy and security

**Nothing leaves the device.** Inference runs locally through Foundry Local.
There is no telemetry, no analytics, and no outbound call carrying user content
at any tier. The only network operation is a TCP connection to a fixed IP used
to test whether a route exists - it transmits no data and can be disabled.

**The interface is bound to 127.0.0.1.** It is not reachable from the network.
A test fails if that binding is ever changed.

**No content is loaded from the internet.** The interface has no CDN reference,
no web font and no external script. A test fails if one is added. This is a
privacy property as much as an offline one: no third party learns that the tool
was used or when.

**Extracted content is inspectable.** Everything read from a user's files is
stored as plain JSONL. Anyone can open it and see exactly what was extracted.

**The user chooses the scope.** Only folders listed in `config.yaml` are read.
Nothing is discovered or indexed without being named.

**Data stays where the user put it.** Briefs are written beside the index on the
local disk. Nothing is uploaded, synced or shared.

---

## Fairness and inclusiveness

**It runs on hardware people already own.** Verified on a standard corporate
laptop with an 11 TOPS NPU - well below the 40 TOPS Copilot+ threshold. A tool
that requires new hardware is not available to everyone who needs it.

**It degrades rather than excluding.** On a machine that cannot run a language
model at all, the extractive tier still produces a cited brief using only the
Python standard library.

**No paid service is required.** No subscription, no cloud AI, no per-seat cost.

---

## Transparency

**Every claim is traceable.** Citations map to a file and a section the user can
open. The interface shows which sources were used and which were not.

**The system says what it is doing and at which tier.** Visible in the
interface, in the command line, and in the footer of every saved brief.

**Limitations are documented** in the README rather than left to be discovered:
generation latency, small-model behaviour, the scope of the retrieval
benchmark, and the single hardware configuration it was tested on.

---

## Known limitations

- Small language models can produce weak or incorrect summaries. The system
  detects several failure modes but cannot detect all of them. **Briefs are a
  starting point for a person, not a decision.**
- The "who is waiting on a reply" detection is a weighted keyword heuristic. It
  is deliberately conservative and declines to prepare a draft when unsure, but
  it can be wrong.
- Retrieval quality is measured on one scenario of seven files.
- Tested on one hardware configuration.

---

## Data handling summary

| Question | Answer |
|---|---|
| What is read? | Only folders named in `config.yaml` |
| Where does it go? | Nowhere. Processing is local |
| What is stored? | Extracted text and briefs, on local disk |
| Is anything transmitted? | No user content, at any tier |
| Can it send email? | No. It drafts; a person sends |
| Is there telemetry? | None |
| Who can reach the interface? | localhost only |
| Can the user audit it? | Yes - plain-text index, logs and briefs |
