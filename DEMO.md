# Demo runbook - two minutes

The form requires a video of **no more than two minutes** that demonstrates the
working solution and explains its value to the target customer. Two minutes is
short. This script is timed, and the cuts are deliberate.

The generation itself takes 60-90 seconds, which would consume the whole video.
**So the agent runs before you start recording** - which is the honest thing to
show anyway, because the agent is supposed to have already done the work by the
time you look.

---

## Pre-flight

```powershell
# 1. Runtime up. Does NOT survive a reboot.
foundry server start --port 39839 --idle-timeout 0
foundry model load phi-4-mini
foundry model load qwen3-embedding-0.6b

# 2. Index built
fallback-pilot ingest

# 3. Put the meeting 30 minutes out so the agent has a reason to act
python scripts/set_demo_meeting.py --minutes 30

# 4. Confirm tier 1
fallback-pilot probe

# 5. Let the agent do its work NOW, before recording.
#    This is what you will be showing: work already done.
#    IT TAKES 60-90 SECONDS. Do not press Ctrl+C - the brief is
#    being written on the NPU and interrupting it loses the work.
fallback-pilot watch --once

# 6. Confirm there is something to approve
fallback-pilot approvals
```

- [ ] Close Teams, Outlook, Slack. Notifications off.
- [ ] Browser at ~125% zoom.
- [ ] **Unplug Ethernet, disconnect VPN.** Otherwise Wi-Fi off changes nothing.
- [ ] Practise the Wi-Fi toggle until it is one click.
- [ ] Recorder capturing the browser window only.

---

## The script

### 0:00-0:20 | The problem, and who has it

Open `fallback-pilot ui` already loaded, agent panel visible.

> "This is for anyone who picks up work someone else owned. Your colleague is on
> leave, the customer is escalating, and you have a call in thirty minutes.
> Everything you need is already on your laptop - you just can't read it fast
> enough."

### 0:20-0:50 | It already did the work

Point at the **agent activity feed**.

> "Nobody asked it to do this. It saw a meeting coming up in my calendar,
> noticed no brief existed yet, and prepared one. Every line here records what
> triggered it and why it decided to act."

Scroll the brief.

> "Situation, open actions with owners and dates, blockers, next step. Every
> claim cites the file it came from. The walk-away price is in a spreadsheet,
> the real deadline is in call notes, the blocker is in an email - three files,
> one answer."

### 0:50-1:15 | The part it will not do

Point at the **approval card**.

> "It also drafted a reply to the customer who's been chasing us. It has not
> sent it. It cannot send it - there's no send capability in the code. It
> prepares; I decide."

Click **Approve**. Show it move into the log.

> "And that decision is logged too."

### 1:15-1:45 | THE MOMENT

> "Now watch the badge."

**Turn Wi-Fi off.** Wait for **Tier 2**.

> "No network. The agent is still running, still watching, and the brief it
> produces is identical - because nothing here ever depended on the network."

Click **Check now**.

### 1:45-2:00 | Close

> "No cloud AI. No subscription. No new hardware - this is an eleven-TOPS NPU
> in a standard work laptop, well under the Copilot+ bar. Fallback Pilot keeps
> work moving when your best player, your network, or your cloud AI isn't
> there."

---

## Timing discipline

| Segment | Budget | If you overrun |
|---|---|---|
| Problem | 20s | Cut to one sentence |
| Agent did it | 30s | Skip scrolling the brief |
| Approval | 25s | Do not cut - this is confirmation #6 |
| Offline | 30s | Do not cut - this is the whole thesis |
| Close | 15s | Cut the NPU detail, keep "no subscription" |

**The two segments never to cut** are the approval queue and the offline
switch. They are the two things judges are explicitly asked to verify.

---

## If something breaks

| Symptom | Say this |
|---|---|
| Badge stuck tier 1 | You still have a connection - Ethernet or VPN |
| Nothing in the feed | `fallback-pilot watch --once` beforehand |
| No approval card | Nobody in the demo data is waiting - check `approvals` |
| Badge slow to flip | It confirms with a real connection. 2-3 seconds. |

Do not restart for a small stumble. A demo that recovers reads as real.

---

## Worth capturing separately

Not part of the two minutes - useful as evidence in the project description.

1. Task Manager **NPU graph** spiking during generation.
2. `python scripts/eval_retrieval.py` with and without embeddings.
3. `docs/model_comparison.md` on screen.
4. `index/agent_activity.jsonl` open in an editor.
5. `index/chunks.jsonl` - answers "is it uploading my documents?"
