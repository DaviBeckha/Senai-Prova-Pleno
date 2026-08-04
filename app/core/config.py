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


@lru_cache
def get_settings() -> Settings:
    return Settings()
