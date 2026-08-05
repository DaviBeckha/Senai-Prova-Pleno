"""Monta a evidencia que sustenta uma resposta, com identificador e limite.

Dois modos, escolhidos pela QueryScope da pergunta:

- FOCUSED: busca por similaridade, k trechos por familia, corte em min_score.
- COMPLETE: trechos em ordem documental ate um teto de caracteres. Quando o
  teto corta o documento, o bundle carrega uma limitacao explicita — pedir "o
  procedimento completo" e receber metade sem aviso e pior que receber metade
  sabendo que e metade.
"""

from app.chat.types import QueryScope
from app.rag.search import (
    EvidenceItem,
    FamilyEvidence,
    RetrievalBundle,
)


def _focused_family(index, question, family, k, min_score):
    hits = index.search(
        question,
        doc_family=family,
        k=k,
        min_score=min_score,
    )
    items = tuple(
        EvidenceItem(
            f"{family}:E{position}",
            family,
            hit.chunk,
            hit.score,
        )
        for position, hit in enumerate(hits, start=1)
    )
    # complete=False: busca focada nunca representa o documento inteiro.
    return FamilyEvidence(family, items, complete=False)


def _complete_family(index, family, max_chars):
    selected = []
    used_chars = 0
    chunks = index.chunks_for_family(family)
    for chunk in chunks:
        # `selected and ...`: o primeiro trecho entra mesmo se sozinho ja
        # estourar o teto, senao uma familia de trecho unico e grande
        # devolveria evidencia vazia.
        if selected and used_chars + len(chunk.text) > max_chars:
            break
        selected.append(chunk)
        used_chars += len(chunk.text)
    items = tuple(
        EvidenceItem(
            f"{family}:E{position}",
            family,
            chunk,
            None,
        )
        for position, chunk in enumerate(selected, start=1)
    )
    omitted = len(chunks) - len(selected)
    return FamilyEvidence(
        family,
        items,
        complete=omitted == 0,
        omitted_chunks=omitted,
    )


def retrieve_evidence(
    index,
    question: str,
    families: tuple[str, ...],
    scope: QueryScope,
    *,
    k: int,
    min_score: float,
    complete_max_chars: int,
) -> RetrievalBundle:
    if scope is QueryScope.COMPLETE:
        evidence = tuple(
            _complete_family(index, family, complete_max_chars)
            for family in families
        )
    else:
        evidence = tuple(
            _focused_family(index, question, family, k, min_score)
            for family in families
        )
    limitations = tuple(
        (
            f"A evidência de {item.family} omitiu {item.omitted_chunks} trechos "
            "e não representa o documento completo."
        )
        for item in evidence
        if not item.complete and item.omitted_chunks
    )
    return RetrievalBundle(evidence, limitations)
