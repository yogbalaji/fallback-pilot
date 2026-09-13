from .chunker import Chunk, chunk_blocks
from .readers import Block, discover, read_any
from .store import load_chunks, save_chunks


def ingest_paths(paths: list[str], root=None) -> tuple[list[Chunk], list[dict]]:
    """Read every supported file under the given paths and chunk it.

    Returns the chunks plus a per-file report, so the caller can tell the user
    what was skipped and why rather than silently dropping files.
    """
    blocks: list[Block] = []
    report: list[dict] = []

    for p in paths:
        for f in discover(p):
            file_blocks = read_any(f)
            problems = [b for b in file_blocks if b.kind in ("skipped", "error")]
            usable = [b for b in file_blocks if b.kind not in ("skipped", "error")]
            blocks.extend(usable)
            report.append(
                {
                    "file": str(f),
                    "name": f.name,
                    "blocks": len(usable),
                    "status": "ok" if usable else ("skipped" if problems else "empty"),
                    "reason": problems[0].meta.get("reason", "") if problems else "",
                }
            )

    return chunk_blocks(blocks), report
