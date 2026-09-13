import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fallback_pilot.ingest import ingest_paths  # noqa: E402
from fallback_pilot.ingest.chunker import TARGET_CHARS, chunk_blocks  # noqa: E402
from fallback_pilot.ingest.readers import Block, discover, read_any  # noqa: E402
from fallback_pilot.ingest.store import load_chunks, save_chunks  # noqa: E402

DEMO = ROOT / "demo_data"


def test_discovers_every_demo_format():
    found = {p.suffix.lower() for p in discover(DEMO)}
    assert {".docx", ".pptx", ".xlsx", ".md", ".eml"} <= found


def test_word_tracks_headings():
    blocks = read_any(DEMO / "Northwind_Account_Plan.docx")
    assert blocks
    assert any("Open risks" in b.location for b in blocks)
    assert any(b.kind == "table" for b in blocks)


def test_powerpoint_extracts_speaker_notes():
    blocks = read_any(DEMO / "Northwind_QBR_August.pptx")
    notes = [b for b in blocks if b.kind == "notes"]
    assert notes, "speaker notes carry the real context and must be read"
    assert any("floor" in b.text.lower() for b in notes)


def test_excel_labels_rows_with_headers():
    blocks = read_any(DEMO / "Northwind_Renewal_Pricing.xlsx")
    joined = "\n".join(b.text for b in blocks)
    assert "Owner: Priya Raman" in joined, "values must travel with their column name"
    assert any("Open Actions" in b.location for b in blocks)


def test_email_keeps_sender_and_subject():
    blocks = read_any(DEMO / "email_priya_handover.eml")
    assert blocks
    assert "priya.raman" in blocks[0].text
    assert all(b.meta.get("subject") for b in blocks)


def test_long_email_splits_but_every_part_keeps_context():
    """Each fragment must still say who sent it and what it is about."""
    blocks = read_any(DEMO / "email_priya_handover.eml")
    assert len(blocks) > 1, "a long handover email should not be one blob"
    for b in blocks:
        assert "priya" in b.text.lower()
        assert b.meta["subject"] in b.text


def test_unsupported_file_is_ignored(tmp_path):
    junk = tmp_path / "photo.jpeg"
    junk.write_bytes(b"\xff\xd8\xff")
    assert read_any(junk) == []


def test_corrupt_file_does_not_raise(tmp_path):
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"this is not a zip archive")
    blocks = read_any(broken)
    assert len(blocks) == 1 and blocks[0].kind == "error"


def test_chunks_respect_size_budget():
    long_text = ". ".join(f"Sentence number {i} about the renewal" for i in range(400))
    chunks = chunk_blocks([Block(long_text, "x.docx", "x", "body", "paragraph")])
    assert len(chunks) > 1
    assert all(len(c.text) <= TARGET_CHARS + 200 for c in chunks)


def test_duplicate_text_is_deduplicated():
    b = Block("The renewal is blocked on the security review evidence pack.", "a.docx", "a", "body")
    b2 = Block("The renewal is blocked on the security review evidence pack.", "b.docx", "b", "body")
    assert len(chunk_blocks([b, b2])) == 1


def test_citation_names_file_and_location():
    chunks, _ = ingest_paths([str(DEMO)])
    cited = [c for c in chunks if "Slide" in c.location]
    assert cited
    assert cited[0].citation.endswith(cited[0].location)
    assert ".pptx" in cited[0].citation


def test_roundtrip_through_store(tmp_path):
    chunks, report = ingest_paths([str(DEMO)])
    assert all(r["status"] == "ok" for r in report)
    save_chunks(chunks, tmp_path)
    assert len(load_chunks(tmp_path)) == len(chunks)
