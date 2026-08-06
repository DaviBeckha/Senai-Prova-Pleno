import re
from dataclasses import dataclass

from pypdf import PdfReader

from app.core.maintenance_intent import ContentRole, classify_content_role

_NUMBERED_LINE = re.compile(r"^(\d+(?:\.\d+)*)[\.)]?\s+(.{3,120})$")
_STEP_END = re.compile(r"[.;:]$")


@dataclass
class Chunk:
    doc_family: str
    source: str
    section: str
    text: str
    section_path: tuple[str, ...] = ()
    content_role: ContentRole = ContentRole.GENERAL
    document_order: int = 0


@dataclass(frozen=True)
class _Heading:
    number: str
    title: str
    original: str
    line_index: int


def _heading_for(line: str, line_index: int) -> _Heading | None:
    stripped = line.strip()
    match = _NUMBERED_LINE.fullmatch(stripped)
    if match is None:
        return None
    number, title = match.groups()
    if "." not in number and _STEP_END.search(title.strip()):
        return None
    return _Heading(number, title.strip(), stripped, line_index)


def _split_payload(payload: str, context: str, max_chars: int) -> list[str]:
    payload = payload.strip()
    if not payload:
        return [context]
    complete = f"{context}\n{payload}"
    if len(complete) <= max_chars:
        return [complete]

    available = max(max_chars - len(context) - 1, 1)
    paragraphs = [
        part.strip()
        for part in re.split(r"\n\s*\n", payload)
        if part.strip()
    ]
    if len(paragraphs) == 1:
        paragraphs = [line.strip() for line in payload.splitlines() if line.strip()]

    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= available:
            units.append(paragraph)
            continue
        units.extend(
            paragraph[start:start + available]
            for start in range(0, len(paragraph), available)
        )

    parts: list[str] = []
    current = ""
    for unit in units:
        candidate = unit if not current else f"{current}\n\n{unit}"
        if current and len(candidate) > available:
            parts.append(f"{context}\n{current}")
            current = unit
        else:
            current = candidate
    if current:
        parts.append(f"{context}\n{current}")
    return parts


def _fallback_chunks(
    text: str,
    doc_family: str,
    source: str,
    max_chars: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for start in range(0, len(text), max_chars):
        segment = text[start:start + max_chars]
        if segment.strip():
            chunks.append(Chunk(
                doc_family,
                source,
                f"parte {start // max_chars + 1}",
                segment,
                content_role=classify_content_role((), segment),
                document_order=len(chunks),
            ))
    return chunks


def chunk_text(
    text: str,
    doc_family: str,
    source: str,
    max_chars: int = 1500,
) -> list[Chunk]:
    lines = text.splitlines()
    headings = [
        heading
        for index, line in enumerate(lines)
        if (heading := _heading_for(line, index)) is not None
    ]
    if not headings:
        return _fallback_chunks(text, doc_family, source, max_chars)

    chunks: list[Chunk] = []
    parents: dict[int, str] = {}
    for position, heading in enumerate(headings):
        depth = heading.number.count(".") + 1
        parents[depth] = heading.original
        parents = {
            level: value
            for level, value in parents.items()
            if level <= depth
        }
        section_path = tuple(parents[level] for level in sorted(parents))
        next_line = (
            headings[position + 1].line_index
            if position + 1 < len(headings)
            else len(lines)
        )
        payload = "\n".join(lines[heading.line_index + 1:next_line])
        context = "\n".join(section_path)
        role = classify_content_role(section_path, payload)
        section = f"{heading.number}. {heading.title}"
        for part in _split_payload(payload, context, max_chars):
            chunks.append(Chunk(
                doc_family,
                source,
                section,
                part,
                section_path=section_path,
                content_role=role,
                document_order=len(chunks),
            ))
    return chunks


def chunk_pdf(path: str, doc_family: str) -> list[Chunk]:
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    source = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return chunk_text(text, doc_family=doc_family, source=source)


def chunk_file(path: str, doc_family: str) -> list[Chunk]:
    """Segmenta PDF ou transcrição UTF-8 em blocos hierárquicos."""
    lower = path.lower()
    if lower.endswith(".pdf"):
        return chunk_pdf(path, doc_family)
    if lower.endswith(".md") or lower.endswith(".txt"):
        with open(path, "r", encoding="utf-8") as file:
            text = file.read()
        source = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return chunk_text(text, doc_family=doc_family, source=source)
    raise ValueError(f"unsupported file extension for chunk_file: {path!r}")
