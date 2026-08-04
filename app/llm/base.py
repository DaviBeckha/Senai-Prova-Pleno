from dataclasses import dataclass
from typing import Protocol

from app.rag.chunking import Chunk
from app.similarity.stats import OccurrenceStats


@dataclass
class DiagnosisContext:
    family: str
    stats: OccurrenceStats
    chunks: list[Chunk]
    event: dict


class Renderer(Protocol):
    name: str

    def render(self, ctx: DiagnosisContext) -> str: ...


PROMPT_SISTEMA = (
    "Voce e um assistente de manutencao industrial. Responda em portugues, "
    "APENAS com base nos trechos de procedimento fornecidos. Estruture: "
    "1) Defeito identificado; 2) Historico (ocorrencias, frequencia); "
    "3) Acoes de correcao (cite a secao do documento); 4) Fonte. "
    "Nunca invente procedimentos que nao estejam nos trechos."
)


def build_user_prompt(ctx: DiagnosisContext) -> str:
    trechos = "\n\n".join(
        f"[{c.source} — secao {c.section}]\n{c.text}" for c in ctx.chunks)
    return (
        f"Defeito: {ctx.family}\n"
        f"Ocorrencias similares no historico: {ctx.stats.total}\n"
        f"Frequencia: {ctx.stats.freq_per_day} por dia "
        f"(de {ctx.stats.first_seen[:10]} a {ctx.stats.last_seen[:10]})\n"
        f"Evento atual: {ctx.event}\n\n"
        f"Trechos dos procedimentos:\n{trechos}"
    )
