"""Teste de reinicio: uploads cadastrados sobrevivem a troca de processo.

O indice vetorial (VectorIndex) e volatil em memoria — qualquer reinicio do
processo (deploy, restart do container, etc.) o zera. O que faz um documento
cadastrado via /documentos sobreviver e a combinacao de dois fatores:

  1. O arquivo persistido em disco (Settings.uploads_dir) sobrevive ao
     reinicio (no Docker, isso exige um volume nomeado — ver
     docker-compose.yml, servico `api`).
  2. O registro no banco (DocumentRegistry) tambem sobrevive, e
     scripts.bootstrap.ingest_registry_documents usa esse registro para
     reidratar o indice a partir do arquivo, no bootstrap seguinte.

Este teste simula esse ciclo completo SEM Docker: usa sqlite em ARQUIVO (nao
":memory:", que morre com a conexao) para o registry, e destroi/reconstroi
engine, indice e estado da aplicacao entre os dois "processos" simulados.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import create_app, get_state
from app.api.state import AppState
from app.core.config import get_settings
from app.data.db import make_session_factory
from app.data.models import Base
from app.data.registry import DocumentRegistry
from app.rag.index import VectorIndex
from scripts.bootstrap import _bootstrap_seed_paths, ingest_registry_documents


class FakeEmbedder:
    """Embedder deterministico de teste (mesmo padrao de tests/test_rag.py e
    tests/test_bootstrap.py): conta ocorrencias de palavras-chave do dominio
    e normaliza a mao, sem depender de modelo real."""

    dim = 4

    def embed(self, texts: list[str], type_: str) -> list[list[float]]:
        out = []
        for t in texts:
            low = t.lower()
            v = [float(low.count("ventoinha")), float(low.count("procedimento")),
                 float(len(low)), 1.0]
            norm = sum(x * x for x in v) ** 0.5
            out.append([x / norm for x in v])
        return out


_CONTEUDO_VENTOINHA = (
    "1. Objetivo\n"
    "Procedimento de manutencao da ventoinha de resfriamento do motor.\n"
    "2. Sintomas\n"
    "Ventoinha desbalanceada gera vibracao excessiva no eixo do motor.\n"
)


def _session_factory_arquivo(db_path: Path):
    """sessionmaker sqlite em ARQUIVO real (nao :memory:), com StaticPool e
    check_same_thread=False: necessario porque o TestClient roda a rota
    /documentos em thread separada (Starlette executa handlers sync via
    threadpool) — mesma razao pela qual tests/test_api.py usa StaticPool
    para :memory:. A diferenca aqui e que o arquivo em disco sobrevive ao
    dispose() da engine, permitindo reabrir com uma engine NOVA depois,
    exatamente como um restart real do processo faria."""
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return factory, engine


def _state_override(state: AppState):
    """Cria uma dependency override sem parametros para o FastAPI."""
    def current_state() -> AppState:
        return state

    return current_state


def test_reinicio_preserva_documentos_cadastrados_e_reindexados(tmp_path, monkeypatch):
    # Cenario: usuario cadastra um documento novo (familia "ventoinha", sem
    # PDF_MAP/seed) via /documentos; o processo reinicia (deploy, restart de
    # container); o bootstrap seguinte precisa reidratar esse documento no
    # indice vetorial novo, sem intervencao manual.
    db_path = tmp_path / "reg.db"
    uploads_dir = tmp_path / "uploads"

    try:
        # ---- Ciclo 1: processo "antes do reinicio" ----------------------
        monkeypatch.setenv("UPLOADS_DIR", str(uploads_dir))
        get_settings.cache_clear()

        factory1, engine1 = _session_factory_arquivo(db_path)
        registry1 = DocumentRegistry(factory1)
        index1 = VectorIndex(FakeEmbedder())

        app1 = create_app(skip_bootstrap=True)
        state1 = AppState(pipeline=None, registry=registry1, index=index1, df=None,
                          session_factory=factory1)
        app1.dependency_overrides[get_state] = _state_override(state1)
        client1 = TestClient(app1)

        r = client1.post(
            "/documentos",
            files={"file": ("ventoinha.md", _CONTEUDO_VENTOINHA.encode("utf-8"),
                            "text/markdown")},
            data={"familia": "ventoinha", "titulo": "Procedimento Ventoinha"},
        )
        assert r.status_code == 200
        assert r.json()["trechos_indexados"] > 0

        # Documento realmente foi parar em disco (uploads_dir), nao so em
        # memoria — pre-requisito para sobreviver ao "reinicio" abaixo.
        arquivos_gravados = list(uploads_dir.iterdir())
        assert len(arquivos_gravados) == 1

        # ---- Fim do ciclo 1: destroi indice e estado ---------------------
        # Descarta TUDO que era volatil em memoria: cliente, app, estado e o
        # indice vetorial. O que resta e apenas o arquivo em uploads_dir/ e o
        # arquivo de banco em disco (db_path) — exatamente o que sobrevive a
        # um restart real (com o volume Docker correto).
        client1.close()
        engine1.dispose()
        del client1, app1, state1, index1, registry1, factory1, engine1

        # ---- Ciclo 2: processo "depois do reinicio" ----------------------
        # Engine e indice NOVOS, sem nenhuma referencia ao ciclo 1. So o
        # arquivo de banco (mesmo db_path) e o arquivo em uploads_dir ligam
        # os dois ciclos.
        factory2 = make_session_factory(f"sqlite+pysqlite:///{db_path.as_posix()}")
        registry2 = DocumentRegistry(factory2)
        registry2.seed_defaults()  # mesma ordem de scripts.bootstrap.build_state
        index2 = VectorIndex(FakeEmbedder())

        ingested, missing = ingest_registry_documents(registry2, index2, _bootstrap_seed_paths())

        assert ingested == 1
        assert missing == []

        hits = index2.search("procedimento de manutencao da ventoinha",
                             doc_family="ventoinha", k=4, min_score=0.0)
        assert len(hits) > 0
        assert "ventoinha" in hits[0].chunk.text.lower()
    finally:
        get_settings.cache_clear()


def test_reidratacao_e_o_que_popula_o_indice_apos_reinicio(tmp_path, monkeypatch):
    # Prova de que o teste principal e genuino: NAO basta mostrar que um
    # VectorIndex novo comeca vazio (isso e verdade por construcao —
    # VectorIndex.search faz early-return pra qualquer familia ausente de
    # self._indexes, entao "busca vazia" sozinho passaria mesmo com
    # ingest_registry_documents quebrado, ex.: sempre retornando 0 docs
    # ingeridos). O teste real precisa ser um CONTRASTE na MESMA
    # maquina de busca (mesmo index2/registry2): (1) antes de chamar
    # ingest_registry_documents, a busca pela familia "ventoinha" vem vazia;
    # (2) chamando ingest_registry_documents nesse MESMO index2, a MESMA
    # busca passa a retornar o chunk. So esse delta vazio->cheio isola o
    # efeito da reidratacao — uma regressao em ingest_registry_documents
    # (ex.: parar de chamar ingest_pdf, ou nao encontrar o doc no registry)
    # faz a etapa (2) falhar, porque a busca continuaria vazia.
    db_path = tmp_path / "reg.db"
    uploads_dir = tmp_path / "uploads"

    try:
        # ---- Ciclo 1: processo "antes do reinicio" ----------------------
        monkeypatch.setenv("UPLOADS_DIR", str(uploads_dir))
        get_settings.cache_clear()

        factory1, engine1 = _session_factory_arquivo(db_path)
        registry1 = DocumentRegistry(factory1)
        index1 = VectorIndex(FakeEmbedder())

        app1 = create_app(skip_bootstrap=True)
        state1 = AppState(pipeline=None, registry=registry1, index=index1, df=None,
                          session_factory=factory1)
        app1.dependency_overrides[get_state] = _state_override(state1)
        client1 = TestClient(app1)

        r = client1.post(
            "/documentos",
            files={"file": ("ventoinha.md", _CONTEUDO_VENTOINHA.encode("utf-8"),
                            "text/markdown")},
            data={"familia": "ventoinha", "titulo": "Procedimento Ventoinha"},
        )
        assert r.status_code == 200

        # ---- Fim do ciclo 1: destroi indice e estado ---------------------
        client1.close()
        engine1.dispose()
        del client1, app1, state1, index1, registry1, factory1, engine1

        # ---- Ciclo 2: processo "depois do reinicio" ----------------------
        factory2 = make_session_factory(f"sqlite+pysqlite:///{db_path.as_posix()}")
        registry2 = DocumentRegistry(factory2)
        index2 = VectorIndex(FakeEmbedder())

        # O registro sobrevive ao reinicio sozinho (o banco por si so
        # preserva o cadastro)...
        assert any(doc.family == "ventoinha" for doc in registry2.list_documents())

        # ...mas o indice novo (mesmo index2 usado depois) comeca sem
        # nenhum chunk da familia "ventoinha": a busca vem vazia ANTES da
        # reidratacao.
        hits_antes = index2.search("procedimento de manutencao da ventoinha",
                                   doc_family="ventoinha", k=4, min_score=0.0)
        assert hits_antes == []

        # Reidratacao explicita, no MESMO index2/registry2 usados acima.
        ingested, missing = ingest_registry_documents(registry2, index2, _bootstrap_seed_paths())
        assert ingested == 1
        assert missing == []

        # MESMA busca, MESMO index2: agora retorna o chunk. O contraste
        # vazio (antes) -> cheio (depois) e o que prova que foi a chamada
        # de ingest_registry_documents que populou o indice.
        hits_depois = index2.search("procedimento de manutencao da ventoinha",
                                    doc_family="ventoinha", k=4, min_score=0.0)
        assert len(hits_depois) > 0
        assert "ventoinha" in hits_depois[0].chunk.text.lower()
    finally:
        get_settings.cache_clear()
