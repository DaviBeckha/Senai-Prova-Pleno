from app.api.state import AppState
from app.core.config import Settings
from app.data.dataset_store import ensure_dataset
from app.data.db import make_session_factory
from app.data.registry import DocumentRegistry
from app.llm.ollama_adapter import OllamaRenderer
from app.llm.openai_adapter import OpenAIRenderer
from app.llm.router import Router
from app.llm.template_fallback import TemplateRenderer
from app.rag.embedding import EmbeddingService
from app.rag.index import VectorIndex
from app.rag.ingest import ingest_pdf
from app.similarity.engine import SimilarityEngine
from app.pipeline import PrescriptivePipeline

# Doc1.pdf e digitalizado sem camada de texto extraivel. No lugar, usamos a
# transcricao versionada em docs_fontes/doc1_rolamentos.md, que chunk_file/
# ingest_pdf ja suportam via despacho por extensao. Doc2-Doc6 permanecem
# PDFs originais.
PDF_MAP = [
    ("docs_fontes/doc1_rolamentos.md", ["rolamento_inner", "rolamento_outer",
                                        "rolamento_ball", "rolamento_combination"]),
    ("Doc2.pdf", ["desalinhado"]),
    ("Doc3.pdf", ["desbalanceado"]),
    ("Doc4.pdf", ["correia"]),
    ("Doc5.pdf", ["polia"]),
    ("Doc6.pdf", ["cocked_rotor"]),
]


def make_routers(settings: Settings) -> dict[str, Router]:
    # Um Router por modo, montado uma vez no bootstrap. A escolha de QUAL
    # router usar em cada requisicao e do pipeline (via kwarg `mode`), nao
    # mais fixa no processo inteiro — ver PrescriptivePipeline.diagnose/
    # answer_question em app/pipeline.py.
    fallback_offline = TemplateRenderer()
    fallback_online = TemplateRenderer()
    ollama = OllamaRenderer(settings.ollama_base_url, settings.ollama_model)
    if settings.openai_api_key:
        online_primary = OpenAIRenderer(settings.openai_api_key,
                                        settings.openai_model)
    else:
        # sem chave: degrada silenciosamente para ollama no modo online
        online_primary = OllamaRenderer(settings.ollama_base_url,
                                        settings.ollama_model)
    return {
        "offline": Router(primary=ollama, fallback=fallback_offline),
        "online": Router(primary=online_primary, fallback=fallback_online),
    }


def make_router(settings: Settings) -> Router:
    routers = make_routers(settings)
    return routers.get(settings.llm_mode, routers["offline"])


def build_state(settings: Settings) -> AppState:
    factory = make_session_factory(settings.database_url)
    df = ensure_dataset(factory, settings.data_file)
    engine = SimilarityEngine()
    engine.fit(df)

    registry = DocumentRegistry(factory)
    registry.seed_defaults()

    embedder = EmbeddingService(settings.embedding_model,
                                settings.embedding_model, settings.embedding_dim)
    embedder.load()
    index = VectorIndex(embedder)
    for pdf, families in PDF_MAP:
        for family in families:
            chunks = ingest_pdf(pdf, family, index)
            print(f"ingerido {pdf} → {family}: {chunks} chunks")

    pipeline = PrescriptivePipeline(engine, df, registry, index,
                                    make_router(settings),
                                    routers=make_routers(settings),
                                    rag_k=settings.rag_k,
                                    rag_min_score=settings.rag_min_score,
                                    rag_complete_max_chars=settings.rag_complete_max_chars)
    return AppState(pipeline=pipeline, registry=registry, index=index, df=df,
                    session_factory=factory)
