from dataclasses import dataclass

from app.rag.search import RetrievalBundle
from app.similarity.stats import OccurrenceStats


@dataclass(frozen=True)
class ChatContext:
    """Contexto de uma resposta de chat: pode cobrir mais de uma familia.

    Difere do DiagnosisContext (caminho /eventos) em tres pontos: carrega a
    pergunta em linguagem natural, carrega N familias em vez de uma, e carrega
    evidencia identificada (RetrievalBundle) em vez de uma lista anonima de
    trechos — para que cada afirmacao da resposta possa apontar a fonte.
    """

    question: str
    families: tuple[str, ...]
    stats_by_family: dict[str, OccurrenceStats]
    retrieval: RetrievalBundle
    limitations: tuple[str, ...] = ()
