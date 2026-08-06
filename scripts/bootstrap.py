import logging
from pathlib import Path

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

logger = logging.getLogger(__name__)

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


def _bootstrap_seed_paths() -> set[str]:
    """Paths que build_state trata como seed (ja ingeridos fora do registry).

    Uniao dos paths do PDF_MAP com "Doc1.pdf": o PDF original de rolamentos
    nao entra no PDF_MAP (usamos a transcricao docs_fontes/doc1_rolamentos.md
    no lugar — ver comentario acima), mas fica aqui por seguranca, caso algum
    registro legado no banco ainda aponte pra ele em vez da transcricao.

    Ponto unico de verdade: usado por build_state E pelos testes (ver
    tests/test_bootstrap.py), com um teste dedicado que trava a divergencia
    caso `app.data.registry._SEED` ganhe uma familia com source_path fora
    deste conjunto.
    """
    return {path for path, _ in PDF_MAP} | {"Doc1.pdf"}


def ingest_registry_documents(
    registry: DocumentRegistry, index: VectorIndex, seed_paths: set[str]
) -> tuple[int, list[str]]:
    """Reindexa documentos cadastrados (uploads) que nao vieram do PDF_MAP.

    Cobre o reinicio do processo: uploads persistidos em disco (ver
    Settings.uploads_dir) ficam registrados no banco, mas o indice vetorial
    e volatil em memoria — sem esta reindexacao, um restart faz os uploads
    sumirem da busca RAG mesmo com o registro intacto. Documentos do seed
    (`seed_paths`, paths do PDF_MAP acima) sao pulados por ja terem sido
    ingeridos no loop.

    Retorna (ingerido, nao_reidratados): a segunda lista acumula tanto os
    documentos cujo arquivo nao existe mais em disco quanto os que existem
    mas falham na ingestao (PDF corrompido, extensao nao suportada etc.) —
    em nenhum dos dois casos o bootstrap e derrubado; a falha fica so
    registrada em log (com o path e o erro) e no retorno, para quem chamou
    decidir o que fazer.
    """
    ingested = 0
    not_ingested: list[str] = []
    for doc in registry.list_documents():
        if doc.source_path in seed_paths:
            continue
        if not Path(doc.source_path).exists():
            not_ingested.append(doc.source_path)
            logger.warning(
                "documento cadastrado sem arquivo em disco, pulando: %s", doc.source_path
            )
            continue
        try:
            ingest_pdf(doc.source_path, doc.family, index)
        except Exception as exc:
            not_ingested.append(doc.source_path)
            logger.warning(
                "falha ao reindexar documento cadastrado, pulando: %s (%s)",
                doc.source_path, exc,
            )
            continue
        ingested += 1
    return ingested, not_ingested


def make_routers(settings: Settings) -> dict[str, Router]:
    # Um Router por modo, montado uma vez no bootstrap. A escolha de QUAL
    # router usar em cada requisicao e do pipeline (via kwarg `mode`), nao
    # mais fixa no processo inteiro — ver PrescriptivePipeline.diagnose/
    # answer_question em app/pipeline.py.
    fallback_offline = TemplateRenderer()
    fallback_online = TemplateRenderer()
    ollama = OllamaRenderer(settings.ollama_base_url, settings.ollama_model,
                            timeout=settings.ollama_timeout,
                            num_ctx=settings.ollama_num_ctx)
    if settings.openai_api_key:
        online_primary = OpenAIRenderer(settings.openai_api_key,
                                        settings.openai_model)
    else:
        # sem chave: degrada silenciosamente para ollama no modo online
        online_primary = OllamaRenderer(settings.ollama_base_url,
                                        settings.ollama_model,
                                        timeout=settings.ollama_timeout,
                                        num_ctx=settings.ollama_num_ctx)
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

    reindexed, not_reindexed = ingest_registry_documents(registry, index, _bootstrap_seed_paths())
    if reindexed:
        print(f"reindexados {reindexed} documento(s) cadastrado(s) apos reinicio")
    if not_reindexed:
        print(f"{len(not_reindexed)} documento(s) cadastrado(s) nao reidratado(s): {not_reindexed}")

    pipeline = PrescriptivePipeline(engine, df, registry, index,
                                    make_router(settings),
                                    routers=make_routers(settings),
                                    rag_k=settings.rag_k,
                                    rag_min_score=settings.rag_min_score,
                                    rag_complete_max_chars=settings.rag_complete_max_chars)
    return AppState(pipeline=pipeline, registry=registry, index=index, df=df,
                    session_factory=factory)
