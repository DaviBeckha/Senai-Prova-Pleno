from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import create_app, get_state
from app.api.state import AppState
from app.data.loader import FEATURE_COLUMNS
from app.data.models import Base, Diagnosis, Event
from app.pipeline import DiagnosisReport


class FakePipeline:
    def __init__(self):
        self.last_mode = "nao chamado"

    def diagnose(self, event, mode=None):
        self.last_mode = mode
        return DiagnosisReport("diagnostico", "correia", "ajustar tensao",
                               10, 1.5, ["Doc4.pdf"], "template", False,
                               {"correia": 10})

    def answer_question(self, pergunta, mode=None):
        self.last_mode = mode
        return DiagnosisReport("diagnostico", "correia", "ajustar tensao",
                               10, 1.5, ["Doc4.pdf"], "template", False,
                               {"correia": 10})


def _client():
    app = create_app(skip_bootstrap=True)
    state = AppState(pipeline=FakePipeline(), registry=None, index=None, df=None)
    app.dependency_overrides[get_state] = lambda: state
    return TestClient(app)


def _client_com_pipeline():
    """Variante que devolve tambem o FakePipeline, para inspecionar o mode
    que efetivamente chegou nele (o campo `modo` do body precisa atravessar
    a rota ate a chamada de diagnose/answer_question)."""
    app = create_app(skip_bootstrap=True)
    pipeline = FakePipeline()
    state = AppState(pipeline=pipeline, registry=None, index=None, df=None)
    app.dependency_overrides[get_state] = lambda: state
    return TestClient(app), pipeline


def _session_factory_memoria() -> sessionmaker:
    """sessionmaker sqlite in-memory com StaticPool: uma unica conexao
    compartilhada, necessaria porque a rota /eventos roda em thread separada
    (Starlette executa handlers sync via threadpool) e um :memory: comum
    abriria um banco vazio por conexao/thread."""
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def test_health():
    assert _client().get("/health").status_code == 200


def test_eventos_retorna_diagnostico():
    body = {c: 0.1 for c in FEATURE_COLUMNS}
    r = _client().post("/eventos", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "diagnostico"
    assert data["sources"] == ["Doc4.pdf"]
    assert data["family_votes"] == {"correia": 10}


def test_eventos_valida_campos():
    r = _client().post("/eventos", json={"rpm": 1000.0})
    assert r.status_code == 422


def test_eventos_feature_null_retorna_422():
    # Bug corrigido: com EventIn tipado (float obrigatorio, nao float | None),
    # uma feature com valor null no JSON tambem vira 422 da validacao do
    # FastAPI/Pydantic, e nao mais um 500 (getattr/float(None) explodindo
    # dentro do pipeline).
    body = {c: 0.1 for c in FEATURE_COLUMNS}
    body["rpm"] = None
    r = _client().post("/eventos", json=body)
    assert r.status_code == 422


def test_eventos_modo_online_chega_ao_pipeline():
    client, pipeline = _client_com_pipeline()
    body = {c: 0.1 for c in FEATURE_COLUMNS}
    body["modo"] = "online"
    r = client.post("/eventos", json=body)
    assert r.status_code == 200
    assert pipeline.last_mode == "online"


def test_eventos_modo_invalido_retorna_422():
    client, pipeline = _client_com_pipeline()
    body = {c: 0.1 for c in FEATURE_COLUMNS}
    body["modo"] = "banana"
    r = client.post("/eventos", json=body)
    assert r.status_code == 422
    assert "modo invalido" in r.json()["detail"]
    assert pipeline.last_mode == "nao chamado"


def test_chat_fora_do_dominio():
    # FakePipeline com answer_question que retorna sem_documento
    class FakeChatPipeline(FakePipeline):
        def answer_question(self, pergunta, mode=None):
            return DiagnosisReport("sem_documento", "desconhecido",
                                   "Problema ainda não documentado...", 0, 0.0,
                                   [], None, False, {})
    app = create_app(skip_bootstrap=True)
    state = AppState(pipeline=FakeChatPipeline(), registry=None, index=None, df=None)
    app.dependency_overrides[get_state] = lambda: state
    r = TestClient(app).post("/chat", json={"pergunta": "e a fase eletrica?"})
    assert "não documentado" in r.json()["resposta"]


def test_chat_modo_online_chega_ao_pipeline():
    client, pipeline = _client_com_pipeline()
    r = client.post("/chat", json={"pergunta": "como corrigir correia?",
                                   "modo": "online"})
    assert r.status_code == 200
    assert pipeline.last_mode == "online"


def test_chat_modo_invalido_retorna_422():
    client, pipeline = _client_com_pipeline()
    r = client.post("/chat", json={"pergunta": "como corrigir correia?",
                                   "modo": "banana"})
    assert r.status_code == 422
    assert "modo invalido" in r.json()["detail"]
    assert pipeline.last_mode == "nao chamado"


def test_eventos_persiste_event_e_diagnosis():
    # Persistencia minima: quando state.session_factory esta presente, cada
    # POST /eventos grava 1 Event + 1 Diagnosis (event_id referenciando o
    # Event recem-criado).
    factory = _session_factory_memoria()
    app = create_app(skip_bootstrap=True)
    pipeline = FakePipeline()
    state = AppState(pipeline=pipeline, registry=None, index=None, df=None,
                     session_factory=factory)
    app.dependency_overrides[get_state] = lambda: state
    client = TestClient(app)

    body = {c: 0.1 for c in FEATURE_COLUMNS}
    r = client.post("/eventos", json=body)
    assert r.status_code == 200

    with factory() as session:
        events = list(session.scalars(select(Event)).all())
        diagnoses = list(session.scalars(select(Diagnosis)).all())

    assert len(events) == 1
    assert len(diagnoses) == 1
    assert events[0].family == "correia"
    assert events[0].kind == "falha"
    assert diagnoses[0].event_id == events[0].id
    assert diagnoses[0].status == "diagnostico"
    assert diagnoses[0].family == "correia"


def test_eventos_sem_session_factory_nao_persiste():
    # session_factory=None (default do AppState/dataclass): nenhuma tentativa
    # de persistencia deve ocorrer — comportamento identico ao anterior a
    # esta mudanca.
    r = _client().post("/eventos", json={c: 0.1 for c in FEATURE_COLUMNS})
    assert r.status_code == 200


def test_documentos_extensao_nao_suportada():
    client, _ = _client_com_pipeline()
    r = client.post(
        "/documentos",
        files={"file": ("documento.docx", b"conteudo fake",
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document")},
        data={"family": "ventoinha", "title": "Doc Fake"},
    )
    assert r.status_code == 422
    assert "extensão não suportada" in r.json()["detail"]
