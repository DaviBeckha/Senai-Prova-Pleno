"""GET /familias, /documentos, /historico/resumo e /eventos/amostra.

As quatro rotas existem para tirar o dashboard de duas dependencias que o
faziam divergir da API:

  1. a leitura local de banner.xlsx — duas fontes de verdade para o mesmo
     dataset, com a normalizacao de rotulo reimplementada no cliente;
  2. a ausencia de vocabulario em portugues — os slugs de familia
     (cocked_rotor, eccentric_rotor, rolamento_inner...) chegavam crus aos
     eixos dos graficos e ao texto do chat.
"""

import json
from datetime import datetime, timezone

import pandas as pd
from fastapi.testclient import TestClient

from app.api.main import create_app, get_state
from app.api.state import AppState
from app.data.labels import FAULT_FAMILIES, STATE_FAMILIES
from app.data.loader import FEATURE_COLUMNS
from app.pipeline import DiagnosisReport


class PipelineFalso:
    def diagnose(self, event, mode=None):
        return DiagnosisReport(
            status="diagnostico", family="correia", message="ajustar tensao",
            total_ocorrencias=3, freq_per_day=1.5, sources=["Doc4.pdf"],
            renderer="template", degraded=False, family_votes={"correia": 3},
            neighbor_count=3, first_seen="2026-06-01T10:00:00+00:00",
            last_seen="2026-06-02T10:00:00+00:00",
            per_day={"2026-06-01": 2, "2026-06-02": 1}, validation_errors=[],
        )


class DocumentoFalso:
    """Stand-in de app.data.models.Document, sem tocar banco."""

    def __init__(self, family, title, source_path, created_at):
        self.family = family
        self.title = title
        self.source_path = source_path
        self.created_at = created_at


class RegistryComDocumentos:
    def __init__(self, documentos=()):
        self._documentos = list(documentos)

    def list_documents(self):
        return list(self._documentos)

    def has_document(self, family, title=None):
        return any(doc.family == family for doc in self._documentos)


def _df_historico() -> pd.DataFrame:
    """Historico minimo com o mesmo contrato de app.data.loader.load_dataset."""
    linhas = []
    for i, (fault, family, kind, dia) in enumerate([
        ("correia_2", "correia", "falha", "2026-06-01"),
        ("correia_3", "correia", "falha", "2026-06-01"),
        ("correia_4", "correia", "falha", "2026-06-02"),
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


def _client(documentos=(), df=None) -> TestClient:
    app = create_app(skip_bootstrap=True)
    state = AppState(pipeline=PipelineFalso(),
                     registry=RegistryComDocumentos(documentos),
                     index=None,
                     df=_df_historico() if df is None else df)
    app.dependency_overrides[get_state] = lambda: state
    return TestClient(app)


# --- GET /familias ---------------------------------------------------------

def test_familias_lista_todo_o_vocabulario_com_rotulo_em_portugues():
    data = _client().get("/familias").json()

    assert len(data) == len(FAULT_FAMILIES) + len(STATE_FAMILIES)
    rotulo = {item["familia"]: item["rotulo"] for item in data}
    # Justamente as familias cujo slug e (parcial ou totalmente) ingles: eram
    # elas que apareciam cruas nos dois graficos e no texto do chat.
    assert rotulo["eccentric_rotor"] == "Rotor excêntrico"
    assert rotulo["cocked_rotor"] == "Rotor desalinhado no eixo"
    assert rotulo["rolamento_inner"] == "Rolamento — pista interna"
    assert rotulo["rolamento_combination"] == "Rolamento — falha combinada"
    assert rotulo["falta_fase"] == "Falta de fase"
    assert all(item["rotulo"] for item in data)


def test_familias_nenhum_rotulo_deixa_underscore_vazar_para_a_tela():
    # display_label degrada para family.replace("_", " ") quando falta entrada
    # em DISPLAY_LABELS. O fallback protege contra 500, mas nao deve estar em
    # uso: um "_" no rotulo denuncia familia sem traducao.
    data = _client().get("/familias").json()

    assert [item for item in data if "_" in item["rotulo"]] == []


def test_familias_separa_falha_de_estado_de_operacao():
    data = _client().get("/familias").json()
    tipo = {item["familia"]: item["tipo"] for item in data}

    assert tipo["correia"] == "falha"
    assert tipo["normal"] == "estado"
    assert tipo["motor_desligado"] == "estado"
    # Falhas antes dos estados: e a ordem em que o dashboard as apresenta.
    tipos = [item["tipo"] for item in data]
    assert tipos == ["falha"] * len(FAULT_FAMILIES) + ["estado"] * len(STATE_FAMILIES)


def test_familias_marca_cobertura_documental():
    # E o que explica, na tela, quando o sistema se contem: familia sem
    # documento nunca recebe recomendacao (ver app/guardrails/policy.py).
    documentos = [DocumentoFalso("correia", "Doc4 - Correias", "Doc4.pdf",
                                 datetime(2026, 6, 1, tzinfo=timezone.utc))]
    data = _client(documentos).get("/familias").json()
    documentado = {item["familia"]: item["documentado"] for item in data}

    assert documentado["correia"] is True
    assert documentado["ventoinha"] is False
    assert documentado["eccentric_rotor"] is False


# --- GET /documentos ------------------------------------------------------

def test_documentos_lista_registros_sem_vazar_caminho_em_disco():
    # source_path aponta para dentro de UPLOADS_DIR no servidor: nao tem uso
    # legitimo no cliente e nao entra no contrato.
    documentos = [DocumentoFalso("correia", "Doc4 - Correias",
                                 "/srv/data_uploads/correia--doc4--ab12cd34.pdf",
                                 datetime(2026, 6, 1, tzinfo=timezone.utc))]
    data = _client(documentos).get("/documentos").json()

    assert len(data) == 1
    assert data[0]["familia"] == "correia"
    assert data[0]["rotulo"] == "Correia"
    assert data[0]["titulo"] == "Doc4 - Correias"
    assert set(data[0]) == {"familia", "rotulo", "titulo", "cadastrado_em"}
    assert "data_uploads" not in json.dumps(data, ensure_ascii=False)


def test_documentos_sem_registro_devolve_lista_vazia():
    # Empty state honesto: o dashboard distingue "nenhum documento" de "falha
    # ao consultar" — sao mensagens diferentes na tela.
    assert _client().get("/documentos").json() == []


# --- GET /historico/resumo -----------------------------------------------

def test_historico_resumo_agrega_o_mesmo_dataframe_do_knn():
    data = _client().get("/historico/resumo").json()

    assert data["total_leituras"] == 5
    assert data["janela"] == {"primeira": "2026-06-01", "ultima": "2026-06-03"}
    por_familia = {item["familia"]: item for item in data["por_familia"]}
    assert por_familia["correia"]["ocorrencias"] == 3
    assert por_familia["correia"]["tipo"] == "falha"
    assert por_familia["normal"]["tipo"] == "estado"
    # A soma por familia tem de fechar com o total: se divergir, o grafico da
    # tela nao representa o corpus que o motor de similaridade indexou.
    assert sum(i["ocorrencias"] for i in data["por_familia"]) == data["total_leituras"]


def test_historico_resumo_serie_por_dia_fecha_com_o_total():
    data = _client().get("/historico/resumo").json()

    dias = {(i["dia"], i["familia"]): i["ocorrencias"] for i in data["por_dia"]}
    assert dias[("2026-06-01", "correia")] == 2
    assert dias[("2026-06-02", "correia")] == 1
    assert dias[("2026-06-02", "ventoinha")] == 1
    assert sum(i["ocorrencias"] for i in data["por_dia"]) == data["total_leituras"]


def test_historico_resumo_devolve_apenas_slugs():
    # O rotulo em portugues vem do cache de GET /familias. Repetir o rotulo em
    # cada uma das ~1.000 entradas de por_dia inflaria a resposta e criaria uma
    # segunda fonte de vocabulario.
    data = _client().get("/historico/resumo").json()

    assert set(data["por_familia"][0]) == {"familia", "tipo", "ocorrencias"}
    assert set(data["por_dia"][0]) == {"dia", "familia", "ocorrencias"}


def test_historico_resumo_sem_dataframe_retorna_503():
    assert _client(df=pd.DataFrame()).get("/historico/resumo").status_code == 503


# --- GET /eventos/amostra ------------------------------------------------

def test_eventos_amostra_devolve_linha_real_pronta_para_diagnostico():
    data = _client().get("/eventos/amostra?familia=correia").json()

    assert data["familia"] == "correia"
    assert data["rotulo_original"].startswith("correia")
    assert data["id_externo"] in (100, 101, 102)
    # As 23 features completas e numericas: o payload segue direto para
    # POST /eventos, que exige float em todas (EventIn).
    assert set(data["features"]) == set(FEATURE_COLUMNS)
    assert all(isinstance(valor, float) for valor in data["features"].values())
    assert data["features_substituidas"] == []


def test_eventos_amostra_alimenta_post_eventos_sem_ajuste():
    # O contrato so vale se o payload atravessar a validacao do /eventos como
    # esta: qualquer ajuste necessario no cliente seria logica duplicada.
    client = _client()
    amostra = client.get("/eventos/amostra?familia=correia").json()

    r = client.post("/eventos", json=amostra["features"])

    assert r.status_code == 200


def test_eventos_amostra_nomeia_features_substituidas_por_zero():
    # ~38% das linhas do banner.xlsx tem artefato de datetime em coluna
    # numerica (virou NULL no seed). scripts/simulator.py::build_payload troca
    # por 0.0 e avisa apenas no stdout do container; aqui o aviso chega a quem
    # esta olhando a tela.
    df = _df_historico()
    df.loc[df["family"] == "correia", "rpm"] = None

    data = _client(df=df).get("/eventos/amostra?familia=correia").json()

    assert data["features_substituidas"] == ["rpm"]
    assert data["features"]["rpm"] == 0.0


def test_eventos_amostra_familia_desconhecida_retorna_422():
    # Sem a checagem de pertinencia, qualquer string que passasse a allowlist
    # _FAMILY_RE viraria um filtro aceito com resultado vazio — 404 confuso em
    # vez de 422 dizendo que a familia nao existe.
    client = _client()

    assert client.get("/eventos/amostra?familia=banana").status_code == 422
    assert client.get("/eventos/amostra?familia=../etc/passwd").status_code == 422
    assert client.get("/eventos/amostra?familia=").status_code == 422


def test_eventos_amostra_normaliza_a_familia_recebida():
    # Mesma normalizacao do POST /documentos (strip + casefold): a tela envia o
    # slug do selectbox, mas um link colado a mao nao deve falhar por caixa.
    client = _client()

    assert client.get("/eventos/amostra?familia=CORREIA").status_code == 200
    assert client.get("/eventos/amostra?familia=%20correia%20").status_code == 200


def test_eventos_amostra_familia_valida_sem_historico_retorna_404():
    # falta_fase existe no vocabulario mas nao ha leitura dela neste corpus:
    # e 404 (nada a sortear), nao 422 (familia invalida).
    assert _client().get("/eventos/amostra?familia=falta_fase").status_code == 404


def test_eventos_amostra_sem_dataframe_retorna_503():
    assert _client(df=pd.DataFrame()).get(
        "/eventos/amostra?familia=correia").status_code == 503
