## The tier badge is stuck on tier 1

Run:

```powershell
fallback-pilot probe
```

It prints every raw signal behind the tier decision. The two that matter:

- **TCP to 1.1.1.1:443** - if this says `True` with your Wi-Fi off, something
  else is providing connectivity (Ethernet, a VPN, a phone hotspot).
- **Models endpoint** - if this lists models after you unloaded them, the
  runtime is still serving its catalogue.

If a corporate firewall blocks outbound 443 to 1.1.1.1, the app will read as
offline while you are online. Point it somewhere your network does allow:

```yaml
availability:
  network_probe_host: "8.8.8.8"
  network_probe_port: 443
```

## Turning Wi-Fi off did not move it to tier 2

Windows keeps routes alive through virtual adapters - WSL, Hyper-V, Docker, a
VPN client - so the routing table still claims a path to the internet. The app
now makes a real TCP connection to confirm, which takes about a second. Give
the badge two to three seconds to catch up.

If it still does not move, check whether you are on Ethernet as well as Wi-Fi.

## Unloading the model did not move it to tier 3

Use `foundry model unload <name>` and confirm with `fallback-pilot probe` that
the models endpoint reports `0 model(s)`. Stopping the whole server with
`foundry server stop` is the more decisive way to show tier 3.

## `fallback-pilot` is not recognized
The install did not complete. The most common cause is a missing trailing dot:

```powershell
pip install -e .
```

That `.` means "the project in this folder". Without it, pip errors with
`-e option requires 1 argument` and nothing gets installed.

Or skip installing altogether:

```powershell
python run.py ingest
python run.py brief "Northwind renewal"
```

# Troubleshooting Step 1

## `foundry` is not recognized
The install needs a **new** terminal. Close VS Code's terminal and open a fresh
one, then `foundry --version`.

## "Request to local service failed" / port 127.0.0.1:0
The server is running but not bound properly. Restart it pinned:
```powershell
foundry server restart --port 39839 --idle-timeout 0
```

## doctor still shows "Endpoint: none discovered"
Find the real port and tell the app directly:
```powershell
foundry server status
```
Copy the URL it prints, then in `config.yaml` set:
```yaml
runtime:
  endpoint: "http://localhost:<PORT>/v1"
```

## The model download is huge / slow
`qwen2.5-0.5b` is the smallest. Force the CPU variant if hardware detection
misfires:
```powershell
foundry model load qwen2.5-0.5b-instruct-generic-cpu
```

## Server keeps shutting down between commands
That's the idle timeout. Always start with `--idle-timeout 0`.

## `pip install -e .` fails
Fall back to the plain path approach:
```powershell
pip install -r requirements.txt
$env:PYTHONPATH="src"
python -m fallback_pilot.cli doctor
```

## Which tier should I see?
- Model loaded, Wi-Fi on  -> **tier 1** (cloud AI withheld by policy)
- Model loaded, Wi-Fi off -> **tier 2** (offline, same answer)
- No model at all         -> **tier 3** (extractive, still answers)

If Wi-Fi off gives you tier 2 with a real answer, Step 1 is done.

## `ingest` finds no files
Check `context.sources` in `config.yaml`. Paths are relative to where you run
the command, so run it from the project folder. Use full paths for folders
elsewhere on disk:
```yaml
context:
  sources:
    - C:\Users\you\Documents\SomeAccount
```

## A PDF shows as "skipped"
PDF support is optional:
```powershell
pip install pypdf
```
Word, PowerPoint and Excel never need this.

## A file shows as "error"
It is corrupt, password-protected, or still open in Office with a lock file.
Ingest deliberately never stops on a bad file - it reports it and moves on.

## I want to see exactly what was read
```powershell
notepad index\chunks.jsonl
```
One JSON object per chunk, including the file and section it came from.

## `search` says "keyword only"
That is a working state, not an error - keyword search needs no model. To add
semantic search:
```powershell
foundry model load qwen3-embedding-0.6b
fallback-pilot search "your question" --rebuild
```

## Embeddings are slow the first time
Every chunk is embedded once, then cached in `index/embeddings.json`. Later
searches reuse the cache. It recomputes automatically if your documents change.

## Search results look wrong after editing documents
Re-ingest, then rebuild:
```powershell
fallback-pilot ingest
fallback-pilot search "your question" --rebuild
```

## How do I know retrieval is actually good?
```powershell
python scripts/eval_retrieval.py
```
Scores real questions against the files that should answer them.
