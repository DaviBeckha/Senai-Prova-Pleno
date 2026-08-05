"""Valores de recuperacao: o que foi buscado, com que score, e sob que rotulo.

O `evidence_id` existe para que a resposta gerada possa apontar para um trecho
especifico em vez de citar "o documento" em bloco — e o gancho que o Plano 3
usa para validar cada afirmacao contra a evidencia que a sustenta.
"""

from dataclasses import dataclass

from app.rag.chunking import Chunk


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    family: str
    chunk: Chunk
    # None no modo COMPLETE: os trechos vem em ordem documental, nao por
    # similaridade, entao nao ha score a exibir.
    score: float | None


@dataclass(frozen=True)
class FamilyEvidence:
    family: str
    items: tuple[EvidenceItem, ...]
    complete: bool
    omitted_chunks: int = 0


@dataclass(frozen=True)
class RetrievalBundle:
    families: tuple[FamilyEvidence, ...]
    limitations: tuple[str, ...] = ()

    @property
    def items(self) -> tuple[EvidenceItem, ...]:
        return tuple(
            item
            for family_evidence in self.families
            for item in family_evidence.items
        )

    @property
    def has_evidence(self) -> bool:
        return bool(self.items)
