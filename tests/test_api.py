from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import create_app, get_state
from app.api.state import AppState
from app.core.config import get_settings
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


class FakeEmbedder:
    """Embedder deterministico (sem dependencia de modelo real) para exercitar
    VectorIndex.add durante a ingestao no fluxo de upload."""

    def embed(self, texts, type_):
        return [[float(len(t)), 1.0] for t in texts]


class FakeRegistry:
    """Registry em memoria que apenas grava as chamadas de register(), para
    inspecionar o caminho persistido sem tocar em banco/sqlite."""

    def __init__(self):
        self.registered = []

    def has_document(self, family, title=None):
        """Fake has_document para compatibilidade (dedup é checado antes nestes testes)."""
        if title is None:
            return any(f == family for f, _, _ in self.registered)
        normalized_title = title.strip().lower()
        return any(f == family and t.strip().lower() == normalized_title for f, t, _ in self.registered)

    def register(self, family, title, source_path):
        self.registered.append((family, title, source_path))


def _client_com_uploads(tmp_path, monkeypatch):
    """Client com uploads_dir apontando para tmp_path (via env var + cache_clear
    do get_settings), registry/index fake para inspecionar o resultado do
    upload sem sujar o repositorio nem depender de embeddings reais."""
    from app.rag.index import VectorIndex

    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    get_settings.cache_clear()

    registry = FakeRegistry()
    app = create_app(skip_bootstrap=True)
    state = AppState(pipeline=FakePipeline(), registry=registry,
                     index=VectorIndex(FakeEmbedder()), df=None)
    app.dependency_overrides[get_state] = lambda: state
    return TestClient(app), registry


def test_documentos_salva_arquivo_persistente(tmp_path, monkeypatch):
    # Uploads precisam sobreviver a restart: o arquivo tem que existir de
    # fato em uploads_dir/ (nao um tempfile apagado) e o registry deve guardar
    # o caminho REAL em disco, nao o filename original enviado pelo cliente.
    try:
        client, registry = _client_com_uploads(tmp_path, monkeypatch)
        content = b"1. Objetivo\nAjustar tensao da correia frouxa.\n"
        r = client.post(
            "/documentos",
            files={"file": ("Doc Teste.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r.status_code == 200

        assert len(registry.registered) == 1
        family, title, source_path = registry.registered[0]
        assert family == "correia"
        assert title == "Doc Teste"

        saved = Path(source_path)
        assert saved.exists()
        assert saved.parent == tmp_path
        assert saved.name != "Doc Teste.md"
        assert saved.read_bytes() == content
    finally:
        get_settings.cache_clear()


def test_documentos_arquivo_excede_10mb():
    client, _ = _client_com_pipeline()
    conteudo_grande = b"a" * (10 * 1024 * 1024 + 1)
    r = client.post(
        "/documentos",
        files={"file": ("grande.md", conteudo_grande, "text/markdown")},
        data={"family": "correia", "title": "Doc Grande"},
    )
    assert r.status_code == 422
    assert "10 MB" in r.json()["detail"]


def test_documentos_ingestao_falha_remove_arquivo_orfao(tmp_path, monkeypatch):
    # Se a ingestao falhar depois do arquivo ja gravado em disco, nao pode
    # sobrar lixo orfao em uploads_dir/ — e o erro original ainda precisa
    # propagar (comportamento existente preservado).
    import app.rag.ingest as ingest_module

    def _falha(*args, **kwargs):
        raise RuntimeError("falha simulada na ingestao")

    monkeypatch.setattr(ingest_module, "ingest_pdf", _falha)
    try:
        client, _ = _client_com_uploads(tmp_path, monkeypatch)
        with pytest.raises(RuntimeError):
            client.post(
                "/documentos",
                files={"file": ("doc.md", b"conteudo qualquer", "text/markdown")},
                data={"family": "correia", "title": "Doc X"},
            )
        assert list(tmp_path.iterdir()) == []
    finally:
        get_settings.cache_clear()


def test_documentos_family_com_path_traversal_e_rejeitada(tmp_path, monkeypatch):
    # PoC reportado na revisao: family="../../../evil_escape_poc" escapava
    # do uploads_dir e gravava fora do diretorio esperado. uploads_dir aqui
    # e um subdiretorio nao-criado de tmp_path (tmp_path e exclusivo deste
    # teste) para conseguirmos provar que NADA foi escrito em lugar nenhum
    # da arvore, nem dentro nem fora do uploads_dir.
    uploads_dir = tmp_path / "uploads_dir"
    try:
        client, registry = _client_com_uploads(uploads_dir, monkeypatch)
        r = client.post(
            "/documentos",
            files={"file": ("doc.md", b"conteudo qualquer", "text/markdown")},
            data={"family": "../../../evil_escape_poc", "title": "Doc Malicioso"},
        )
        assert r.status_code == 422
        assert "família inválida" in r.json()["detail"]
        assert registry.registered == []
        assert list(tmp_path.rglob("*")) == []
    finally:
        get_settings.cache_clear()


def test_documentos_family_snake_case_valida_continua_aceita(tmp_path, monkeypatch):
    # Familias legitimas do dominio sao snake_case com underscore (ex.:
    # rolamento_outer, motor_desligado) — a validacao anti-traversal nao
    # pode rejeitar esse formato.
    try:
        client, registry = _client_com_uploads(tmp_path, monkeypatch)
        content = b"1. Objetivo\nInspecionar pista externa do rolamento.\n"
        r = client.post(
            "/documentos",
            files={"file": ("Doc Rolamento.md", content, "text/markdown")},
            data={"family": "rolamento_outer", "title": "Doc Rolamento"},
        )
        assert r.status_code == 200
        assert registry.registered[0][0] == "rolamento_outer"
    finally:
        get_settings.cache_clear()


def test_documentos_defesa_em_profundidade_bloqueia_escape_do_uploads_dir(tmp_path, monkeypatch):
    # Camada extra, independente da validacao de family: mesmo que
    # _safe_filename um dia devolva um nome com travessia de diretorio, o
    # endpoint tem que barrar ANTES de gravar (422), nunca deixar escapar do
    # uploads_dir nem estourar em 500.
    import app.api.main as main_module

    monkeypatch.setattr(main_module, "_safe_filename",
                        lambda family, original: "../evil_escape.md")
    uploads_dir = tmp_path / "uploads_dir"
    try:
        client, registry = _client_com_uploads(uploads_dir, monkeypatch)
        r = client.post(
            "/documentos",
            files={"file": ("doc.md", b"conteudo qualquer", "text/markdown")},
            data={"family": "correia", "title": "Doc X"},
        )
        assert r.status_code == 422
        assert registry.registered == []
        assert not (tmp_path / "evil_escape.md").exists()
    finally:
        get_settings.cache_clear()


def test_documentos_filename_sem_extensao_retorna_422():
    # Fixado propositalmente: o fluxo novo rejeita com 422 quando o filename
    # nao tem extensao, em vez de assumir .pdf silenciosamente como o fluxo
    # antigo fazia.
    client, _ = _client_com_pipeline()
    r = client.post(
        "/documentos",
        files={"file": ("documento_sem_extensao", b"conteudo qualquer",
                        "application/octet-stream")},
        data={"family": "correia", "title": "Doc Sem Extensao"},
    )
    assert r.status_code == 422
    assert "extensão não suportada" in r.json()["detail"]


def _client_com_registry_e_index(tmp_path, monkeypatch):
    """Client com registry em SQLite, index fake e uploads em tmp_path."""
    from app.data.registry import DocumentRegistry
    from app.rag.index import VectorIndex

    session_factory = _session_factory_memoria()
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    get_settings.cache_clear()

    registry = DocumentRegistry(session_factory)
    app = create_app(skip_bootstrap=True)
    state = AppState(pipeline=FakePipeline(), registry=registry,
                     index=VectorIndex(FakeEmbedder()), df=None,
                     session_factory=session_factory)
    app.dependency_overrides[get_state] = lambda: state
    return TestClient(app), registry, state.index


def test_documentos_dedup_retorna_409_na_segunda_tentativa(tmp_path, monkeypatch):
    # POST /documentos duas vezes com mesmo family+title → 409
    try:
        client, _, _ = _client_com_registry_e_index(tmp_path, monkeypatch)
        content = b"1. Objetivo\nAjustar tensao da correia frouxa.\n"

        # Primeiro upload deve suceder
        r1 = client.post(
            "/documentos",
            files={"file": ("Doc Teste.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r1.status_code == 200

        # Segundo upload com mesma familia+titulo deve retornar 409
        r2 = client.post(
            "/documentos",
            files={"file": ("Doc Teste2.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r2.status_code == 409
        assert "documento já cadastrado" in r2.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_documentos_dedup_arquivo_nao_grava_quando_409(tmp_path, monkeypatch):
    # Dedup checado ANTES de gravar → 409 retorna sem arquivo em disco
    try:
        client, _, _ = _client_com_registry_e_index(tmp_path, monkeypatch)
        content = b"1. Objetivo\nAjustar tensao da correia frouxa.\n"

        # Primeiro upload
        r1 = client.post(
            "/documentos",
            files={"file": ("Doc Teste.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r1.status_code == 200
        files_after_first = list(tmp_path.iterdir())
        assert len(files_after_first) == 1
        first_file = files_after_first[0]

        # Segundo upload (dedup failure imediato)
        r2 = client.post(
            "/documentos",
            files={"file": ("Doc Teste2.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r2.status_code == 409

        # Arquivo não deve ter aumentado (o segundo nem foi gravado)
        files_after_second = list(tmp_path.iterdir())
        assert len(files_after_second) == 1
        assert files_after_second[0] == first_file
    finally:
        get_settings.cache_clear()


def test_documentos_dedup_chunks_nao_crescem_apos_409(tmp_path, monkeypatch):
    # Critical: chunks_for_family não cresce após 409 (dedup é ANTES da ingestão)
    try:
        client, _, index = _client_com_registry_e_index(tmp_path, monkeypatch)
        content = b"1. Objetivo\nAjustar tensao da correia frouxa.\n"

        # Primeiro upload
        r1 = client.post(
            "/documentos",
            files={"file": ("Doc Teste.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r1.status_code == 200
        chunks_after_first = len(index.chunks_for_family("correia"))
        assert chunks_after_first > 0

        # Segundo upload (dedup antes da ingestão)
        r2 = client.post(
            "/documentos",
            files={"file": ("Doc Teste2.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r2.status_code == 409

        # Chunks não devem ter aumentado
        chunks_after_second = len(index.chunks_for_family("correia"))
        assert chunks_after_second == chunks_after_first
    finally:
        get_settings.cache_clear()


def test_documentos_dedup_titulo_normalizado_com_espacos(tmp_path, monkeypatch):
    # Título normalizado: " Doc Teste " deve ser tratado como "Doc Teste"
    try:
        client, _, _ = _client_com_registry_e_index(tmp_path, monkeypatch)
        content = b"1. Objetivo\nAjustar tensao da correia frouxa.\n"

        # Primeiro upload com espaços
        r1 = client.post(
            "/documentos",
            files={"file": ("Doc Teste.md", content, "text/markdown")},
            data={"family": "correia", "title": " Doc Teste "},
        )
        assert r1.status_code == 200

        # Segundo upload sem espaços → 409
        r2 = client.post(
            "/documentos",
            files={"file": ("Doc Teste2.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r2.status_code == 409
    finally:
        get_settings.cache_clear()


def test_documentos_dedup_titulo_normalizado_case_insensitive(tmp_path, monkeypatch):
    # Título normalizado: "DOC TESTE" deve ser tratado como "Doc Teste"
    try:
        client, _, _ = _client_com_registry_e_index(tmp_path, monkeypatch)
        content = b"1. Objetivo\nAjustar tensao da correia frouxa.\n"

        # Primeiro upload
        r1 = client.post(
            "/documentos",
            files={"file": ("Doc Teste.md", content, "text/markdown")},
            data={"family": "correia", "title": "Doc Teste"},
        )
        assert r1.status_code == 200

        # Segundo upload com case diferente → 409
        r2 = client.post(
            "/documentos",
            files={"file": ("Doc Teste2.md", content, "text/markdown")},
            data={"family": "correia", "title": "doc teste"},
        )
        assert r2.status_code == 409
    finally:
        get_settings.cache_clear()
