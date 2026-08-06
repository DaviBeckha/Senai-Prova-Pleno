"""O dashboard contra a API real, sem stub de resposta no meio.

Os testes de tests/test_dashboard_paginas.py usam dicionarios escritos a mao. Se
o backend renomear um campo, aqueles dicionarios continuam com o nome antigo e
passam — o acoplamento nao seria pego.

Aqui o caminho e o real: FastAPI de verdade -> schemas de verdade -> JSON de
verdade -> dashboard/api.py -> paginas. O httpx do cliente do dashboard e
redirecionado para o TestClient, entao a serializacao exercitada e a de
app/api/schemas.py, nao uma copia.

E o que este arquivo protege, agora que o dashboard e cliente puro da API: um
campo renomeado no backend quebra aqui, na hora, em vez de aparecer como
KeyError na tela em producao.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app, get_state
from app.api.state import AppState
from app.chat.types import ChatReport
from app.data.loader import FEATURE_COLUMNS
from app.pipeline import DiagnosisReport

_DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"
# APPEND, nunca insert(0) — ver a nota em tests/test_dashboard_paginas.py:
# dashboard/app.py sombrearia o pacote app/ se viesse antes da raiz do projeto.
if str(_DASHBOARD) not in sys.path:
    sys.path.append(str(_DASHBOARD))

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


class PipelineComEmpate:
    """Reproduz o desfecho medido na avaliacao local do modo offline.

    correia venceu com 9 de 50 votos, empatada com rolamento_outer e
    rolamento_ball, e a geracao foi rejeitada pelo grounding (degradado, com o
    motivo em erros_de_validacao). E o caso que a tela precisa qualificar em vez
    de apresentar como conclusao.
    """

    def diagnose(self, event, mode=None):
        return DiagnosisReport(
            status="diagnostico", family="correia",
            message="Ajustar a tensão da correia até a deflexão especificada.",
            total_ocorrencias=11999, freq_per_day=1499.88, sources=["Doc4.pdf"],
            renderer="template", degraded=True,
            family_votes={"correia": 9, "rolamento_outer": 9,
                          "rolamento_ball": 9, "rolamento_inner": 7,
                          "normal": 2},
            neighbor_count=50,
            first_seen="2026-06-01T00:00:00+00:00",
            last_seen="2026-06-08T00:00:00+00:00",
            per_day={"2026-06-01": 1500, "2026-06-02": 1499},
            validation_errors=["passo 1: ação possui suporte lexical de 0.40, "
                               "abaixo de 0.60"],
        )

    def answer_question(self, pergunta, mode=None):
        return ChatReport(
            status="answered",
            message="- Ajustar tensão [Doc4.pdf — seção 9.1].",
            families=("correia",), sources=("Doc4.pdf",), renderer="ollama",
            degraded=False,
            limitations=("A evidência não cobre o torque exato de reaperto.",),
        )


class DocumentoFalso:
    def __init__(self, family, title):
        self.family = family
        self.title = title
        self.source_path = f"/srv/data_uploads/{family}.pdf"
        self.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)


class RegistryFalso:
    def __init__(self):
        self._documentos = [DocumentoFalso("correia", "Doc4 - Correias"),
                            DocumentoFalso("rolamento_inner", "Doc1 - Rolamentos")]

    def list_documents(self):
        return list(self._documentos)

    def has_document(self, family, title=None):
        return any(doc.family == family for doc in self._documentos)


def _df() -> pd.DataFrame:
    linhas = []
    for i, (fault, family, kind, dia) in enumerate([
        ("correia_2", "correia", "falha", "2026-06-01"),
        ("correia_3", "correia", "falha", "2026-06-02"),
        ("rolamento_inner_2", "rolamento_inner", "falha", "2026-06-01"),
        ("ventoinha_1", "ventoinha", "falha", "2026-06-02"),
        ("normal_1", "normal", "estado", "2026-06-03"),
    ]):
        linha = {c: float(i + 1) for c in FEATURE_COLUMNS}
        linha.update(id=100 + i, fault=fault, family=family, kind=kind,
                     created_at=f"{dia}T10:00:00+00:00")
        linhas.append(linha)
    df = pd.DataFrame(linhas)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df


@pytest.fixture(autouse=True)
def api_real(monkeypatch):
    """Roteia o httpx do cliente do dashboard para o TestClient da API real."""
    import api as cliente
    import estado

    app = create_app(skip_bootstrap=True)
    estado_da_api = AppState(pipeline=PipelineComEmpate(),
                             registry=RegistryFalso(), index=None, df=_df())
    app.dependency_overrides[get_state] = lambda: estado_da_api
    servidor = TestClient(app)

    def _request(metodo, url, **kwargs):
        # O cliente monta a URL absoluta; o TestClient quer o caminho relativo.
        kwargs.pop("timeout", None)
        return servidor.request(metodo, url.replace(cliente.API_URL, ""), **kwargs)

    monkeypatch.setattr(cliente.httpx, "request", _request)

    for cacheada in (estado._familias_cru, estado.carregar_historico,
                     estado.carregar_documentos, estado.carregar_saude):
        cacheada.clear()
    yield servidor
    for cacheada in (estado._familias_cru, estado.carregar_historico,
                     estado.carregar_documentos, estado.carregar_saude):
        cacheada.clear()


def _rodar(pagina: str):
    prova = AppTest.from_file(str(_DASHBOARD / "paginas" / pagina),
                             default_timeout=30)
    prova.run()
    assert not prova.exception, [str(e) for e in prova.exception]
    return prova


def _textos(prova) -> str:
    partes = []
    for colecao in (prova.markdown, prova.caption, prova.warning, prova.error,
                    prova.success, prova.info, prova.subheader, prova.title):
        partes.extend(elemento.value for elemento in colecao)
    for metrica in prova.metric:
        partes.extend([metrica.label, str(metrica.value)])
    return "\n".join(partes)


# --- Cliente contra a API real -------------------------------------------

def test_cliente_le_vocabulario_da_api_real():
    import api as cliente

    familias = cliente.familias()

    por_slug = {item["familia"]: item for item in familias}
    assert por_slug["eccentric_rotor"]["rotulo"] == "Rotor excêntrico"
    assert por_slug["correia"]["documentado"] is True
    assert por_slug["ventoinha"]["documentado"] is False


def test_cliente_le_historico_da_api_real():
    import api as cliente

    resumo = cliente.historico_resumo()

    assert resumo["total_leituras"] == 5
    assert resumo["janela"]["primeira"] == "2026-06-01"


def test_cliente_diagnostica_pela_api_real():
    import api as cliente

    amostra = cliente.amostra("correia")
    resposta = cliente.diagnosticar(amostra["features"], "offline")

    # Os campos que a tela le, vindos da serializacao real de DiagnosticoOut.
    assert resposta["rotulo"] == "Correia"
    assert resposta["degradado"] is True
    assert resposta["erros_de_validacao"]
    assert resposta["ocorrencias"]["primeira"]
    assert resposta["vizinhos_consultados"] == 50


def test_cliente_traduz_erro_da_api_em_excecao_de_dominio():
    import api as cliente

    # 422 real da rota: familia fora do vocabulario.
    with pytest.raises(cliente.ApiRecusou) as erro:
        cliente.amostra("banana")

    assert erro.value.status == 422
    assert "família" in erro.value.detalhe


# --- Paginas contra a API real -------------------------------------------

def test_historico_renderiza_com_a_api_real():
    prova = _rodar("historico.py")

    assert "01/06/2026 a 03/06/2026" in _textos(prova)
    # O rotulo em portugues vive no grafico e na tabela, que o AppTest nao
    # inspeciona; o multiselect usa o MESMO rotulador e serve de prova de que o
    # vocabulario da API chegou a pagina.
    exibidas = prova.multiselect[0].options
    assert "Rolamento — pista interna" in exibidas
    assert not [texto for texto in exibidas if "_" in texto]


def test_diagnostico_qualifica_o_empate_com_a_api_real():
    prova = _rodar("diagnostico.py")
    prova.button[0].click().run()
    assert not prova.exception, [str(e) for e in prova.exception]

    texto = _textos(prova)
    assert "9 de 50" in texto
    assert "inconclusiva" in texto.lower()
    assert "não produzido pelo modelo" in texto.lower()
    # Numeros grandes em padrao brasileiro, vindos do contrato real.
    assert "11.999" in texto
    assert "1.499,88" in texto


def test_chat_renderiza_resposta_da_api_real():
    prova = _rodar("chat.py")
    prova.chat_input[0].set_value("como corrigir correia?").run()
    assert not prova.exception, [str(e) for e in prova.exception]

    texto = _textos(prova)
    assert "Respondido com fonte" in texto
    assert "Doc4.pdf" in texto
    assert "torque exato" in texto


def test_documentos_lista_da_api_real_sem_expor_caminho():
    prova = _rodar("documentos.py")

    texto = _textos(prova)
    assert "data_uploads" not in texto
    metricas = {m.label: m.value for m in prova.metric}
    assert metricas["Cobertura documental"].startswith("2 de ")
