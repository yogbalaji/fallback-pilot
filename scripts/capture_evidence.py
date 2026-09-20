"""Capture proof that this works, into docs/, in one command.

    python scripts/capture_evidence.py

Writes plain text files rather than screenshots on purpose: they live in the
repo, they diff in git when something changes, and a judge can read them
without opening an image. Screenshot them afterwards if you want pictures for
a slide - but the files are the durable evidence.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# (output filename, human label, command)
STEPS = [
    ("01_device.txt", "What this machine can do",
     [sys.executable, "scripts/check_device.py"]),
    ("02_readiness.txt", "Which fallback tier is active",
     [sys.executable, "-m", "fallback_pilot.cli", "doctor"]),
    ("03_ingest.txt", "Reading local Office files",
     [sys.executable, "-m", "fallback_pilot.cli", "ingest"]),
    ("04_eval_keyword_only.txt", "Retrieval with NO model at all",
     [sys.executable, "scripts/eval_retrieval.py", "--keyword-only"]),
    ("05_eval_hybrid.txt", "Retrieval with on-device embeddings",
     [sys.executable, "scripts/eval_retrieval.py"]),
    ("06_brief.txt", "A continuity brief, generated on-device",
     [sys.executable, "-m", "fallback_pilot.cli", "brief",
      "Northwind renewal - what do I need to know before the call"]),
    ("07_agent_cycle.txt", "The agent starting work with no human prompt",
     [sys.executable, "-m", "fallback_pilot.cli", "watch", "--once"]),
    ("08_agent_activity.txt", "What the agent did, and why",
     [sys.executable, "-m", "fallback_pilot.cli", "activity"]),
    ("09_approvals.txt", "Actions prepared but NOT taken, awaiting a person",
     [sys.executable, "-m", "fallback_pilot.cli", "approvals"]),
]


def run(cmd: list[str]) -> tuple[str, int]:
    env_note = "(no output)"
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=900,
            # Decode explicitly. The child writes UTF-8 box-drawing characters
            # and a Windows parent would otherwise decode them with the local
            # codepage and either mangle or fail on them.
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONPATH": str(ROOT / "src"),
                 "PYTHONIOENCODING": "utf-8"},
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        return combined.strip() or env_note, proc.returncode
    except subprocess.TimeoutExpired:
        return "Timed out after 15 minutes.", 1
    except Exception as exc:
        return f"Could not run: {exc}", 1


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary: list[str] = []

    print(f"Capturing evidence to {DOCS}\n")
    for filename, label, cmd in STEPS:
        print(f"  {label} ...", end=" ", flush=True)
        output, code = run(cmd)
        header = (
            f"# {label}\n"
            f"# Fallback Pilot - captured {stamp}\n"
            f"# {platform.system()} {platform.release()} | "
            f"command: {' '.join(cmd[1:])}\n"
            f"{'-' * 70}\n\n"
        )
        (DOCS / filename).write_text(header + output + "\n", encoding="utf-8")
        print("done" if code == 0 else f"done (exit {code})")
        summary.append(f"- `{filename}` - {label}")

    # One combined file, so there is a single thing to paste or attach.
    combined = [f"# Fallback Pilot - evidence captured {stamp}\n"]
    for filename, label, _ in STEPS:
        combined.append(f"\n\n{'=' * 70}\n{label}\n{'=' * 70}\n")
        combined.append((DOCS / filename).read_text(encoding="utf-8"))
    (DOCS / "ALL.txt").write_text("".join(combined), encoding="utf-8")

    (DOCS / "README.md").write_text(
        "# Evidence\n\n"
        f"Captured {stamp} by `python scripts/capture_evidence.py`.\n\n"
        + "\n".join(summary)
        + "\n- `ALL.txt` - everything above in one file\n\n"
        "## What to look at\n\n"
        "`04_eval_keyword_only.txt` and `05_eval_hybrid.txt` are the same\n"
        "retrieval benchmark run twice - once with no model available at all,\n"
        "once with on-device embeddings loaded. The difference between them is\n"
        "what the semantic layer contributes.\n\n"
        "`01_device.txt` shows the hardware this ran on. It is a standard\n"
        "corporate laptop, not a Copilot+ PC.\n\n"
        "`07_agent_cycle.txt` through `09_approvals.txt` show the agent starting\n"
        "work without being prompted, the reasoning behind each decision, and the\n"
        "approval queue holding an action it prepared but will not take.\n",
        encoding="utf-8",
    )

    print(f"\nWrote {len(STEPS) + 2} files to docs/")
    print("Paste docs/ALL.txt if you need to share the whole picture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
