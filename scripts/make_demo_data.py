"""Generate the demo scenario: a customer renewal whose expert went on leave.

Everything here is fictional. Northwind Traders is Microsoft's standard sample
company, and the people are invented - so the repo can be shared publicly and
demoed without touching real customer data.

The generated files are already included in demo_data/. Re-run this only if you
want to change the scenario:

    pip install python-docx python-pptx openpyxl
    python scripts/make_demo_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "demo_data"


def make_account_plan(path: Path) -> None:
    from docx import Document

    d = Document()
    d.add_heading("Northwind Traders - Account Plan FY26", 0)
    d.add_paragraph("Owner: Priya Raman, Solution Architect")
    d.add_paragraph("Last updated: 12 August 2026")

    d.add_heading("1. Account summary", 1)
    d.add_paragraph(
        "Northwind Traders is a mid-market logistics company running 4,200 seats. "
        "They have been a customer for six years. Current annual contract value is "
        "USD 1.24M across productivity, security and a small analytics footprint."
    )
    d.add_paragraph(
        "The current three-year agreement expires on 30 November 2026. Renewal "
        "discussions began in June and have stalled twice."
    )

    d.add_heading("2. Stakeholders", 1)
    t = d.add_table(rows=1, cols=3)
    t.style = "Table Grid"
    hdr = t.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Name", "Role", "Position"
    for name, role, pos in [
        ("Marcus Feld", "CTO", "Champion. Sponsored the original deal."),
        ("Dana Kowalski", "Head of IT Security", "Blocker. Wants SOC 2 evidence before signing."),
        ("Ravi Chandra", "Procurement Lead", "Neutral. Driving the discount conversation."),
        ("Elena Voss", "CFO", "Sceptical. Asked for a cost-per-seat comparison in July."),
    ]:
        row = t.add_row().cells
        row[0].text, row[1].text, row[2].text = name, role, pos

    d.add_heading("3. Open risks", 1)
    for risk in [
        "Security review incomplete. Dana requires updated SOC 2 Type II evidence "
        "and a completed data residency questionnaire. This is the primary blocker.",
        "Procurement has requested a 15% discount, citing a competing quote. "
        "Approved discount authority is 8% without executive sign-off.",
        "Legal redlines on the Data Processing Addendum have been open since 4 August. "
        "Northwind's counsel wants EU-only data residency written into the DPA.",
        "Marcus Feld indicated in July he may move to a new role in Q1. Losing the "
        "champion before signature would be material.",
    ]:
        d.add_paragraph(risk, style="List Bullet")

    d.add_heading("4. Commercial position", 1)
    d.add_paragraph(
        "Target renewal value is USD 1.31M, a 5.6% uplift reflecting seat growth. "
        "Walk-away floor agreed with the deal desk is USD 1.18M. A 15% discount "
        "would take the deal to USD 1.05M, which is below floor and would require "
        "escalation to the regional director."
    )
    d.save(path)


def make_qbr_deck(path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    blank = prs.slide_layouts[1]

    slides = [
        (
            "Northwind Traders - Q2 Business Review",
            ["Reviewed 19 August 2026", "Presented by Priya Raman",
             "Attendees: Marcus Feld, Dana Kowalski, Ravi Chandra"],
            "Marcus was engaged throughout. Dana joined late and pushed hard on the "
            "security evidence. Do not open the next meeting with commercials - "
            "security has to be resolved first.",
        ),
        (
            "Adoption and value delivered",
            ["Monthly active usage up 22% year on year",
             "Security incidents down 31% since deployment",
             "Analytics pilot live with 40 users in the logistics planning team",
             "Support satisfaction 4.4 out of 5"],
            "Marcus asked us to quantify the incident reduction in currency terms "
            "for the CFO. That analysis has not been produced yet. Elena Voss will "
            "ask for it again.",
        ),
        (
            "Outstanding items before renewal",
            ["SOC 2 Type II evidence pack - owner Priya - NOT STARTED",
             "Data residency questionnaire - owner Priya - in progress",
             "DPA redlines with legal - open since 4 August",
             "Cost-per-seat benchmark for CFO - not started"],
            "This is the slide that matters. Every one of these is on our side, not "
            "theirs. Dana said plainly she will not approve without the SOC 2 pack.",
        ),
        (
            "Proposed renewal structure",
            ["Three-year term, 30 November 2026 start",
             "Target value USD 1.31M annually",
             "Seat growth from 4,200 to 4,450",
             "Discount discussion deferred to the next session"],
            "Ravi pushed for 15%. I did not commit to any number. Deal desk floor is "
            "1.18M - do not go below that without escalation.",
        ),
    ]

    for title, bullets, notes in slides:
        s = prs.slides.add_slide(blank)
        s.shapes.title.text = title
        body = s.placeholders[1].text_frame
        body.text = bullets[0]
        for b in bullets[1:]:
            p = body.add_paragraph()
            p.text = b
            p.level = 0
        s.notes_slide.notes_text_frame.text = notes

    prs.save(path)


def make_pricing(path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()

    ws = wb.active
    ws.title = "Renewal Summary"
    rows = [
        ["Line item", "Current term", "Proposed renewal", "Delta", "Notes"],
        ["Productivity seats", 4200, 4450, 250, "Seat growth in logistics planning"],
        ["Annual contract value USD", 1240000, 1310000, 70000, "5.6% uplift"],
        ["Term length years", 3, 3, 0, "No change requested"],
        ["Contract end date", "2026-11-30", "2029-11-30", "", "Hard deadline for signature"],
        ["Discount applied percent", 12, 12, 0, "Procurement asking for 15"],
        ["Deal desk floor USD", "", 1180000, "", "Below this requires escalation"],
        ["Value at 15 percent discount USD", "", 1050000, "", "BELOW FLOOR - needs regional director"],
    ]
    for r in rows:
        ws.append(r)

    ws2 = wb.create_sheet("Open Actions")
    actions = [
        ["Action", "Owner", "Due", "Status", "Blocking renewal"],
        ["SOC 2 Type II evidence pack", "Priya Raman", "2026-09-05", "Not started", "Yes"],
        ["Data residency questionnaire", "Priya Raman", "2026-09-05", "In progress", "Yes"],
        ["DPA redlines with legal", "Legal - S. Ahmed", "2026-09-12", "Open since 4 Aug", "Yes"],
        ["Cost per seat benchmark for CFO", "Priya Raman", "2026-09-19", "Not started", "No"],
        ["Incident reduction value analysis", "Priya Raman", "2026-09-19", "Not started", "No"],
        ["Confirm Marcus Feld role change", "Account team", "2026-09-08", "Not started", "No"],
    ]
    for r in actions:
        ws2.append(r)

    wb.save(path)


def make_emails(folder: Path) -> None:
    emails = [
        (
            "email_priya_handover.eml",
            "priya.raman@contoso.com",
            "account-team@contoso.com",
            "Mon, 25 Aug 2026 18:42:00 +0530",
            "Northwind - handing over, out from tomorrow",
            """Team,

I am going out on unplanned medical leave from tomorrow and will be
unreachable for at least three weeks. Handing over Northwind.

Where things stand:

The renewal signature deadline is 30 November. That is hard - their
current agreement lapses and procurement will not backdate.

The single blocker is Dana Kowalski in security. She will not approve
until she has the SOC 2 Type II evidence pack and the completed data
residency questionnaire. I had not started the SOC 2 pack. The
questionnaire is about half done, saved in the shared account folder.

Do NOT lead the next conversation with pricing. Ravi will try to pull
you into the 15% discussion immediately. Our floor is 1.18M and 15%
puts us at 1.05M which is below it. Deflect to security and tell him
commercials follow once Dana signs off.

Marcus is still our champion but he hinted in July he may move roles in
Q1. Worth confirming quietly.

Legal have had the DPA redlines since 4 August. Chase S. Ahmed.

Priya""",
        ),
        (
            "email_customer_escalation.eml",
            "dana.kowalski@northwindtraders.com",
            "account-team@contoso.com",
            "Thu, 28 Aug 2026 09:15:00 +0000",
            "RE: Northwind renewal - security evidence still outstanding",
            """Hello,

Following up for the third time. We are now four weeks from our
internal approval cut-off and I still do not have:

1. The SOC 2 Type II report covering the current audit period
2. A completed data residency questionnaire confirming EU-only
   processing for our logistics data
3. Written confirmation that sub-processors have not changed since
   the last review

I want to be direct. Our board requires the security sign-off before
procurement can even open commercial terms. If I do not have these by
12 September I will have to recommend we extend the current agreement
on a short-term basis while we evaluate alternatives.

I would rather not do that. Please advise on timing.

Dana Kowalski
Head of IT Security
Northwind Traders""",
        ),
        (
            "email_procurement_discount.eml",
            "ravi.chandra@northwindtraders.com",
            "account-team@contoso.com",
            "Fri, 29 Aug 2026 14:03:00 +0000",
            "Northwind renewal - commercial terms",
            """Hi,

Picking up where we left off at the August review.

We have a competing proposal that comes in materially below your
renewal number. To be competitive I need 15% off the proposed annual
value, or a two-year term at the current rate rather than three.

I appreciate Priya said commercials come after security. But our
timelines are compressing and I would like both tracks running in
parallel.

Can we get a revised quote before the next call?

Ravi Chandra
Procurement Lead""",
        ),
    ]

    for fname, sender, to, date, subject, body in emails:
        (folder / fname).write_text(
            f"From: {sender}\nTo: {to}\nDate: {date}\nSubject: {subject}\n"
            f"MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\n\n{body}\n",
            encoding="utf-8",
        )


def make_notes(path: Path) -> None:
    path.write_text(
        """# Northwind Traders - call notes 19 August 2026

Attendees: Marcus Feld (CTO), Dana Kowalski (Security), Ravi Chandra
(Procurement), Priya Raman (us)

# Security

Dana repeated that the SOC 2 Type II evidence pack is mandatory. She was
firm. Said her board will not let procurement open commercials until
security signs off. Asked specifically about sub-processor changes.

Priya committed to delivering the evidence pack by 5 September.

# Commercial

Ravi raised the 15% discount again, referencing a competing quote he
would not name. Priya deflected and did not commit to a number.

Marcus asked for the security incident reduction to be expressed in
currency terms so he can take it to Elena Voss, the CFO. Nobody owns
this yet.

# Timeline

Contract lapses 30 November. Dana's internal approval cut-off is 12
September. That is the real deadline, not November.

# Next steps

- Priya to produce SOC 2 evidence pack
- Priya to finish data residency questionnaire
- Chase legal on DPA redlines, open since 4 August
- Someone to own the CFO cost-per-seat benchmark
""",
        encoding="utf-8",
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        make_account_plan(OUT / "Northwind_Account_Plan.docx")
        make_qbr_deck(OUT / "Northwind_QBR_August.pptx")
        make_pricing(OUT / "Northwind_Renewal_Pricing.xlsx")
    except ImportError as exc:
        print(f"Missing a generator dependency: {exc}")
        print("Run: pip install python-docx python-pptx openpyxl")
        return 1
    make_emails(OUT)
    make_notes(OUT / "call_notes_2026-08-19.md")
    print(f"Demo scenario written to {OUT}")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
