"""Recupera e compõe evidências por intenção, segurança e validação."""

from app.chat.types import QueryScope, QuestionAnalysis
from app.core.maintenance_intent import (
    ContentRole,
    is_intervention_action,
)
from app.rag.reranking import rerank_hits, select_procedure_hits
from app.rag.search import EvidenceItem, FamilyEvidence, RetrievalBundle, SearchHit


def _document_hits(index, family: str, analysis: QuestionAnalysis) -> list[SearchHit]:
    if not hasattr(index, "chunks_for_family"):
        return []
    hits = [
        SearchHit(chunk, 0.0)
        for chunk in index.chunks_for_family(family)
    ]
    return rerank_hits(hits, analysis)


def _role_block(
    hits: list[SearchHit],
    role: ContentRole,
) -> list[SearchHit]:
    candidates = [hit for hit in hits if hit.chunk.content_role == role]
    if not candidates:
        return []
    anchor = min(candidates, key=lambda hit: hit.chunk.document_order)
    block_key = (
        anchor.chunk.source,
        anchor.chunk.section,
        anchor.chunk.section_path,
    )
    return sorted(
        (
            hit
            for hit in candidates
            if (
                hit.chunk.source,
                hit.chunk.section,
                hit.chunk.section_path,
            ) == block_key
        ),
        key=lambda hit: hit.chunk.document_order,
    )


def _deduplicate(hits: list[SearchHit]) -> list[SearchHit]:
    selected: list[SearchHit] = []
    seen: set[tuple[str, int, str]] = set()
    for hit in hits:
        key = (
            hit.chunk.source,
            hit.chunk.document_order,
            hit.chunk.section,
        )
        if key not in seen:
            selected.append(hit)
            seen.add(key)
    return selected


def _limit_complete(
    hits: list[SearchHit],
    max_chars: int,
) -> tuple[list[SearchHit], int]:
    if max_chars <= 0:
        return [], len(hits)
    selected: list[SearchHit] = []
    used_chars = 0
    for hit in hits:
        size = len(hit.chunk.text)
        if used_chars + size > max_chars:
            break
        selected.append(hit)
        used_chars += size
    return selected, len(hits) - len(selected)


def _retrieve_family(
    index,
    question: str,
    family: str,
    analysis: QuestionAnalysis,
    *,
    k: int,
    min_score: float,
    complete_max_chars: int,
) -> FamilyEvidence:
    candidate_k = max(k * 3, 12)
    vector_hits = index.search(
        question,
        doc_family=family,
        k=candidate_k,
        min_score=min_score,
    )
    document_hits = _document_hits(index, family, analysis)
    complete = analysis.scope is QueryScope.COMPLETE
    procedure_candidates = document_hits if complete and document_hits else vector_hits
    procedure = select_procedure_hits(
        procedure_candidates,
        analysis,
        k=k,
        complete=complete,
    )

    intervention = any(
        is_intervention_action(action)
        for action in analysis.requested_actions
    )
    safety = (
        _role_block(document_hits, ContentRole.SAFETY)
        if analysis.requires_safety or intervention
        else []
    )
    validation = (
        _role_block(document_hits, ContentRole.VALIDATION)
        if intervention
        else []
    )

    omitted = 0
    if complete:
        mandatory_chars = sum(
            len(hit.chunk.text)
            for hit in (*safety, *validation)
        )
        if mandatory_chars > complete_max_chars:
            # Segurança e validação são indivisíveis em um procedimento
            # completo. Se nem o bloco obrigatório cabe no orçamento, é mais
            # seguro declarar evidência insuficiente do que truncá-lo.
            return FamilyEvidence(
                family,
                (),
                complete=False,
                omitted_chunks=len(
                    _deduplicate([*safety, *procedure, *validation])
                ),
            )
        procedure, omitted = _limit_complete(
            procedure,
            complete_max_chars - mandatory_chars,
        )
    composed = _deduplicate([*safety, *procedure, *validation])
    items = tuple(
        EvidenceItem(
            f"{family}:E{position}",
            family,
            hit.chunk,
            hit.score,
        )
        for position, hit in enumerate(composed, start=1)
    )
    return FamilyEvidence(
        family,
        items,
        complete=complete and omitted == 0,
        omitted_chunks=omitted,
    )


def retrieve_evidence(
    index,
    question: str,
    families: tuple[str, ...],
    analysis: QuestionAnalysis,
    *,
    k: int,
    min_score: float,
    complete_max_chars: int,
) -> RetrievalBundle:
    evidence = tuple(
        _retrieve_family(
            index,
            question,
            family,
            analysis,
            k=k,
            min_score=min_score,
            complete_max_chars=complete_max_chars,
        )
        for family in families
    )
    limitations = tuple(
        (
            f"A evidência de {item.family} omitiu {item.omitted_chunks} trechos "
            "e não representa o procedimento completo."
        )
        for item in evidence
        if item.omitted_chunks
    )
    return RetrievalBundle(evidence, limitations)
