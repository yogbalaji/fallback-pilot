# Submission notes

Everything the hackathon form asks for, plus the results that back it up.
Fields marked **[changed]** differ from the original baseline document and the
reason is given - do not paste the old wording.

---

## Form fields

| Field | Entry |
|---|---|
| **Title** | Fallback Pilot: On-Device Work Continuity for Office |
| **Tagline** | Work continues when your best player, network, or cloud AI is unavailable. |
| **Executive Challenge** | Hack for Zero-Cost Productivity |
| **Writing code** | Yes |
| **Code repository** | *(paste your repo URL)* |

**Problem statement** (156 characters, limit 200):

> Work stalls when experts, network, or cloud AI are unavailable. Fallback Pilot
> uses local Office context and on-device models to keep work moving privately.

**Hacking On:** On-device AI; small language models; NPU inference; Office
productivity; local AI; offline productivity; privacy; zero-cost productivity;
Microsoft 365; context-aware AI; retrieval.

**Who is this for:** Business users and information workers - especially
customer-facing teams, project managers, consultants, and anyone who needs
rapid meeting preparation or has to pick up work after a handover.

**Potential product fit:** Microsoft 365 Copilot and Office applications on
Windows. Outlook, Teams and Word are the natural surfaces. Runs today on
Foundry Local, so it needs no Copilot+ hardware.

**Brief description:**

> An on-device Office productivity tool. When the colleague who owns a piece of
> work is unavailable, the network is down, or paid cloud AI is off the table,
> Fallback Pilot reads permitted local work files and produces a cited
> continuity brief - situation, open actions, blockers, recommended next step,
> and a draft reply. Four capability tiers degrade visibly rather than failing,
> down to a tier that needs no language model at all.

---

## What to lead with

Most on-device entries will demo a local model answering a question. Three
things here are harder to copy, and all three are measured rather than claimed.

**1. It degrades instead of failing.** Four tiers, and the bottom one produces a
usable brief with no language model whatsoever. Most projects have a happy path
and an error message.

**2. Claims are verified, not trusted.** Sources are numbered before generation
and every citation is checked afterwards. A model citing a source it was never
given is reported as unverified. During development a model reproduced the
prompt's own example as though it were the user's data - the app now detects
that and marks the brief unusable.

**3. It runs on hardware people already own.** Not a Copilot+ PC.

---

## Measured results

Hardware: Intel Core Ultra 7 165H, 11 TOPS NPU, Intel Arc graphics, 31.6 GB
RAM, Windows 11. A standard corporate laptop, well below the 40 TOPS Copilot+
threshold.

**The headline number**

| | Tier | Time | Brief |
|---|---|---|---|
| Wi-Fi on | 1 - local model, cloud AI withheld | 81.0s | identical |
| Wi-Fi off | 2 - offline, local model | 80.5s | identical |

Same command, same output, nothing degraded.

**Retrieval quality** (`scripts/eval_retrieval.py`)

| Mode | Lexical | Semantic |
|---|---|---|
| Keyword only, no model at all | 7/7 | n/a - skipped by design |
| Hybrid, with on-device embeddings | 7/7 | 2/2 |

The semantic cases share no vocabulary with their source documents, so keyword
search cannot reach them. They are scored only when embeddings are loaded
rather than being quietly dropped.

**Model comparison** (`scripts/compare_models.py`)

| Model | Size | Key facts | Citations | Verdict |
|---|---|---|---|---|
| phi-4-mini | 2.2 GB, NPU | 4/5 | ok | usable |
| qwen2.5-7b | 4.2 GB, NPU | 1/5 | ok | weak |
| qwen2.5-0.5b | 331 MB | 1/5 | none | fabricated |

Bigger is not automatically better: the 7B model produced a worse brief than
the 2.2 GB one on this task. Worth saying out loud - it is a genuinely
counter-intuitive result and it is reproducible from the repo.

---

## [changed] Corrections to the baseline document

**NPU claim - now verified, and stronger than expected.** Foundry Local's
documentation lists Arrow Lake (Core Ultra Series 2) as the minimum for its
Intel NPU execution provider. This machine is Meteor Lake, Series 1. It loads
`phi-4-mini-instruct-openvino-npu` onto the NPU anyway, confirmed by the NPU
graph in Task Manager moving during generation. Claim NPU inference - it is
real - but describe the hardware accurately as a standard laptop, not a
Copilot+ PC.

**Phi Silica is not used, deliberately.** It requires either a Copilot+ PC or an
NVIDIA RTX 30-series / AMD RX 9060-class GPU, and Microsoft is replacing it with
Aion Instruct in November 2026. A portable local runtime reaches far more
machines and does not expire. If asked why not Phi Silica, that is the answer -
it is a reasoned choice, not an omission.

**Say "zero-cost" precisely.** No paid cloud AI, no subscription, no new
hardware. That is the claim, and it holds.

---

## Questions you should expect

**"Eighty seconds is slow."**
> It is. That is a 2.2 GB model on an 11 TOPS NPU in a laptop, and the output
> streams so the wait is visible rather than blank. The alternative on this
> hardware is a cloud round-trip, which is the thing we are refusing to
> require. On a Copilot+ machine or a discrete GPU it is considerably faster.

**"Why not Phi Silica?"**
> It needs a Copilot+ PC or an RTX 30-series class GPU, and Microsoft replaces
> it with Aion Instruct in November 2026. A portable runtime reaches more
> machines and does not expire.

**"Why no Outlook integration?"**
> Reading from a cloud mailbox would make the product depend on the exact thing
> it exists to survive without. It reads local files, including exported mail.
> A local Outlook cache reader is the natural next step.

**"How do I know it isn't uploading my documents?"**
> Open `index/chunks.jsonl`. That is everything the app extracted, in plain
> text, on your disk. Then run the whole demo with the network off.

**"Did you measure any of this, or does it just look right?"**
> `scripts/eval_retrieval.py` scores retrieval against known answers.
> `scripts/compare_models.py` scores three models on the same sources. Both are
> in the repo and both are reproducible. The results are in `docs/`.

---

## Repo checklist

- [ ] `git init`, commit, push
- [ ] Repo URL pasted into the form
- [ ] `python scripts/capture_evidence.py` run, `docs/` committed
- [ ] `docs/model_comparison.md` committed
- [ ] README renders correctly on the repo page
- [ ] Clone into a clean folder and run the quick start end to end
- [ ] Demo video recorded and linked
