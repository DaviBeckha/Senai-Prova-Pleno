from dataclasses import replace

from app.chat.context import ChatContext
from app.core.maintenance_intent import ContentRole
from app.llm.base import DiagnosisContext
from app.llm.router import Router
from app.llm.template_fallback import TemplateRenderer
from app.rag.chunking import Chunk
from app.rag.search import EvidenceItem, FamilyEvidence, RetrievalBundle
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


def _ventoinha_ctx() -> ChatContext:
    chunks = (
        Chunk(
            doc_family="ventoinha",
            source="ventoinha--procedimento_de_manutencao_da_ventoinha_v1.pdf",
            section="3. Sintomas e diagnóstico",
            text=(
                "3. Sintomas e diagnóstico\n"
                "Os principais sinais são: • Ruído anormal durante a operação. "
                "• Vibração excessiva."
            ),
            section_path=("3. Sintomas e diagnóstico",),
            content_role=ContentRole.DIAGNOSIS,
            document_order=0,
        ),
        Chunk(
            doc_family="ventoinha",
            source="ventoinha--procedimento_de_manutencao_da_ventoinha_v1.pdf",
            section="4. Inspeção da ventoinha",
            text=(
                "4. Inspeção da ventoinha\n"
                "Com o equipamento desligado: • Inspecionar visualmente todas "
                "as pás. • Verificar folga excessiva."
            ),
            section_path=("4. Inspeção da ventoinha",),
            content_role=ContentRole.INSPECTION,
            document_order=1,
        ),
        Chunk(
            doc_family="ventoinha",
            source="ventoinha--procedimento_de_manutencao_da_ventoinha_v1.pdf",
            section="6. Alinhamento",
            text=(
                "6. Alinhamento\n"
                "Corrigir a posição dos elementos de fixação. Página 2"
            ),
            section_path=("6. Alinhamento",),
            content_role=ContentRole.ALIGNMENT,
            document_order=2,
        ),
    )
    items = tuple(
        EvidenceItem(f"ventoinha:E{position}", "ventoinha", chunk, 0.9)
        for position, chunk in enumerate(chunks, start=1)
    )
    return ChatContext(
        question="como corrigir a ventoinha?",
        families=("ventoinha",),
        stats_by_family={},
        retrieval=RetrievalBundle((FamilyEvidence("ventoinha", items, False),)),
        limitations=("O documento não informa o torque de reaperto.",),
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


def test_template_renders_evidence_without_internal_metadata():
    out = TemplateRenderer().render(_ctx())

    assert "### Orientação encontrada para Correia" in out
    assert "Afrouxar os parafusos do motor" in out
    assert "Doc4.pdf" not in out
    assert "correia:E1" not in out


def test_template_organiza_evidencia_sem_metadados_internos():
    out = TemplateRenderer().render(_ventoinha_ctx())

    assert "### Orientação encontrada para Ventoinha" in out
    assert "#### Sintomas e diagnóstico" in out
    assert "#### Inspeção" in out
    assert "#### Alinhamento" in out
    assert "- Ruído anormal durante a operação." in out
    assert "- Inspecionar visualmente todas as pás." in out
    assert "Página 2" not in out
    assert "ventoinha:E1" not in out
    assert "procedimento_de_manutencao" not in out
    assert "### Limitações" in out
    assert "O documento não informa o torque de reaperto." in out


def test_template_preserva_conteudo_geral_em_secao_previsivel():
    chunk = Chunk(
        doc_family="ventoinha",
        source="ventoinha.pdf",
        section="1. Objetivo",
        text="1. Objetivo\nOrientar a inspeção da ventoinha.",
        section_path=("1. Objetivo",),
        content_role=ContentRole.GENERAL,
    )
    item = EvidenceItem("ventoinha:E1", "ventoinha", chunk, 0.9)
    context = replace(
        _ventoinha_ctx(),
        retrieval=RetrievalBundle((
            FamilyEvidence("ventoinha", (item,), False),
        )),
    )

    out = TemplateRenderer().render(context)

    assert "#### Informações complementares" in out
    assert "Orientar a inspeção da ventoinha." in out


def test_router_degrades_to_fallback():
    outcome = Router(primary=BoomRenderer(), fallback=TemplateRenderer()).render(_ctx())
    assert outcome.degraded is True
    assert outcome.renderer == "template"
    assert "Correia" in outcome.text


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
