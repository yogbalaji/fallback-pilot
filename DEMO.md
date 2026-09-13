# Demo runbook

A three-minute recording. The whole thing turns on one moment: the network
goes off and nothing changes.

---

## Before you record

Do all of this. Every item is something that has actually gone wrong.

```powershell
# 1. Runtime up on the pinned port. This does NOT survive a reboot.
foundry server start --port 39839 --idle-timeout 0
foundry model load phi-4-mini
foundry model load qwen3-embedding-0.6b

# 2. Index built
fallback-pilot ingest

# 3. Tier 1 confirmed
fallback-pilot doctor

# 4. Warm the model - the FIRST generation after loading is slower.
#    Run one throwaway brief so the recording gets a representative time.
fallback-pilot brief "warm up" --no-draft
```

Then:

- [ ] **Close Teams, Outlook, Slack.** A notification banner mid-recording is unusable.
- [ ] Windows notifications off (Focus assist / Do not disturb).
- [ ] Browser at ~125% zoom. Text must be readable when the video is scaled down.
- [ ] **Know how to turn Wi-Fi off in one click.** Practise it. Fumbling for the
      toggle kills the pace at the most important moment.
- [ ] **Unplug Ethernet and disconnect any VPN.** With either connected, turning
      off Wi-Fi changes nothing and the badge will correctly stay on tier 1.
      Confirm with `fallback-pilot probe` before you record.
- [ ] Task Manager open on a second screen, Performance tab, NPU visible.
- [ ] Screen recorder set to capture the browser window, not the full desktop.

---

## The script

### 0:00 — the problem (20 seconds)

> "Your best player is unavailable. The expert who owns this account went on
> medical leave three weeks before a hard deadline, the customer is escalating,
> and you are on a train with no signal. Everything you need is already on your
> laptop. You just cannot read it fast enough."

### 0:20 — what it has (25 seconds)

```powershell
fallback-pilot ui
```

Point at the browser:

> "Seven files. An account plan, a QBR deck, a pricing sheet, three emails,
> call notes. Normal work files, sitting in a folder."

Point at the tier badge:

> "Tier 1. There is a network, but paid cloud AI is off the table. So this runs
> a two-gigabyte Microsoft model on the NPU of a standard corporate laptop."

### 0:45 — generate (60 seconds)

Click **Get me ready**.

While it streams - do not stand in silence, narrate:

> "Retrieval took forty milliseconds. It is now writing from eight sources
> across all seven files."
>
> "Every claim carries a citation. That number maps to a file you can open.
> This matters: the app checks the citations afterwards, and if the model cites
> a source it was never given, the brief is flagged as unverified rather than
> printed as fact."

When it lands, read one line aloud - the strongest one:

> "'A fifteen percent discount takes the deal to 1.05 million, below the
> walk-away floor of 1.18 million.' That number is in a spreadsheet. The
> deadline is in call notes. The blocker is in an email. Three files, one
> answer."

### 1:45 — THE MOMENT (35 seconds)

Say this first, so they know what to watch:

> "Now watch the badge in the corner."

**Turn Wi-Fi off.** Wait two to three seconds for the badge to flip to
**Tier 2 · offline**. It confirms with a real connection attempt rather than
trusting the routing table, so it is deliberately not instant.

> If you are plugged into Ethernet, or on a VPN, unplug it first - otherwise
> you still have a network and the badge is right to say so. Verify before you
> record with `fallback-pilot probe`.

> "Tier 2. No network at all."

Click **Get me ready** again. Let it stream.

> "Same brief. Same sources. Same time. Nothing degraded, because nothing was
> ever depending on the network."

### 2:20 — the floor (25 seconds)

In a second terminal:

```powershell
foundry model unload phi-4-mini
# Or, more decisively:  foundry server stop
```

Click **Get me ready** once more.

> "And if the model will not load at all - low battery, NPU busy, a machine too
> old - it drops to tier 3 and extracts the brief straight from your files.
> Less fluent. Still cited. Still useful. That is the difference between
> degrading and failing."

### 2:45 — close (15 seconds)

> "No cloud AI. No subscription. No new hardware. Fallback Pilot runs on the
> laptop you already have - and it keeps working when your best player, your
> network, or your cloud AI is not there."

---

## If something breaks mid-recording

| Symptom | Cause | Say this and move on |
|---|---|---|
| Badge stuck on tier 3 | Runtime died | "The runtime needs restarting - that is tier 3 doing its job." |
| Brief is slow | Cold model | Keep narrating the citations. Never apologise for the wait. |
| Badge slow to flip | Windows releasing the adapter | Wait. It is 2-second polling, not a hang. |
| Blank brief | Index missing | Stop. `fallback-pilot ingest`. Re-record. |

**Do not restart the recording for a small stumble.** A demo that visibly
recovers reads as real. A demo that is too smooth reads as a video.

---

## Worth capturing separately

Short clips, no narration, useful as cutaways or as evidence in the write-up:

1. **Task Manager NPU graph** spiking while a brief generates. This is the proof
   that it runs on the NPU of a non-Copilot+ machine.
2. **`python scripts/eval_retrieval.py`** with and without the embedding model -
   shows retrieval was measured, not eyeballed.
3. **`docs/model_comparison.md`** on screen - shows model choice was tested.
4. **`index/chunks.jsonl` open in an editor** - answers "how do I know it is not
   uploading my documents?" better than any claim.
