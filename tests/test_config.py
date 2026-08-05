from app.core.config import get_settings


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("LLM_MODE", raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert s.llm_mode == "offline"
    assert s.embedding_dim == 768
    assert s.ollama_model == "qwen2.5:7b-instruct"
