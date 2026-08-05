from app.core.config import Settings, get_settings


def test_settings_defaults(monkeypatch):
    # Settings direto com _env_file=None: imune ao .env local da maquina
    # (que legitimamente sobrescreve OLLAMA_MODEL em dev — ver spec da
    # conversa LLM). get_settings() continua coberto pelo teste de override.
    monkeypatch.delenv("LLM_MODE", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    s = Settings(_env_file=None)
    assert s.llm_mode == "offline"
    assert s.embedding_dim == 768
    assert s.ollama_model == "qwen2.5:7b-instruct"
    assert s.ollama_timeout == 300.0
    assert s.ollama_num_ctx == 8192


def test_settings_ollama_env_overrides(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT", "45.5")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")
    get_settings.cache_clear()
    s = get_settings()
    assert s.ollama_timeout == 45.5
    assert s.ollama_num_ctx == 4096
    get_settings.cache_clear()
