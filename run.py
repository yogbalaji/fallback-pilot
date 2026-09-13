"""Run Fallback Pilot without installing it.

    python run.py doctor
    python run.py ingest
    python run.py brief "Northwind renewal"

`pip install -e .` gives you the shorter `fallback-pilot` command, but this
works straight from a fresh clone with nothing installed but the dependencies.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fallback_pilot.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
