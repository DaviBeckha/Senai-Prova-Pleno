import json

import pandas as pd
from app.data.loader import FEATURE_COLUMNS
from app.llm.router import Router
from app.llm.template_fallback import TemplateRenderer
from app.pipeline import PrescriptivePipeline
from app.rag.chunking import Chunk
from app.rag.search import SearchHit
from app.similarity.engine import SimilarityEngine


class FakeIndex:
    # Contrato atual de VectorIndex.search (app/rag/index.py): aceita
    # min_score (kwarg) e devolve list[SearchHit], nao list[Chunk] cru —
    # pipeline.py e retrieval.py acessam hit.chunk/hit.score.
    def search(self, query, doc_family, k=4, min_score=0.0):
        return [SearchHit(Chunk(doc_family, "Doc4.pdf", "9.1", "ajustar tensao"), 0.9)]


class EmptyIndex:
    """Indice documentado mas sem nenhum trecho recuperavel (ex.: reindexacao pendente)."""

    def search(self, query, doc_family, k=4, min_score=0.0):
        return []


class RaisingIndex:
    """Trava estruturalmente que o retrieval nao e tocado nos ramos estado/sem_documento."""

    def search(self, query, doc_family, k=4, min_score=0.0):
        raise RuntimeError("index.search nao deveria ser chamado neste ramo")


class RaisingRouter:
    """Trava estruturalmente que o LLM/router nao e tocado nos ramos estado/sem_documento."""

    def render(self, ctx):
        raise RuntimeError("router.render nao deveria ser chamado neste ramo")


class FakeNamedRenderer:
    """Renderer nomeado usado para provar qual Router foi escolhido por mode.

    Contrato atual (app/llm/router.py): Router.render() SEMPRE tenta fazer
    parse do texto do primary como GroundedDraft JSON e valida a
    fundamentacao (app/llm/grounding.py) antes de aceitar o renderer primario
    — texto livre nao-JSON degrada incondicionalmente para o fallback. Para
    provar selecao de router por "quem respondeu" e preciso devolver um
    rascunho valido (evidence_id/quote que batem com o chunk que o FakeIndex
    devolve: family="correia", texto "ajustar tensao").
    """

    def __init__(self, name):
        self.name = name

    def render(self, ctx):
        return json.dumps({
            "steps": [{
                "action": "ajustar tensao",
                "family": ctx.family,
                "evidence_id": f"{ctx.family}:E1",
                "quote": "ajustar tensao",
            }],
            "unanswered": [],
        })


class FakeRegistry:
    def has_document(self, family):
        return family == "correia"


class AllDocumentedRegistry:
    def has_document(self, family):
        return True


def _df(family, kind, n=20):
    rows = []
    for i in range(n):
        r = {c: 0.1 for c in FEATURE_COLUMNS}
        r.update(id=i, family=family, kind=kind,
                 created_at=pd.Timestamp("2026-06-01T00:00:00Z"))
        rows.append(r)
    return pd.DataFrame(rows)


def _pipeline(df, registry=None, index=None, router=None, routers=None):
    eng = SimilarityEngine()
    eng.fit(df)
    if registry is None:
        registry = FakeRegistry()
    if index is None:
        index = FakeIndex()
    if router is None:
        router = Router(primary=TemplateRenderer(), fallback=TemplateRenderer())
    return PrescriptivePipeline(eng, df, registry, index, router, routers=routers)


def _event():
    return {c: 0.1 for c in FEATURE_COLUMNS}


def test_falha_documentada_gera_diagnostico():
    rep = _pipeline(_df("correia", "falha")).diagnose(_event())
    assert rep.status == "diagnostico"
    assert rep.total_ocorrencias == 20
    assert rep.sources == ["Doc4.pdf"]
    assert "correia" in rep.family_votes
    assert rep.family_votes["correia"] == 20


def test_falha_sem_documento_nao_chama_llm():
    # RaisingIndex/RaisingRouter travam estruturalmente que nem o retrieval
    # nem o LLM sao tocados quando o guardrail ja decide "nao_documentado".
    rep = _pipeline(
        _df("ventoinha", "falha"),
        index=RaisingIndex(), router=RaisingRouter(),
    ).diagnose(_event())
    assert rep.status == "sem_documento"
    assert "Registre um novo documento" in rep.message
    assert rep.renderer is None
    assert "ventoinha" in rep.family_votes


def test_estado_retorna_sem_diagnostico():
    # Idem: em "estado" o guardrail decide antes de qualquer retrieval/LLM.
    rep = _pipeline(
        _df("normal", "estado"),
        index=RaisingIndex(), router=RaisingRouter(),
    ).diagnose(_event())
    assert rep.status == "estado"
    assert "normal" in rep.family_votes


def test_falha_documentada_sem_trechos_retorna_sem_documento_sem_chamar_llm():
    # Falha documentada, mas o indice nao devolve nenhum trecho utilizavel:
    # contencao honesta (sem_documento) em vez de "diagnostico" infundado;
    # RaisingRouter trava que o LLM nunca e chamado neste ramo.
    rep = _pipeline(
        _df("correia", "falha"),
        registry=AllDocumentedRegistry(),
        index=EmptyIndex(),
        router=RaisingRouter(),
    ).diagnose(_event())
    assert rep.status == "sem_documento"
    assert "nenhum trecho utilizável" in rep.message
    assert rep.renderer is None
    assert rep.sources == []
    assert rep.degraded is False
    assert rep.total_ocorrencias == 20
    assert "correia" in rep.family_votes


def test_chat_familia_documentada_gera_diagnostico():
    # pergunta cita uma familia de falha documentada (FakeRegistry: apenas
    # "correia") e o indice (FakeIndex) devolve um trecho utilizavel.
    # Contrato atual: o desfecho de sucesso de answer_question() e status
    # "answered" (nao "diagnostico" — esse status e exclusivo de diagnose()),
    # e ChatReport.sources e tuple[str, ...], nao list. ChatReport tambem nao
    # carrega family_votes (so DiagnosisReport carrega: chat nao roda kNN
    # sobre features de vibracao, ver docstring de PrescriptivePipeline).
    rep = _pipeline(_df("correia", "falha")).answer_question(
        "como corrigir correia frouxa?")
    assert rep.status == "answered"
    assert rep.sources == ("Doc4.pdf",)


def test_chat_familia_fora_do_dominio_nao_chama_router():
    # Nenhum token da pergunta bate com uma familia de falha conhecida nem
    # com um sintoma cadastrado (analyze_question): intent vira OUT_OF_SCOPE
    # e o metodo retorna via out_of_scope_report() antes de tocar
    # index/router. RaisingRouter trava estruturalmente essa garantia.
    # Contrato atual distingue "fora de escopo" (nada reconhecido, status
    # out_of_scope) de "nao documentado" (familia reconhecida sem doc,
    # status sem_documento) — ver app/chat/responses.py.
    rep = _pipeline(
        _df("correia", "falha"), router=RaisingRouter(),
    ).answer_question("problema na fase eletrica")
    assert rep.status == "out_of_scope"
    assert "Consigo responder somente sobre falhas" in rep.message


def test_chat_pergunta_generica_sem_familia_retorna_out_of_scope():
    # Idem: sem familia e sem sintoma reconhecido, o desfecho e out_of_scope.
    rep = _pipeline(_df("correia", "falha")).answer_question("o que fazer?")
    assert rep.status == "out_of_scope"


def test_chat_familia_documentada_sem_trechos_nao_chama_router():
    # Familia documentada (AllDocumentedRegistry), mas o indice nao devolve
    # nenhum trecho utilizavel (EmptyIndex): contencao honesta; RaisingRouter
    # prova que o router/LLM nunca e chamado neste ramo do chat (RF4).
    # Contrato atual: no chat esse desfecho e status "insufficient_evidence"
    # (nao "sem_documento" — esse e reservado a familia sem documento
    # cadastrado; aqui a familia TEM documento, so nao ha trecho acima do
    # limiar). ChatReport.sources e tuple, nao list, e ChatReport nao carrega
    # family_votes (exclusivo de DiagnosisReport).
    rep = _pipeline(
        _df("correia", "falha"),
        registry=AllDocumentedRegistry(),
        index=EmptyIndex(),
        router=RaisingRouter(),
    ).answer_question("como corrigir correia?")
    assert rep.status == "insufficient_evidence"
    assert "nenhum trecho atingiu o limite mínimo" in rep.message
    assert rep.renderer is None
    assert rep.sources == ()
    assert rep.degraded is False


def test_mode_seleciona_router():
    # RF: selecao de router POR REQUISICAO (kwarg mode), com fallback para
    # o router default (bootstrap via LLM_MODE) quando mode e None ou
    # nao existe em self._routers.
    evento_documentado = _df("correia", "falha")
    routers = {"online": Router(FakeNamedRenderer("fake_online"), TemplateRenderer())}
    pipeline = _pipeline(evento_documentado, routers=routers)

    rep_online = pipeline.diagnose(_event(), mode="online")
    assert rep_online.renderer == "fake_online"

    rep_default = pipeline.diagnose(_event(), mode=None)
    assert rep_default.renderer == "template"

    rep_inexistente = pipeline.diagnose(_event(), mode="inexistente")
    assert rep_inexistente.renderer == "template"
