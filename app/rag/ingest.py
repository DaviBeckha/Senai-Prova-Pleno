from app.rag.chunking import chunk_file
from app.rag.index import VectorIndex


def ingest_pdf(path: str, doc_family: str, index: VectorIndex) -> int:
    """Ingest a source document (PDF, or .md/.txt transcript) into the index.

    Name kept as ingest_pdf for backward compatibility; dispatch by extension
    now happens in chunk_file, so this also accepts .md/.txt transcripts
    (e.g. docs_fontes/doc1_rolamentos.md for PDFs with no extractable text
    layer).
    """
    chunks = chunk_file(path, doc_family)
    index.add(chunks)
    return len(chunks)
