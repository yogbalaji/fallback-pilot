# Fallback Pilot

**On-Device Work Continuity for Office**
*Work continues when your best player, network, or cloud AI is unavailable.*

Microsoft Global Hackathon 2026 — Executive Challenge: **Hack for Zero-Cost Productivity**

---

## What this is

**An agent.** It is not prompted - it watches your local calendar, your work
folders and the machine's own capability, and starts work when any of them
change. By the time you look, the brief is usually already there.

It drafts replies but never sends them: outgoing messages wait in an approval
queue, and every autonomous action is logged with its reasoning. See
[RESPONSIBLE-AI.md](RESPONSIBLE-AI.md).


An information worker has to prepare for an important customer meeting. The
expert who owns the account is unavailable, the connection is unreliable, and
paid cloud AI is off the table. Fallback Pilot reads permitted **local** Office
context and produces a **Continuity Brief** — situation, open actions, blockers
and a draft message — entirely on the device.

## The fallback ladder

The core idea. The app always knows what it can count on, and degrades visibly
instead of failing:

| Tier | Condition | Behaviour |
|------|-----------|-----------|
| 0 | Network + sanctioned cloud AI | Cloud assisted |
| 1 | Network up, cloud AI withheld | Local model + local index |
| 2 | No network | Identical output, fully offline |
| 3 | No model available | Extractive brief, no LLM at all |

Tier 3 is not an error path. It is a working answer produced with the standard
library alone.

## Quick start

```powershell
# 0. Install the local runtime (once)
winget install Microsoft.FoundryLocal

# 1. Set up the project
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
#              ^ the trailing dot matters - it means "this folder"
#
# Or skip the install entirely and use  python run.py <command>  instead.

# 2. What can this machine do?
python scripts/check_device.py

# 3. Start the local server on a PINNED port and load a model.
#    Foundry Local picks a random port by default; pinning makes
#    endpoint discovery deterministic.
foundry server start --port 39839 --idle-timeout 0
foundry model load phi-4-mini

# 4. Confirm the app sees it - expect "Active tier 1"
fallback-pilot doctor        # or: python run.py doctor

# 5. Read the demo scenario into the local index
fallback-pilot ingest
fallback-pilot sources

# 6. Search your local context
fallback-pilot search "what is blocking the renewal"

# 7. Optional: add semantic search (finds meaning, not just words)
foundry model load qwen3-embedding-0.6b
fallback-pilot search "why is the customer unhappy" --rebuild

# 8. Build a continuity brief
fallback-pilot brief "Northwind renewal" --out brief.md

# 9. Or open the interface - this is the demo
fallback-pilot ui
```

Then turn off your Wi-Fi and run step 6 again. The output should not change.

## Reading your own files

`config.yaml` controls what gets read:

```yaml
context:
  sources:
    - demo_data
    - C:\Users\you\Documents\SomeAccount
```

Supported: `.docx` `.pptx` `.xlsx` `.pdf` `.txt` `.md` `.eml`

Word, PowerPoint and Excel are parsed with the **standard library only** — no
third-party parsers, nothing that reaches the network. PDF uses `pypdf` and
skips cleanly if it is not installed.

Extracted text lands in `index/chunks.jsonl` as plain text. Open it. For a tool
whose pitch is privacy, being able to see exactly what was read matters more
than shaving milliseconds off load time.

## The demo scenario

`demo_data/` contains a fictional renewal at risk — Northwind Traders, whose
solution architect went on unplanned leave three weeks before a hard deadline.
Seven files across five formats, containing a real blocker, a customer
ultimatum, a pricing floor and a handover email.

Nothing in it is real. Regenerate or edit it with:

```powershell
pip install -e ".[demo]"
python scripts/make_demo_data.py
```

## Layout

```
.vscode/                       ready-made VS Code run + debug config
demo_data/                     the Northwind renewal scenario
scripts/check_device.py        hardware + runtime detection
scripts/make_demo_data.py      regenerates the demo scenario
src/fallback_pilot/
  config.py                    config.yaml loading with defaults
  availability.py              the fallback ladder
  ingest/readers.py            Office formats -> text blocks (stdlib only)
  ingest/chunker.py            blocks -> retrieval chunks with citations
  ingest/store.py              plain JSONL persistence
  retrieve/bm25.py             keyword ranking, stdlib only - always works
  retrieve/embed.py            optional on-device embeddings, cached
  retrieve/hybrid.py           rank fusion across both
  llm/base.py                  Backend interface - one contract, many engines
  llm/foundry.py               Foundry Local over its OpenAI-compatible endpoint
  llm/extractive.py            Tier 3, pure stdlib, always available
  brief/prompts.py             templates, written for small models
  brief/generate.py            the brief chain + citation validation
  brief/extractive.py          tier 3 brief - quoted, not generated
  brief/render.py              terminal + markdown output
  web/server.py                local interface, stdlib only
  web/app.html                 single page, everything inline
  agent/signals.py             calendar, file and capability triggers
  agent/runner.py              observe -> decide -> act, with reasoning
  agent/journal.py             append-only log of autonomous actions
  agent/approvals.py           outgoing messages, waiting for a person
  cli.py                       watch / activity / approvals / brief / ui / ...
tests/                         run: pytest
scripts/eval_retrieval.py      retrieval quality gate - run after any change
scripts/capture_evidence.py    writes proof of all of the above into docs/
scripts/compare_models.py      run one brief across several models
scripts/set_demo_meeting.py    place a meeting N minutes from now
DEMO.md                        runbook for the two-minute recording
RESPONSIBLE-AI.md              RAI, security and privacy
SUBMISSION.md                  form fields and measured results
```

## The agent

```powershell
python scripts/set_demo_meeting.py --minutes 30   # give it a reason to act
fallback-pilot watch                              # it takes it from here
```

Three kinds of signal start it, with no human prompt:

| Trigger | Example |
|---|---|
| **Calendar** | a meeting enters the lead window |
| **Files** | a document or email appears or changes on disk |
| **Capability** | the tier changes - losing the network is the urgent one |

It then decides from observed state rather than running a fixed sequence:

- a meeting 10 minutes away outranks one 3 hours away
- a brief already written is not rewritten unless its sources changed
- losing connectivity promotes everything, because the window is closing
- at tier 3 it still produces a brief, extractively, and says so
- it remembers across restarts, so it does not redo work

### Oversight

```powershell
fallback-pilot activity              # what it did, and why
fallback-pilot approvals             # what is waiting on you
fallback-pilot approvals --approve <id>
```

**The agent cannot send anything.** It drafts; a person sends. That is not a
setting - there is no send capability in the code. Replies wait in a queue, and
the decision is logged alongside everything else.

The activity log records the trigger, the decision, the reasoning and the tier
for every action, in plain JSONL at `index/agent_activity.jsonl`.

Pause it, resume it, or clear its memory to force work to be redone - from the
interface or the command line. Overrides are logged too.

## The interface

```powershell
fallback-pilot ui
```

Opens `http://127.0.0.1:8756`. A live tier badge, the brief streaming in,
citations linked to the files they came from, and retrieval and generation
timings.

Built on the standard library alone - no Flask, no build step, no
`node_modules`, and **nothing loaded from the internet at runtime**. That last
one is not a preference: the demo switches the network off, so a page that
fetched a font or a script from a CDN would break at precisely the moment the
product is meant to prove itself. Bound to `127.0.0.1` only.

Leave it open and toggle your Wi-Fi. The badge moves from tier 1 to tier 2
within two seconds, and the next brief is identical.

## The Continuity Brief

```powershell
fallback-pilot brief "Northwind renewal" --out brief.md
```

Retrieves the most relevant local context, then writes four sections -
**Situation**, **Open actions**, **Blockers and risks**, **Recommended next
step** - plus a draft message, with a bracketed citation after each claim.

### Two failures that shaped this design

**A 0.5B model confabulates.** `qwen2.5-0.5b` produced a fluent brief with
1 of 5 key facts and zero citations, inventing positions for three named people
who had proposed nothing.

**A worked example gets copied.** The first fix was a realistic sample brief in
the prompt. `phi-4-mini` reproduced its contents verbatim - a "Sam Doe", a
"30 June" deadline and a "20% discount" that exist nowhere in the user's files.
Plausible sentences are easier to reproduce than to adapt. The prompt now shows
a placeholder skeleton with no copyable facts, and the app **detects** leakage
if it happens anyway and marks the brief unusable.

Both failures are now regression tests. Neither was imagined - both were
observed on real hardware, and finding them is what the instrumentation is for.

### A 0.5B model is not enough

Measured on the demo scenario, `qwen2.5-0.5b` produced a fluent, well-formatted
brief containing **1 of 5 key facts and zero citations** - and invented
positions for three named people who had proposed nothing. It took 68 seconds
to do it.

That failure shaped the design. Use **2B or larger**; `phi-4-mini` is the
default. The point is not that a small model is bad - it is that the app has to
*detect* this rather than present confabulation as fact, which is what the
citation check and the fact scorer are for.

Three things make it trustworthy rather than plausible:

**Sources are numbered and every citation is checked.** If the model cites a
source it was never given, that is reported as unverified rather than printed
as fact. `brief.grounded` is false and the note says which number was invented.

**A brief asks several questions, not one.** Searching once for the topic left
the walk-away price unretrieved, so the model was free to invent one. The brief
now also asks what is blocking progress, what the hard date is, what the numbers
are, and who owns what - which raised measured key-fact coverage from 4/5 to
**5/5** across 7 files. A fact the model never saw is a fact it will make up.

**It still works at tier 3.** With no model at all, the brief is assembled by
extracting and attributing the retrieved sentences. Less fluent, still useful,
still cited.

### Measured on a Core Ultra 7 165H

| model | key facts | citations | verdict | seconds |
|---|---|---|---|---|
| phi-4-mini (2.2 GB, NPU) | 5/5 | ok | usable | ~77 |
| qwen2.5-7b (4.2 GB, NPU) | 1/5 | ok | weak | ~81 |
| qwen2.5-0.5b (331 MB) | 1/5 | none | fabricated | ~43 |

Bigger is not automatically better: `qwen2.5-7b` is twice the size of
`phi-4-mini` and produced a worse brief on this task. Measure on your own
scenario rather than assuming.

The brief and the draft both **stream** as they are written. The work takes the
same time either way; watching it appear is a demo, watching a blank terminal
for 80 seconds is a stall. Use `--quiet` to disable.

### The result that matters

Same command, same machine, Wi-Fi toggled:

```
Wi-Fi on   tier 1 - Local model (cloud AI withheld)   81.0s
Wi-Fi off  tier 2 - Offline - local model             80.5s
```

Byte-identical brief. Nothing degraded, because nothing was ever depending on
the network.

### Choosing a model

Model size is the biggest single lever on how the brief reads. Measure instead
of guessing:

```powershell
foundry model load phi-4-mini
foundry model load qwen2.5-7b
python scripts/compare_models.py phi-4-mini qwen2.5-7b
```

Runs the same brief, from identical sources, through each model and compares
speed, how many key facts survived, and whether citations held up. Writes the
full briefs to `docs/model_comparison.md` so you can judge the prose yourself.

## Capturing evidence

```powershell
python scripts/capture_evidence.py
```

Runs the hardware check, the readiness check, ingestion, and the retrieval
benchmark twice - once with no model at all, once with embeddings - and writes
each result into `docs/`. Plain text rather than screenshots, so the files live
in the repo, diff in git, and can be read without opening an image.

## Retrieval degrades on the same ladder

Search uses two methods that fail in opposite directions:

| Method | Finds | Needs |
|--------|-------|-------|
| Keyword (BM25) | exact terms - names, dates, "SOC 2", "DPA" | nothing at all |
| Semantic (embeddings) | meaning - "unhappy" matching "I want to be direct" | an embedding model |

Results are combined by **rank fusion** rather than by averaging scores: BM25
scores are unbounded while cosine similarity sits in [-1, 1], so averaging
would let one side dominate for reasons unrelated to relevance.

If no embedding model is loaded, search silently falls back to keywords alone -
the same principle as tier 3. Measure it yourself:

```powershell
python scripts/eval_retrieval.py                  # with whatever is loaded
python scripts/eval_retrieval.py --keyword-only   # the no-model baseline
```

Keyword-only scores 7/7 on the lexical cases. Two cases are tagged `semantic`
and skipped without an embedding model, because their questions share no
vocabulary with the source at all - they exist to show what the embedding
layer buys you.

## What is built

- [x] **0** Repo skeleton, config, hardware detection
- [x] **1** Local model answering with zero network
- [x] **2** Ingest local Office files into clean text chunks
- [x] **3** Hybrid retrieval - keyword always, embeddings when available
- [x] **4** Continuity Brief with validated citations
- [x] **5** Four-tier fallback ladder, verified on real hardware
- [x] **6** Local web interface with live tier detection
- [x] **7** Demo runbook and evidence capture
- [x] **8** Autonomous agent: event triggers, state-driven decisions, oversight

**Deliberately not built:** live Outlook and Teams integration. Fallback Pilot
reads files from disk, which is what makes it work offline. Pulling from a
cloud mailbox would add a dependency on the exact thing the project is about
surviving without. Exported `.eml` files are supported instead.

## Known limitations

Stated plainly, because they are the honest shape of the thing:

- **A brief takes 60-90 seconds** on this hardware. The output streams so the
  wait is visible rather than blank, but it is not instant. A larger NPU or a
  GPU with more headroom would close most of that gap.
- **Small models need careful prompting.** A 0.5B model confabulated badly, and
  a 2B model reproduced the prompt's own example as though it were the user's
  data. Both are now detected and reported rather than prevented - the app's
  position is that it must be able to tell you when it cannot be trusted.
- **Retrieval is tuned on one scenario.** The quality gate in
  `scripts/eval_retrieval.py` scores eight questions against seven files.
  Real-world folders are larger and messier.
- **Tested on one hardware configuration** - Intel Core Ultra 7 165H. The
  hardware detection covers other families but has not been run on them.
- **The demo data is fictional.** Northwind Traders is a Microsoft sample
  company and every person in it is invented.

## A note on hardware

Windows' built-in Phi Silica APIs are **not** used here, deliberately. They
require either a Copilot+ PC (40+ TOPS NPU) or an NVIDIA RTX 30-series / AMD
RX 9060-class GPU, and the model is being replaced by Aion Instruct in
November 2026.

**The NPU is still used.** On a Core Ultra 7 165H - a standard corporate
laptop, 11 TOPS, well below the 40 TOPS Copilot+ bar - Foundry Local loads
`phi-4-mini-instruct-openvino-npu` onto the NPU. Foundry Local's documentation
lists Arrow Lake as the minimum for its Intel NPU provider; the observed
behaviour is more permissive than the documented floor. Confirm it on your own
machine by watching Task Manager > Performance > NPU while a brief generates.

That matters for a zero-cost challenge: this runs on hardware people already
own, not on a machine they would have to buy.

A portable local runtime reaches far more machines and does not expire. That is
also the better story for a zero-cost challenge: this runs on the corporate
laptop you already own, not on hardware you would have to buy.

`scripts/check_device.py` reports your actual NPU generation, whether any local
runtime can address it, and which GPU acceleration path applies.

## Constraint

No paid cloud AI is required for the core experience. `allow_paid_cloud_ai` is
`false` by default, and tiers 1–3 never make an inference call off the device.
