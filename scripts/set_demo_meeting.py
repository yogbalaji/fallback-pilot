"""Put a meeting on the local calendar, N minutes from now.

The agent triggers on meetings that are actually approaching, so a calendar
file with a fixed date stops working the day after it is written. Run this
before a demo to place the meeting at a time that will fire:

    python scripts/set_demo_meeting.py            # 45 minutes from now
    python scripts/set_demo_meeting.py --minutes 5
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "demo_data" / "calendar.ics"

TEMPLATE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Fallback Pilot//Demo Calendar//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
UID:northwind-renewal-call@fallback-pilot.local
DTSTAMP:{stamp}
DTSTART:{start}
DTEND:{end}
SUMMARY:Northwind renewal call
DESCRIPTION:Renewal discussion. Priya is on leave - security evidence and
 commercial terms both outstanding.
ATTENDEE;CN=Dana Kowalski:mailto:dana.kowalski@northwindtraders.com
ATTENDEE;CN=Ravi Chandra:mailto:ravi.chandra@northwindtraders.com
ATTENDEE;CN=Marcus Feld:mailto:marcus.feld@northwindtraders.com
END:VEVENT
BEGIN:VEVENT
UID:internal-pipeline-review@fallback-pilot.local
DTSTAMP:{stamp}
DTSTART:{later_start}
DTEND:{later_end}
SUMMARY:Weekly pipeline review
DESCRIPTION:Internal. Lower priority than customer calls.
END:VEVENT
END:VCALENDAR
"""


def ics(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=45,
                    help="how far from now the customer call should be")
    args = ap.parse_args()

    now = datetime.now()
    start = now + timedelta(minutes=args.minutes)
    # A second, less urgent meeting, so the agent has to choose between them.
    later = now + timedelta(minutes=args.minutes + 90)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        TEMPLATE.format(
            stamp=ics(now),
            start=ics(start),
            end=ics(start + timedelta(minutes=30)),
            later_start=ics(later),
            later_end=ics(later + timedelta(minutes=30)),
        ),
        encoding="utf-8",
    )
    print(f"Northwind renewal call  -> {start:%H:%M} ({args.minutes} min from now)")
    print(f"Weekly pipeline review  -> {later:%H:%M}")
    print(f"Written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
