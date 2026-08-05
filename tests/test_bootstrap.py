import logging

from app.core.config import Settings
from app.data.db import make_session_factory
from app.data.models import Base
from app.data.registry import _SEED, DocumentRegistry
from app.rag.index import VectorIndex
from scripts.bootstrap import (
    PDF_MAP,
    _bootstrap_seed_paths,
    ingest_registry_documents,
    make_router,
    make_routers,
)


class FakeEmbedder:
    """Embedder deterministico de teste (mesmo padrao de tests/test_rag.py)."""

    dim = 4

    def embed(self, texts: list[str], type_: str) -> list[list[float]]:
        out = []
        for t in texts:
            low = t.lower()
            v = [float(low.count("ventoinha")), float(low.count("procedimento")), float(len(low)), 1.0]
            norm = sum(x * x for x in v) ** 0.5
            out.append([x / norm for x in v])
        return out


def _registry() -> DocumentRegistry:
    factory = make_session_factory("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(factory.kw["bind"])
    return DocumentRegistry(factory)




def test_router_offline_usa_ollama():
    r = make_router(Settings(llm_mode="offline"))
    assert r._primary.name == "ollama"
    assert r._fallback.name == "template"


def test_router_online_usa_openai():
    r = make_router(Settings(llm_mode="online", openai_api_key="sk-test"))
    assert r._primary.name == "openai"
    assert r._fallback.name == "template"


def test_router_online_sem_chave_cai_para_ollama():
    r = make_router(Settings(llm_mode="online", openai_api_key=None))
    assert r._primary.name == "ollama"
    assert r._fallback.name == "template"


def test_make_routers_tem_offline_e_online():
    # Um Router por modo, independente de LLM_MODE: e o que permite o
    # pipeline escolher POR REQUISICAO via kwarg mode (ver test_pipeline.py
    # test_mode_seleciona_router e test_api.py testes de modo).
    routers = make_routers(Settings(llm_mode="offline", openai_api_key="sk-test"))
    assert set(routers.keys()) == {"offline", "online"}

    assert routers["offline"]._primary.name == "ollama"
    assert routers["offline"]._fallback.name == "template"

    assert routers["online"]._primary.name == "openai"
    assert routers["online"]._fallback.name == "template"


def test_make_routers_online_sem_chave_cai_para_ollama():
    routers = make_routers(Settings(llm_mode="offline", openai_api_key=None))
    assert routers["online"]._primary.name == "ollama"
    assert routers["online"]._fallback.name == "template"


def test_make_routers_propagates_ollama_limits():
    from app.core.config import Settings
    from scripts.bootstrap import make_routers

    settings = Settings(_env_file=None, openai_api_key=None, ollama_timeout=123.0, ollama_num_ctx=2048)
    routers = make_routers(settings)
    offline_primary = routers["offline"]._primary
    assert offline_primary._timeout == 123.0
    assert offline_primary._num_ctx == 2048
    # modo online SEM chave degrada para Ollama — mesmos limites
    online_primary = routers["online"]._primary
    assert online_primary._timeout == 123.0
    assert online_primary._num_ctx == 2048


def test_ingest_registry_documents_ingere_upload_registrado(tmp_path):
    # Simula o cenario pos-reinicio: um upload persistido em disco (ver
    # Settings.uploads_dir) permanece registrado no banco, mas o indice
    # vetorial e volatil em memoria — precisa ser reconstruido no bootstrap.
    reg = _registry()
    reg.seed_defaults()
    doc_path = tmp_path / "ventoinha.md"
    doc_path.write_text("1. Objetivo\nProcedimento de ventoinha para teste.", encoding="utf-8")
    reg.register("ventoinha", "Procedimento Ventoinha", str(doc_path))

    index = VectorIndex(FakeEmbedder())
    ingested, missing = ingest_registry_documents(reg, index, _bootstrap_seed_paths())

    assert ingested == 1
    assert missing == []
    assert index.chunks_for_family("ventoinha")


def test_ingest_registry_documents_pula_documentos_do_seed():
    # Os 6 documentos do seed (PDF_MAP) ja foram ingeridos no loop anterior de
    # build_state — reindexa-los aqui duplicaria o indice.
    reg = _registry()
    reg.seed_defaults()

    index = VectorIndex(FakeEmbedder())
    ingested, missing = ingest_registry_documents(reg, index, _bootstrap_seed_paths())

    assert ingested == 0
    assert missing == []


def test_ingest_registry_documents_reporta_arquivo_ausente_sem_derrubar_bootstrap(tmp_path, caplog):
    reg = _registry()
    reg.seed_defaults()
    caminho_ausente = str(tmp_path / "nao_existe.md")
    reg.register("fantasma", "Procedimento Fantasma", caminho_ausente)

    index = VectorIndex(FakeEmbedder())
    with caplog.at_level(logging.WARNING):
        ingested, missing = ingest_registry_documents(reg, index, _bootstrap_seed_paths())

    assert ingested == 0
    assert missing == [caminho_ausente]
    assert any(caminho_ausente in record.message for record in caplog.records)


def test_ingest_registry_documents_tolera_falha_de_ingestao_sem_derrubar_bootstrap(tmp_path, caplog):
    # Documento existe em disco (Path.exists() == True) mas o conteudo e
    # invalido: PdfReader (chunk_pdf) levanta ao tentar ler o header. Antes
    # desta correcao, essa excecao propagava de ingest_pdf e derrubava
    # build_state inteiro — um unico upload corrompido tirava a API do ar
    # a cada reinicio, ate intervencao manual no banco.
    reg = _registry()
    reg.seed_defaults()
    doc_path = tmp_path / "corrompido.pdf"
    doc_path.write_bytes(b"isto nao e um pdf valido, apenas bytes de lixo")
    reg.register("quebrado", "Procedimento Quebrado", str(doc_path))

    index = VectorIndex(FakeEmbedder())
    with caplog.at_level(logging.WARNING):
        ingested, not_ingested = ingest_registry_documents(reg, index, _bootstrap_seed_paths())

    assert ingested == 0
    assert not_ingested == [str(doc_path)]
    assert any(str(doc_path) in record.message for record in caplog.records)


def test_bootstrap_seed_paths_cobre_todos_os_paths_do_seed_do_registry():
    # Trava contra divergencia futura: se _SEED (app/data/registry.py) ganhar
    # uma familia nova com source_path que nao apareca no PDF_MAP, este teste
    # falha ANTES que o proximo reinicio reindexe (e duplique no indice) um
    # documento que ja deveria ser tratado como seed.
    seed_source_paths = {source_path for _title, source_path in _SEED.values()}
    assert seed_source_paths <= _bootstrap_seed_paths()
