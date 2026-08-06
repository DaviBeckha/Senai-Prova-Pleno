from dataclasses import dataclass
from typing import Callable

from app.similarity.engine import SimilarityResult


@dataclass
class Decision:
    outcome: str
    family: str | None
    candidate_families: tuple[str, ...] = ()


def decide(result: SimilarityResult, has_document: Callable[[str], bool]) -> Decision:
    if result.is_ambiguous:
        return Decision(
            outcome="inconclusivo",
            family=None,
            candidate_families=result.candidate_families,
        )
    if result.dominant_kind == "estado":
        return Decision(outcome="estado", family=result.dominant_family)
    if result.dominant_kind == "falha" and has_document(result.dominant_family):
        return Decision(outcome="documentado", family=result.dominant_family)
    return Decision(outcome="nao_documentado", family=result.dominant_family)
