import json
from pathlib import Path

import pytest

from app.api.schemas import EventIn
from app.core.config import Settings
from app.data.db import make_session_factory
from app.data.loader import FEATURE_COLUMNS, load_dataset
from app.data.models import Base
from app.data.registry import DocumentRegistry
from app.llm.router import Router
from app.llm.template_fallback import TemplateRenderer
from app.pipeline import PrescriptivePipeline
from app.rag.chunking import Chunk
from app.rag.search import SearchHit
from app.similarity.engine import SimilarityEngine

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


class FakeIndex:
    """Indice fake: qualquer familia documentada devolve um trecho utilizavel,
    sem depender de embeddings reais (mesmo contrato de tests/test_pipeline.py)."""

    def search(self, query, doc_family, k=4, min_score=0.0):
        return [SearchHit(Chunk(doc_family, "Doc4.pdf", "9.1", "ajustar tensao"), 0.9)]


def _make_registry() -> DocumentRegistry:
    factory = make_session_factory("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(factory.kw["bind"])
    registry = DocumentRegistry(factory)
    registry.seed_defaults()
    return registry


@pytest.fixture(scope="module")
def real_pipeline():
    """Pipeline real montado sobre o dataset completo (banner.xlsx via
    Settings.data_file), com registry seedado de verdade e o mesmo
    SimilarityEngine/PrescriptivePipeline do bootstrap — so o indice
    vetorial e o roteador de LLM sao substituidos por dublês (índice fake e
    TemplateRenderer), como em tests/test_pipeline.py.

    Escopo de modulo de proposito: ler e normalizar o xlsx inteiro
    (166 mil linhas) leva dezenas de segundos, e os tres testes de evento
    abaixo so leem o pipeline, nunca mutam df/engine/registry — rodar este
    fixture uma vez por teste multiplicaria o tempo da suite por tres sem
    nenhum ganho de isolamento.
    """
    settings = Settings()
    df = load_dataset(settings.data_file)
    engine = SimilarityEngine()
    engine.fit(df)
    registry = _make_registry()
    router = Router(primary=TemplateRenderer(), fallback=TemplateRenderer())
    return PrescriptivePipeline(engine, df, registry, FakeIndex(), router)


def _load_event(filename: str) -> dict:
    path = DEMO_DIR / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    # Trava de contrato: o JSON versionado precisa ter exatamente os 23
    # campos de EventIn — nem faltando (422 na API) nem com metadado extra
    # (linha/fault de origem ficam em demo/README.md, nunca no payload).
    assert set(data.keys()) == set(FEATURE_COLUMNS)
    EventIn(**data)  # nao pode levantar ValidationError
    return data


def test_evento_correia_valida_e_retem_diagnostico_empatado(real_pipeline):
    event = _load_event("evento_correia.json")
    rep = real_pipeline.diagnose(event)
    assert rep.status == "diagnostico_inconclusivo"
    assert rep.family is None
    assert rep.candidate_families == [
        "correia",
        "rolamento_ball",
        "rolamento_outer",
    ]
    assert rep.top_vote_share == pytest.approx(9 / 50)
    assert rep.vote_margin == 0
    assert rep.sources == []
    assert rep.renderer is None


def test_evento_ventoinha_valida_e_fica_sem_documento(real_pipeline):
    event = _load_event("evento_ventoinha.json")
    rep = real_pipeline.diagnose(event)
    assert rep.status == "sem_documento"
    assert rep.family == "ventoinha"
    assert rep.sources == []
    assert rep.renderer is None


def test_evento_normal_valida_e_retorna_estado(real_pipeline):
    event = _load_event("evento_normal.json")
    rep = real_pipeline.diagnose(event)
    assert rep.status == "estado"
    assert rep.family == "normal"
    assert rep.renderer is None


def test_procedimento_ventoinha_demo_gera_chunks_reais():
    """O documento usado no passo 'cadastrar ao vivo' precisa gerar chunks
    de verdade (secoes numeradas reconhecidas por app/rag/chunking), nao
    texto solto — senao o passo da demonstracao nao teria evidencia para
    o RAG recuperar depois do cadastro."""
    from app.rag.ingest import ingest_pdf
    from app.rag.index import VectorIndex

    class FakeEmbedder:
        dim = 4

        def embed(self, texts, type_):
            return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    index = VectorIndex(FakeEmbedder())
    n = ingest_pdf(str(DEMO_DIR / "procedimento_ventoinha_demo.md"), "ventoinha", index)

    assert n == 3
    secoes = {c.section for c in index.chunks_for_family("ventoinha")}
    assert secoes == {"1. Sintomas", "2. Diagnóstico", "3. Correção"}
