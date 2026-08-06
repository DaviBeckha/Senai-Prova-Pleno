from dataclasses import dataclass, field

import pandas as pd

from app.chat.analyzer import analyze_question
from app.chat.context import ChatContext
from app.chat.responses import (
    clarification_report,
    document_status_report,
    explanation_report,
    history_report,
    out_of_scope_report,
    state_report,
    undocumented_report,
)
from app.chat.types import ChatIntent, ChatReport
from app.data.labels import display_label
from app.guardrails.policy import decide
from app.guardrails.request_policy import RequestOutcome, inspect_request
from app.guardrails.safety import (
    SAFETY_ADVISORY,
    SafetyOutcome,
    assess_question_safety,
    safety_evidence_limitation,
)
from app.llm.base import DiagnosisContext
from app.llm.adequacy import validate_evidence_adequacy
from app.llm.router import Router
from app.rag.retrieval import retrieve_evidence
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
MSG_DIAGNOSTICO_INCONCLUSIVO = (
    "O kNN encontrou empate entre as famílias {families}. "
    "O diagnóstico foi retido para não apresentar uma conclusão arbitrária."
)

@dataclass
class DiagnosisReport:
    status: str
    family: str | None
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
    # neighbor_count e uma grandeza DIFERENTE de total_ocorrencias: e quantos
    # vizinhos a query kNN desta requisicao de fato consultou (len de
    # result.neighbor_ids, k=50 clampado ao tamanho do historico), nao o
    # total historico da familia vencedora. Sem default proposital: os quatro
    # retornos de diagnose() sempre preenchem com o valor real da query —
    # um construtor futuro que esquecer o campo deve quebrar em vez de
    # herdar silenciosamente um 0 incorreto.
    neighbor_count: int
    # Janela historica da familia vencedora. occurrence_stats ja calculava os
    # tres desde sempre (app/similarity/stats.py) e o relatorio descartava:
    # so total e freq_per_day chegavam ao cliente. Sem eles a tela informa a
    # media diaria sem dizer sobre qual periodo ela foi medida — 1.499,88/dia
    # significa coisas diferentes em 8 ou em 47 dias.
    first_seen: str = ""
    last_seen: str = ""
    per_day: dict[str, int] = field(default_factory=dict)
    # Por que a geracao foi rejeitada pela validacao de fundamentacao.
    # answer_question ja propagava outcome.validation_errors; diagnose()
    # descartava, e o campo nem existia aqui. Sem ele, as respostas que caem em
    # template extrativo — 43,75% das geracoes numa avaliacao local do modo
    # offline — chegam a tela indistinguiveis de uma geracao aceita.
    validation_errors: list[str] = field(default_factory=list)
    candidate_families: list[str] = field(default_factory=list)
    top_vote_share: float = 0.0
    vote_margin: int = 0


class PrescriptivePipeline:
    def __init__(self, engine: SimilarityEngine, df: pd.DataFrame,
                 registry, index, router: Router,
                 routers: dict[str, "Router"] | None = None,
                 *,
                 rag_k: int = 4,
                 rag_min_score: float = 0.82,
                 rag_complete_max_chars: int = 12_000) -> None:
        self._engine = engine
        self._df = df
        self._registry = registry
        self._index = index
        self._router = router
        self._routers = routers
        # Injetados pelo bootstrap a partir de Settings; os defaults existem
        # para que testes e chamadores diretos nao precisem passa-los.
        self._rag_k = rag_k
        self._rag_min_score = rag_min_score
        self._rag_complete_max_chars = rag_complete_max_chars

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
        result_metadata = {
            "candidate_families": list(result.candidate_families),
            "top_vote_share": result.top_vote_share,
            "vote_margin": result.vote_margin,
        }
        if decision.outcome == "inconclusivo":
            return DiagnosisReport(
                status="diagnostico_inconclusivo",
                family=None,
                message=MSG_DIAGNOSTICO_INCONCLUSIVO.format(
                    families=", ".join(decision.candidate_families)
                ),
                total_ocorrencias=0,
                freq_per_day=0.0,
                sources=[],
                renderer=None,
                degraded=False,
                family_votes=result.family_votes,
                neighbor_count=len(result.neighbor_ids),
                **result_metadata,
            )

        assert decision.family is not None
        stats = occurrence_stats(self._df, decision.family)

        # Os campos comuns aos quatro desfechos ficam em um dict nomeado: com
        # 14 campos no relatorio, a construcao posicional deixaria de ser
        # legivel e um campo novo no meio da lista silenciosamente deslocaria
        # os seguintes.
        def _report(status: str, message: str, *,
                    sources: list[str] | None = None,
                    renderer: str | None = None,
                    degraded: bool = False,
                    validation_errors: tuple[str, ...] | list[str] = ()) -> DiagnosisReport:
            return DiagnosisReport(
                status=status,
                family=decision.family,
                message=message,
                total_ocorrencias=stats.total,
                freq_per_day=stats.freq_per_day,
                sources=sources or [],
                renderer=renderer,
                degraded=degraded,
                family_votes=result.family_votes,
                neighbor_count=len(result.neighbor_ids),
                first_seen=stats.first_seen,
                last_seen=stats.last_seen,
                per_day=stats.per_day,
                validation_errors=list(validation_errors),
                **result_metadata,
            )

        if decision.outcome == "estado":
            return _report("estado", MSG_ESTADO.format(
                family=display_label(decision.family)))
        if decision.outcome == "nao_documentado":
            return _report("sem_documento", MSG_SEM_DOCUMENTO.format(
                family=display_label(decision.family)))

        diagnosis_question = f"como corrigir {decision.family}"
        diagnosis_analysis = analyze_question(diagnosis_question)
        bundle = retrieve_evidence(
            self._index,
            diagnosis_question,
            (decision.family,),
            diagnosis_analysis,
            k=self._rag_k,
            min_score=self._rag_min_score,
            complete_max_chars=self._rag_complete_max_chars,
        )
        chunks = [item.chunk for item in bundle.items]
        if not chunks:
            # Falha documentada, mas o indice nao devolveu nenhum trecho
            # utilizavel: gerar diagnostico aqui seria infundado (sem fonte,
            # sem acoes). Contencao honesta em vez de status "sucesso" vazio;
            # o LLM/router nunca e chamado neste ramo.
            return _report("sem_documento", MSG_SEM_TRECHOS.format(
                family=display_label(decision.family)))
        ctx = DiagnosisContext(decision.family, stats, chunks, event)
        outcome = self._pick_router(mode).render(ctx)
        diagnosis_status = (
            "diagnostico"
            if outcome.answer_status == "answered"
            else outcome.answer_status
        )
        return _report(
            diagnosis_status, f"{SAFETY_ADVISORY}\n\n{outcome.text}",
            sources=sorted({c.source for c in chunks}),
            renderer=outcome.renderer,
            degraded=outcome.degraded,
            validation_errors=outcome.validation_errors,
        )

    def answer_question(self, pergunta: str, mode: str | None = None) -> ChatReport:
        # A intencao e resolvida ANTES de tocar RAG ou LLM: a maioria das
        # perguntas tem desfecho deterministico (sem documento, sintoma
        # ambiguo, fora de dominio, contagem de historico) e gastar uma
        # chamada de modelo nelas so produziria texto plausivel sem fonte.
        # Chat nao roda kNN sobre features de vibracao — nao ha evento de
        # sensor associado — entao ChatReport nao carrega family_votes.
        analysis = analyze_question(pergunta)

        # Politicas do pedido continuam antes de qualquer despacho. Consultas
        # estritamente factuais saem antes do guardrail fisico: palavras como
        # "ajuste" e "troca" podem ser substantivos em uma consulta historica
        # e nao representam uma ordem de intervencao.
        request_policy = inspect_request(pergunta)
        if request_policy.outcome is RequestOutcome.REFUSE_INTERNAL:
            return ChatReport(
                status="refused_internal",
                message=request_policy.message,
                families=analysis.explicit_families,
            )
        if request_policy.outcome is RequestOutcome.REFUSE_UNSAFE:
            return ChatReport(
                status="refused_unsafe",
                message=request_policy.message,
                families=analysis.explicit_families,
            )
        if analysis.intent is ChatIntent.DOCUMENT_STATUS:
            return document_status_report(
                analysis.explicit_families,
                self._registry.has_document,
            )
        if analysis.intent is ChatIntent.STATE:
            return state_report(analysis.explicit_families)
        if analysis.intent is ChatIntent.HISTORY:
            return history_report(
                analysis.explicit_families,
                {
                    family: occurrence_stats(self._df, family)
                    for family in analysis.explicit_families
                },
            )
        if analysis.intent is ChatIntent.EXPLANATION:
            return explanation_report(analysis.explicit_families)

        # Toda intencao procedural usa a mesma taxonomia de acoes do
        # reranking/validador. Com a maquina ligada, a resposta termina aqui e
        # nunca expoe trechos executaveis do indice ou do modelo.
        safety = assess_question_safety(pergunta, analysis.requested_actions)
        if safety.outcome is SafetyOutcome.ADVISE_LIVE_INTERVENTION:
            return ChatReport(
                status="answered",
                message=safety.message,
                families=analysis.explicit_families,
            )

        if analysis.intent is ChatIntent.CLARIFICATION:
            return clarification_report(analysis.candidate_families)
        if analysis.intent is ChatIntent.OUT_OF_SCOPE:
            return out_of_scope_report()
        documented = tuple(
            family
            for family in analysis.explicit_families
            if self._registry.has_document(family)
        )
        undocumented = tuple(
            family
            for family in analysis.explicit_families
            if family not in documented
        )
        if not documented:
            return undocumented_report(undocumented)

        # Pedido adversarial nao e repassado ao modelo: `effective_question`
        # devolve uma formulacao canonica no lugar do texto original.
        effective_question = request_policy.effective_question(documented)
        limitations: list[str] = []
        if request_policy.outcome is RequestOutcome.CONSTRAIN_SOURCES:
            limitations.append(request_policy.message)

        # Uma busca por familia documentada, independentes entre si: a
        # pergunta "correia e polia" produz duas recuperacoes e mantem as
        # fontes separadas, em vez de reduzir a consulta a primeira familia.
        bundle = retrieve_evidence(
            self._index,
            effective_question,
            documented,
            analysis,
            k=self._rag_k,
            min_score=self._rag_min_score,
            complete_max_chars=self._rag_complete_max_chars,
        )
        if not bundle.has_evidence:
            # Mesma contencao honesta do ramo "documentado" de diagnose():
            # familia documentada, mas nenhum trecho atingiu o limiar — o
            # router/LLM nunca e chamado aqui (RF4: nao responder sem fonte).
            return ChatReport(
                "insufficient_evidence",
                (
                    "Reconheci a falha, mas nenhum trecho atingiu o limite mínimo "
                    "de relevância. Não vou gerar uma orientação sem evidência "
                    "suficiente."
                ),
                analysis.explicit_families,
            )

        adequacy_errors = validate_evidence_adequacy(analysis, bundle)
        if adequacy_errors:
            return ChatReport(
                status="insufficient_evidence",
                message=(
                    "Os trechos recuperados não cobrem todas as famílias e "
                    "ações solicitadas. Não vou completar a orientação por "
                    "inferência."
                ),
                families=analysis.explicit_families,
                sources=tuple(sorted({
                    item.chunk.source for item in bundle.items
                })),
                validation_errors=adequacy_errors,
            )

        limitations.extend(bundle.limitations)
        if undocumented:
            limitations.append(
                "Sem documento orientativo: " + ", ".join(undocumented)
            )
        # Uma resposta tecnicamente correta e perigosa se o operador a ler como
        # liberacao para executar. Sem evidencia de parada/bloqueio, isso e dito.
        safety_limitation = safety_evidence_limitation(pergunta, bundle)
        if safety_limitation:
            limitations.append(safety_limitation)
        stats_by_family = {
            family: occurrence_stats(self._df, family)
            for family in documented
        }
        context = ChatContext(
            question=effective_question,
            families=documented,
            stats_by_family=stats_by_family,
            retrieval=bundle,
            limitations=tuple(limitations),
            requested_actions=analysis.requested_actions,
            requires_safety=analysis.requires_safety,
            conditions=analysis.conditions,
            safety_only=analysis.safety_only,
        )
        outcome = self._pick_router(mode).render(context)
        message = outcome.text
        if safety.outcome is SafetyOutcome.ADVISE_INTERVENTION:
            message = f"{safety.message}\n\n{message}"
        return ChatReport(
            status=outcome.answer_status,
            message=message,
            families=analysis.explicit_families,
            sources=tuple(sorted({item.chunk.source for item in bundle.items})),
            renderer=outcome.renderer,
            degraded=outcome.degraded,
            limitations=tuple(limitations),
            validation_errors=outcome.validation_errors,
        )
