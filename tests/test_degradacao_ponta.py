"""Teste de degradacao PONTA A PONTA: POST /eventos com Ollama fora do ar.

Diferenca para tests/test_llm.py (test_router_degrades_to_fallback): aquele
teste exercita Router isoladamente com um BoomRenderer artificial. Este monta
a API inteira (TestClient -> app -> get_state -> PrescriptivePipeline real ->
Router real) com um OllamaRenderer REAL apontando para uma porta sem nada
escutando (http://127.0.0.1:9/) e fallback TemplateRenderer REAL — prova que
a demo sobrevive de fato se o processo do Ollama morrer no meio da
entrevista, nao so que a classe Router sabe degradar em isolamento.

Contrato conferido em app/api/schemas.py antes de escrever este teste:
`DiagnosticoOut` (response_model de `POST /eventos` em app/api/main.py) expõe
`degradado: bool` e `redator: str | None` — nao ha lacuna de contrato aqui.
`ChatOut` (mesmo arquivo, response_model de `POST /chat`) tambem expõe os
dois campos, alem de `status`, `familias`, `limitacoes` e
`erros_de_validacao` — fora do escopo deste teste, que cobre so `/eventos`.
"""

import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.api.main import create_app, get_state
from app.api.state import AppState
from app.data.loader import FEATURE_COLUMNS
from app.llm.ollama_adapter import OllamaRenderer
from app.llm.router import Router
from app.llm.template_fallback import TemplateRenderer
from app.pipeline import PrescriptivePipeline
from app.rag.chunking import Chunk
from app.rag.search import SearchHit
from app.similarity.engine import SimilarityEngine

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"

# Porta sem nenhum servico escutando. O comportamento do SO varia (recusa
# imediata ou espera ate o timeout configurado no OllamaRenderer) — nesta
# maquina, observado na pratica como httpx.ConnectTimeout apos os 2s do
# timeout curto abaixo, nao uma recusa instantanea. Os dois casos terminam
# igual (excecao capturada pelo Router, degradacao para o template), entao o
# teste cobre ambos sem mockar httpx; o timeout curto so existe para nao
# esperar os 300s do default de producao caso a conexao fique presa.
_PORTA_MORTA = "http://127.0.0.1:9/"


class _IndexComEvidenciaCorreia:
    """Indice fake (mesmo contrato de tests/test_pipeline.py): qualquer
    busca por 'correia' devolve um trecho real, sem depender de embeddings.
    """

    def search(self, query, doc_family, k=4, min_score=0.0):
        return [SearchHit(
            Chunk("correia", "Doc4.pdf", "9.1 Correia Frouxa",
                  "1. Afrouxar os parafusos do motor. 2. Ajustar a tensao."),
            0.9,
        )]


class _RegistryCorreiaDocumentada:
    def has_document(self, family):
        return family == "correia"


def _df_correia(n=20) -> pd.DataFrame:
    rows = []
    for i in range(n):
        row = {c: 0.1 for c in FEATURE_COLUMNS}
        row.update(id=i, family="correia", kind="falha",
                   created_at=pd.Timestamp("2026-06-01T00:00:00Z"))
        rows.append(row)
    return pd.DataFrame(rows)


def _pipeline_com_ollama_fora_do_ar() -> PrescriptivePipeline:
    """Pipeline real (SimilarityEngine treinado + guardrails reais) com um
    Router real cujo primario e um OllamaRenderer real apontando para a
    porta morta. timeout curto (2s) para o teste nao esperar os 300s do
    default de producao caso a conexao fique presa em vez de ser recusada.
    """
    df = _df_correia()
    engine = SimilarityEngine()
    engine.fit(df)
    router = Router(
        primary=OllamaRenderer(_PORTA_MORTA, "qwen2.5:7b-instruct", timeout=2.0),
        fallback=TemplateRenderer(),
    )
    return PrescriptivePipeline(
        engine, df, _RegistryCorreiaDocumentada(),
        _IndexComEvidenciaCorreia(), router,
    )


def _evento_correia_demo() -> dict:
    payload = json.loads((DEMO_DIR / "evento_correia.json").read_text(encoding="utf-8"))
    assert set(payload.keys()) == set(FEATURE_COLUMNS)
    return payload


def test_eventos_sobrevive_com_ollama_fora_do_ar():
    # Cenario: o Ollama morre no meio da entrevista. A API precisa continuar
    # respondendo 200, com o diagnostico degradado (somente evidencia crua,
    # sem sintese do modelo) em vez de 500/timeout longo.
    app = create_app(skip_bootstrap=True)
    state = AppState(pipeline=_pipeline_com_ollama_fora_do_ar(),
                     registry=None, index=None, df=None)
    app.dependency_overrides[get_state] = lambda: state
    client = TestClient(app)

    r = client.post("/eventos", json=_evento_correia_demo())

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "diagnostico"
    assert data["familia"] == "correia"
    assert data["rotulo"] == "Correia"
    # Contrato real de DiagnosticoOut: degradado/redator existem e denunciam a
    # degradacao explicitamente — nao e preciso inferir pelo texto.
    assert data["degradado"] is True
    assert data["redator"] == "template"
    # Alem do marcador, o efeito observavel: orientacao organizada pelo
    # template deterministico, nao uma sintese de LLM. A fonte fica no campo
    # auditavel em vez de poluir o texto principal.
    assert "Orientação encontrada para Correia" in data["mensagem"]
    assert "Doc4.pdf" not in data["mensagem"]
    assert "Afrouxar os parafusos do motor" in data["mensagem"]
    assert data["fontes"] == ["Doc4.pdf"]
