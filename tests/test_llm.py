from app.llm.base import DiagnosisContext
from app.llm.router import Router
from app.llm.template_fallback import TemplateRenderer
from app.rag.chunking import Chunk
from app.similarity.stats import OccurrenceStats


def _ctx():
    return DiagnosisContext(
        family="correia",
        stats=OccurrenceStats(120, "2026-05-01T00:00:00+00:00",
                              "2026-06-10T00:00:00+00:00", {"2026-06-10": 3}, 2.9),
        chunks=[Chunk("correia", "Doc4.pdf", "9.1 Correia Frouxa",
                      "1. Afrouxar os parafusos do motor. 2. Ajustar a posicao.")],
        event={"rpm": 1000.0},
    )


class _FakeOllamaResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": "{\"steps\": [], \"unanswered\": []}"}}


def _capture_ollama_post(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeOllamaResponse()

    monkeypatch.setattr("app.llm.ollama_adapter.httpx.post", fake_post)
    return captured


class BoomRenderer:
    name = "boom"

    def render(self, ctx):
        raise RuntimeError("llm fora do ar")


def test_template_renders_evidence_and_sources():
    # Contrato atual (app/llm/template_fallback.py): TemplateRenderer e o
    # "ultimo degrau" e mostra SOMENTE evidencia crua (fonte + citacao),
    # deliberadamente sem sintese — stats.total ("120") nao e mais renderizado
    # aqui para nao reintroduzir texto nao literal na resposta de fallback.
    out = TemplateRenderer().render(_ctx())
    assert "correia" in out and "Doc4.pdf" in out
    assert "Afrouxar os parafusos do motor" in out


def test_router_degrades_to_fallback():
    outcome = Router(primary=BoomRenderer(), fallback=TemplateRenderer()).render(_ctx())
    assert outcome.degraded is True
    assert outcome.renderer == "template"
    assert "correia" in outcome.text


def test_ollama_renderer_defaults_reach_httpx(monkeypatch):
    from app.llm.ollama_adapter import OllamaRenderer

    captured = _capture_ollama_post(monkeypatch)
    OllamaRenderer("http://x:11434", "qwen2.5:7b-instruct").render(_ctx())
    assert captured["timeout"] == 300.0
    assert captured["json"]["options"]["num_ctx"] == 8192
    # opcoes existentes preservadas (reprodutibilidade)
    assert captured["json"]["options"]["temperature"] == 0
    assert captured["json"]["options"]["seed"] == 42


def test_ollama_renderer_custom_limits_reach_httpx(monkeypatch):
    from app.llm.ollama_adapter import OllamaRenderer

    captured = _capture_ollama_post(monkeypatch)
    OllamaRenderer("http://x:11434", "m", timeout=42.0, num_ctx=2048).render(_ctx())
    assert captured["timeout"] == 42.0
    assert captured["json"]["options"]["num_ctx"] == 2048
