from app.core.config import Settings
from scripts.bootstrap import make_router, make_routers


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
