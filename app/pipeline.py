from dataclasses import dataclass

import pandas as pd

from app.guardrails.policy import decide
from app.llm.base import DiagnosisContext
from app.llm.router import Router
from app.similarity.engine import SimilarityEngine
from app.similarity.stats import occurrence_stats

MSG_SEM_DOCUMENTO = (
    "Problema identificado como '{family}', porém ainda não existe documento "
    "orientativo cadastrado para ele. Registre um novo documento para habilitar "
    "as recomendações."
)
MSG_ESTADO = (
    "Evento classificado como estado de operação '{family}' — nenhuma falha "
    "identificada."
)
MSG_SEM_TRECHOS = (
    "Problema identificado como '{family}' e há documento cadastrado, porém "
    "nenhum trecho utilizável foi recuperado do índice. Reindexe o documento "
    "ou registre um novo para habilitar as recomendações."
)
# Usada em answer_question quando nenhuma familia de falha documentada foi
# reconhecida na pergunta (MSG_SEM_DOCUMENTO nao se aplica: exige um {family}
# concreto, que nao existe nesse ramo do chat).
MSG_CHAT_SEM_FAMILIA = (
    "Não identifiquei na pergunta nenhuma falha com documento orientativo "
    "cadastrado. Especifique o problema (ex.: correia, polia, "
    "desbalanceamento) ou registre um novo documento para o defeito."
)


@dataclass
class DiagnosisReport:
    status: str
    family: str
    message: str
    total_ocorrencias: int
    freq_per_day: float
    sources: list[str]
    renderer: str | None
    degraded: bool
    # family_votes existe para expor a incerteza do voto kNN: a distribuicao
    # completa de votos k=50 da SimilarityEngine, em vez de so o rotulo
    # vencedor. Familias se sobrepoem no espaco de features — o voto
    # majoritario concorda com a familia real da propria linha em ~46%.
    # Sempre preenchido apos uma query (nunca {}).
    family_votes: dict[str, int]


class PrescriptivePipeline:
    def __init__(self, engine: SimilarityEngine, df: pd.DataFrame,
                 registry, index, router: Router,
                 routers: dict[str, "Router"] | None = None) -> None:
        self._engine = engine
        self._df = df
        self._registry = registry
        self._index = index
        self._router = router
        self._routers = routers

    def _pick_router(self, mode: str | None) -> Router:
        # Selecao de router POR REQUISICAO: mode explicito e presente em
        # self._routers usa o router daquele modo; caso contrario cai no
        # router default (bootstrap via LLM_MODE), sem quebrar chamadores
        # que nao passam mode explicitamente.
        if mode and self._routers and mode in self._routers:
            return self._routers[mode]
        return self._router

    def diagnose(self, event: dict, mode: str | None = None) -> DiagnosisReport:
        result = self._engine.query(event)
        decision = decide(result, self._registry.has_document)
        stats = occurrence_stats(self._df, decision.family)

        if decision.outcome == "estado":
            return DiagnosisReport(
                "estado", decision.family,
                MSG_ESTADO.format(family=decision.family),
                stats.total, stats.freq_per_day, [], None, False,
                result.family_votes)
        if decision.outcome == "nao_documentado":
            return DiagnosisReport(
                "sem_documento", decision.family,
                MSG_SEM_DOCUMENTO.format(family=decision.family),
                stats.total, stats.freq_per_day, [], None, False,
                result.family_votes)

        chunks = self._index.search(f"como corrigir {decision.family}",
                                    doc_family=decision.family)
        if not chunks:
            # Falha documentada, mas o indice nao devolveu nenhum trecho
            # utilizavel: gerar diagnostico aqui seria infundado (sem fonte,
            # sem acoes). Contencao honesta em vez de status "sucesso" vazio;
            # o LLM/router nunca e chamado neste ramo.
            return DiagnosisReport(
                "sem_documento", decision.family,
                MSG_SEM_TRECHOS.format(family=decision.family),
                stats.total, stats.freq_per_day, [], None, False,
                result.family_votes)
        ctx = DiagnosisContext(decision.family, stats, chunks, event)
        outcome = self._pick_router(mode).render(ctx)
        return DiagnosisReport(
            "diagnostico", decision.family, outcome.text, stats.total,
            stats.freq_per_day, sorted({c.source for c in chunks}),
            outcome.renderer, outcome.degraded, result.family_votes)

    def answer_question(self, pergunta: str, mode: str | None = None) -> DiagnosisReport:
        # Pergunta de chat: nao roda kNN sobre features de vibracao (nao ha
        # evento de sensor associado), entao family_votes fica sempre {} aqui
        # (distinto de diagnose(), que sempre preenche a partir da SimilarityEngine).
        from app.data.labels import normalize_label
        tokens = pergunta.lower().replace("?", " ").split()
        family = None
        for token in tokens:
            info = normalize_label(token)
            if info.kind == "falha" and self._registry.has_document(info.family):
                family = info.family
                break
        if family is None:
            return DiagnosisReport(
                "sem_documento", "desconhecido", MSG_CHAT_SEM_FAMILIA,
                0, 0.0, [], None, False, {})
        stats = occurrence_stats(self._df, family)
        chunks = self._index.search(pergunta, doc_family=family)
        if not chunks:
            # Mesma contencao honesta do ramo "documentado" de diagnose():
            # familia documentada, mas sem trecho recuperavel — o router/LLM
            # nunca e chamado aqui (RF4: nao gerar resposta sem fonte).
            return DiagnosisReport(
                "sem_documento", family, MSG_SEM_TRECHOS.format(family=family),
                stats.total, stats.freq_per_day, [], None, False, {})
        ctx = DiagnosisContext(family, stats, chunks, {})
        outcome = self._pick_router(mode).render(ctx)
        return DiagnosisReport("diagnostico", family, outcome.text, stats.total,
                               stats.freq_per_day,
                               sorted({c.source for c in chunks}),
                               outcome.renderer, outcome.degraded, {})
