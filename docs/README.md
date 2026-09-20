# Evidence

Captured 2026-09-20 17:50 by `python scripts/capture_evidence.py`.

- `01_device.txt` - What this machine can do
- `02_readiness.txt` - Which fallback tier is active
- `03_ingest.txt` - Reading local Office files
- `04_eval_keyword_only.txt` - Retrieval with NO model at all
- `05_eval_hybrid.txt` - Retrieval with on-device embeddings
- `06_brief.txt` - A continuity brief, generated on-device
- `07_agent_cycle.txt` - The agent starting work with no human prompt
- `08_agent_activity.txt` - What the agent did, and why
- `09_approvals.txt` - Actions prepared but NOT taken, awaiting a person
- `ALL.txt` - everything above in one file

## What to look at

`04_eval_keyword_only.txt` and `05_eval_hybrid.txt` are the same
retrieval benchmark run twice - once with no model available at all,
once with on-device embeddings loaded. The difference between them is
what the semantic layer contributes.

`01_device.txt` shows the hardware this ran on. It is a standard
corporate laptop, not a Copilot+ PC.

`07_agent_cycle.txt` through `09_approvals.txt` show the agent starting
work without being prompted, the reasoning behind each decision, and the
approval queue holding an action it prepared but will not take.
