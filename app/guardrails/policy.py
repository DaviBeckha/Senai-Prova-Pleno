from dataclasses import dataclass
from typing import Callable

from app.similarity.engine import SimilarityResult


@dataclass
class Decision:
    outcome: str
    family: str


def decide(result: SimilarityResult, has_document: Callable[[str], bool]) -> Decision:
    if result.dominant_kind == "estado":
        return Decision(outcome="estado", family=result.dominant_family)
    if result.dominant_kind == "falha" and has_document(result.dominant_family):
        return Decision(outcome="documentado", family=result.dominant_family)
    return Decision(outcome="nao_documentado", family=result.dominant_family)
