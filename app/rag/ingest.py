from app.rag.chunking import chunk_file
from app.rag.family_sections import filter_chunks_for_family
from app.rag.index import VectorIndex


def ingest_pdf(path: str, doc_family: str, index: VectorIndex) -> int:
    """Ingest a source document (PDF, or .md/.txt transcript) into the index.

    Name kept as ingest_pdf for backward compatibility; dispatch by extension
    now happens in chunk_file, so this also accepts .md/.txt transcripts
    (e.g. docs_fontes/doc1_rolamentos.md for PDFs with no extractable text
    layer).
    """
    raw_chunks = chunk_file(path, doc_family)
    # doc1_rolamentos.md e ingerido uma vez por subtipo de rolamento (ver
    # PDF_MAP em scripts/bootstrap.py): o filtro e o que impede a familia
    # `rolamento_inner` de indexar o diagnostico de elementos rolantes.
    chunks = filter_chunks_for_family(raw_chunks, doc_family)
    index.add(chunks)
    return len(chunks)
