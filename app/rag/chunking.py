import re
from dataclasses import dataclass

from pypdf import PdfReader

_SECTION = re.compile(r"^(\d+(?:\.\d+)*)[\.\)]?\s+(.{3,80})$", re.MULTILINE)


@dataclass
class Chunk:
    doc_family: str
    source: str
    section: str
    text: str


def chunk_text(text: str, doc_family: str, source: str, max_chars: int = 1500) -> list[Chunk]:
    matches = list(_SECTION.finditer(text))
    chunks: list[Chunk] = []
    if not matches:
        for i in range(0, len(text), max_chars):
            segment = text[i:i + max_chars]
            # Segmentos 100% whitespace (ex.: PDF escaneado, sem camada de
            # texto extraivel — extract_text() devolve "" por pagina e o join
            # sobra so quebras de linha) nao viram chunk: seria
            # evidencia-lixo que "documenta" a familia sem conteudo real.
            if segment.strip():
                chunks.append(Chunk(doc_family, source, f"parte {i // max_chars + 1}", segment))
        return chunks
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            chunks.append(Chunk(doc_family, source, f"{m.group(1)}. {m.group(2).strip()}", body[:max_chars]))
    return chunks


def chunk_pdf(path: str, doc_family: str) -> list[Chunk]:
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    source = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return chunk_text(text, doc_family=doc_family, source=source)


def chunk_file(path: str, doc_family: str) -> list[Chunk]:
    """Dispatch chunking by file extension.

    `.pdf` uses chunk_pdf (pypdf text extraction). `.md`/`.txt` read the file
    as utf-8 plain text and reuse chunk_text — used for documents that were
    manually transcribed because the source PDF has no extractable text layer
    (e.g. scanned/rasterized PDFs).
    """
    lower = path.lower()
    if lower.endswith(".pdf"):
        return chunk_pdf(path, doc_family)
    if lower.endswith(".md") or lower.endswith(".txt"):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        source = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return chunk_text(text, doc_family=doc_family, source=source)
    raise ValueError(f"unsupported file extension for chunk_file: {path!r}")
