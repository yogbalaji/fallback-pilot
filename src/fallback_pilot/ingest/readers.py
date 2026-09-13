"""Turn local Office files into structured text blocks.

Word, PowerPoint and Excel are parsed with the standard library alone. Their
formats are ZIP archives of XML, so no third-party parser is needed - which
keeps the install small, the startup fast, and nothing reaching the network.
PDF is the one exception and degrades gracefully when its reader is absent.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"

SUPPORTED = {".docx", ".pptx", ".xlsx", ".pdf", ".txt", ".md", ".eml"}


@dataclass
class Block:
    """One coherent piece of text plus where it came from."""
    text: str
    source: str
    title: str
    location: str
    kind: str = "paragraph"
    meta: dict = field(default_factory=dict)


def _clean(text: str) -> str:
    return re.sub(r"[ \t\u00a0]+", " ", (text or "")).strip()


def _natural_key(name: str) -> tuple:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name))


# --------------------------------------------------------------------- Word

def _docx_para_text(p: ET.Element) -> str:
    """Word splits a sentence across runs; join them or you get fragments."""
    parts: list[str] = []
    for node in p.iter():
        if node.tag == f"{W}t":
            parts.append(node.text or "")
        elif node.tag in (f"{W}tab",):
            parts.append("\t")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
    return _clean("".join(parts))


def _docx_style(p: ET.Element) -> str:
    pPr = p.find(f"{W}pPr")
    if pPr is None:
        return ""
    st = pPr.find(f"{W}pStyle")
    return st.get(f"{W}val", "") if st is not None else ""


def read_docx(path: Path) -> list[Block]:
    blocks: list[Block] = []
    with zipfile.ZipFile(path) as z:
        if "word/document.xml" not in z.namelist():
            return blocks
        root = ET.fromstring(z.read("word/document.xml"))

    body = root.find(f"{W}body")
    if body is None:
        return blocks

    heading = ""
    for el in body:
        if el.tag == f"{W}p":
            text = _docx_para_text(el)
            if not text:
                continue
            style = _docx_style(el)
            if style.lower().startswith("heading") or style in ("Title", "Subtitle"):
                heading = text
                blocks.append(Block(text, str(path), path.stem, text, "heading"))
            else:
                loc = f"under '{heading}'" if heading else "body"
                blocks.append(Block(text, str(path), path.stem, loc, "paragraph"))

        elif el.tag == f"{W}tbl":
            rows: list[str] = []
            for tr in el.findall(f"{W}tr"):
                cells = [
                    _clean(" ".join(_docx_para_text(p) for p in tc.findall(f"{W}p")))
                    for tc in tr.findall(f"{W}tc")
                ]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                loc = f"table under '{heading}'" if heading else "table"
                blocks.append(Block("\n".join(rows), str(path), path.stem, loc, "table"))
    return blocks


# --------------------------------------------------------------- PowerPoint

def read_pptx(path: Path) -> list[Block]:
    blocks: list[Block] = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        slides = sorted(
            (n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=_natural_key,
        )
        for slide_path in slides:
            num = re.search(r"slide(\d+)\.xml", slide_path).group(1)
            root = ET.fromstring(z.read(slide_path))
            lines = [_clean(t.text) for t in root.iter(f"{A}t") if _clean(t.text or "")]
            if lines:
                blocks.append(
                    Block("\n".join(lines), str(path), path.stem, f"Slide {num}", "slide")
                )

            notes_path = f"ppt/notesSlides/notesSlide{num}.xml"
            if notes_path in names:
                nroot = ET.fromstring(z.read(notes_path))
                notes = [_clean(t.text) for t in nroot.iter(f"{A}t") if _clean(t.text or "")]
                # Strip the slide-number placeholder PowerPoint injects.
                notes = [n for n in notes if n != num]
                if notes:
                    blocks.append(
                        Block(
                            "\n".join(notes), str(path), path.stem,
                            f"Slide {num} (speaker notes)", "notes",
                        )
                    )
    return blocks


# -------------------------------------------------------------------- Excel

def _xlsx_shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall(f"{S}si"):
        out.append(_clean("".join(t.text or "" for t in si.iter(f"{S}t"))))
    return out


def _xlsx_sheets(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Map sheet display names to their part paths, in workbook order."""
    names = z.namelist()
    if "xl/workbook.xml" not in names:
        return []
    wb = ET.fromstring(z.read("xl/workbook.xml"))

    rel_map: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in names:
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.findall(f"{PR}Relationship"):
            target = rel.get("Target", "")
            target = target[1:] if target.startswith("/") else f"xl/{target.lstrip('./')}"
            rel_map[rel.get("Id", "")] = target

    out: list[tuple[str, str]] = []
    sheets_el = wb.find(f"{S}sheets")
    if sheets_el is None:
        return out
    for i, sh in enumerate(sheets_el.findall(f"{S}sheet"), start=1):
        rid = sh.get(f"{R}id", "")
        part = rel_map.get(rid) or f"xl/worksheets/sheet{i}.xml"
        if part in names:
            out.append((sh.get("name", f"Sheet{i}"), part))
    return out


def _cell_value(c: ET.Element, shared: list[str]) -> str:
    ctype = c.get("t", "")
    if ctype == "inlineStr":
        return _clean("".join(t.text or "" for t in c.iter(f"{S}t")))
    v = c.find(f"{S}v")
    if v is None or v.text is None:
        return ""
    if ctype == "s":
        idx = int(v.text)
        return shared[idx] if 0 <= idx < len(shared) else ""
    return _clean(v.text)


def read_xlsx(path: Path) -> list[Block]:
    """Emit one line per row, labelled by header.

    'Renewal date: 2026-11-30 | Owner: Priya' retrieves far better than a bare
    grid of values, because the labels travel with the numbers.
    """
    blocks: list[Block] = []
    with zipfile.ZipFile(path) as z:
        shared = _xlsx_shared_strings(z)
        for sheet_name, part in _xlsx_sheets(z):
            root = ET.fromstring(z.read(part))
            rows: list[list[str]] = []
            for row in root.iter(f"{S}row"):
                vals = [_cell_value(c, shared) for c in row.findall(f"{S}c")]
                if any(vals):
                    rows.append(vals)
            if not rows:
                continue

            header = rows[0]
            labelled: list[str] = []
            for r in rows[1:]:
                pairs = [
                    f"{header[i]}: {v}"
                    for i, v in enumerate(r)
                    if v and i < len(header) and header[i]
                ]
                if pairs:
                    labelled.append(" | ".join(pairs))

            body = "\n".join(labelled) if labelled else "\n".join(" | ".join(r) for r in rows)
            blocks.append(
                Block(
                    f"Columns: {', '.join(h for h in header if h)}\n{body}",
                    str(path), path.stem, f"Sheet '{sheet_name}'", "sheet",
                )
            )
    return blocks


# ---------------------------------------------------------------- PDF, text

def read_pdf(path: Path) -> list[Block]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return [
            Block(
                "", str(path), path.stem, "unavailable", "skipped",
                {"reason": "PDF support needs the pypdf package"},
            )
        ]
    blocks: list[Block] = []
    reader = PdfReader(str(path))
    for i, page in enumerate(reader.pages, start=1):
        text = _clean(page.extract_text() or "")
        if text:
            blocks.append(Block(text, str(path), path.stem, f"Page {i}", "page"))
    return blocks


def read_text(path: Path) -> list[Block]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: list[Block] = []
    section = "body"
    buf: list[str] = []

    def flush():
        joined = _clean("\n".join(buf))
        if joined:
            blocks.append(Block(joined, str(path), path.stem, section, "paragraph"))
        buf.clear()

    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            section = _clean(line.lstrip("#"))
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)
    flush()
    return blocks


def read_eml(path: Path) -> list[Block]:
    import email
    from email import policy

    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    subject = _clean(msg.get("Subject", "") or path.stem)
    sender = _clean(msg.get("From", "") or "unknown sender")
    date = _clean(msg.get("Date", "") or "")
    to = _clean(msg.get("To", "") or "")

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_content()
                break
    else:
        body = msg.get_content()

    meta = {"from": sender, "to": to, "date": date, "subject": subject}
    short_sender = sender.split("<")[-1].strip(">").strip() or sender
    header = f"From: {sender}\nTo: {to}\nDate: {date}\nSubject: {subject}"

    # A long email is several topics wearing one envelope. Splitting on blank
    # lines lets each point be retrieved on its own merits instead of being
    # diluted across one oversized chunk - while the subject line rides along
    # on every piece so no fragment loses its context.
    paras = [_clean(p) for p in re.split(r"\n\s*\n", body or "") if _clean(p)]
    substantive = [p for p in paras if len(p) > 40]

    if len(substantive) < 2:
        return [
            Block(f"{header}\n\n{_clean(body)}", str(path), subject,
                  f"email from {short_sender}", "email", dict(meta))
        ]

    blocks = [
        Block(f"{header}\n\n{substantive[0]}", str(path), subject,
              f"email from {short_sender}", "email", dict(meta))
    ]
    for i, para in enumerate(substantive[1:], start=2):
        blocks.append(
            Block(
                f"Email: {subject}\nFrom: {short_sender}\n\n{para}",
                str(path), subject,
                f"email from {short_sender} (part {i})", "email", dict(meta),
            )
        )
    return blocks


_READERS = {
    ".docx": read_docx,
    ".pptx": read_pptx,
    ".xlsx": read_xlsx,
    ".pdf": read_pdf,
    ".txt": read_text,
    ".md": read_text,
    ".eml": read_eml,
}


def read_any(path: str | Path) -> list[Block]:
    """Read one file. Never raises - a bad file must not stop an ingest run."""
    p = Path(path)
    reader = _READERS.get(p.suffix.lower())
    if reader is None:
        return []
    try:
        return [b for b in reader(p) if b.text or b.kind == "skipped"]
    except Exception as exc:
        return [
            Block("", str(p), p.stem, "unreadable", "error", {"reason": f"{type(exc).__name__}: {exc}"})
        ]


def discover(root: str | Path, recursive: bool = True) -> list[Path]:
    base = Path(root).expanduser()
    if base.is_file():
        return [base] if base.suffix.lower() in SUPPORTED else []
    pattern = "**/*" if recursive else "*"
    return sorted(
        p for p in base.glob(pattern)
        if p.is_file()
        and p.suffix.lower() in SUPPORTED
        and not p.name.startswith("~$")   # Word/Excel lock files
        and not p.name.startswith(".")
    )
