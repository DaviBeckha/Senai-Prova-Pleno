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
