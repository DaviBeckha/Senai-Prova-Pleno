from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://senai:senai@localhost:5432/manutencao"
    llm_mode: str = "offline"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dim: int = 768
    data_file: str = "banner.xlsx"
    faiss_dir: str = "data_local/faiss"

    # Corte de similaridade da evidencia. Os embeddings sao normalizados
    # (EmbeddingService.embed), entao o produto interno e o cosseno.
    #
    # 0.82 e um valor MEDIDO, nao arbitrario: o E5 comprime cossenos para
    # cima, e contra doc1/Doc2/Doc4/Doc5 o espectro inteiro fica entre 0.76 e
    # 0.91 — consultas fora do dominio ("receita de bolo") chegam a 0.844.
    # Em 0.82 preserva-se 100% da evidencia relevante e do caminho /eventos,
    # descartando ~90% do ruido; em 0.85 comeca-se a perder evidencia real.
    rag_min_score: float = 0.82
    rag_k: int = 4
    rag_complete_max_chars: int = 12_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
