import json

from app.chat.analyzer import analyze_question
from app.chat.context import ChatContext
from app.core.maintenance_intent import ContentRole
from app.llm.adequacy import (
    validate_answer_adequacy,
    validate_evidence_adequacy,
)
from app.llm.contracts import GroundedDraft, GroundedStep
from app.llm.router import Router
from app.llm.template_fallback import TemplateRenderer
from app.rag.chunking import Chunk
from app.rag.search import EvidenceItem, FamilyEvidence, RetrievalBundle


def _item(
    family: str,
    role: ContentRole,
    text: str,
    position: int = 1,
) -> EvidenceItem:
    chunk = Chunk(
        family,
        f"{family}.md",
        role.value,
        text,
        (role.value,),
        role,
        position,
    )
    return EvidenceItem(f"{family}:E{position}", family, chunk, 0.9)


def _bundle(*items: EvidenceItem) -> RetrievalBundle:
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in items:
        grouped.setdefault(item.family, []).append(item)
    return RetrievalBundle(tuple(
        FamilyEvidence(family, tuple(found), complete=False)
        for family, found in grouped.items()
    ))


def _ctx(question: str, bundle: RetrievalBundle) -> ChatContext:
    analysis = analyze_question(question)
    return ChatContext(
        question=question,
        families=analysis.explicit_families,
        stats_by_family={},
        retrieval=bundle,
        requested_actions=analysis.requested_actions,
        requires_safety=analysis.requires_safety,
        conditions=analysis.conditions,
        safety_only=analysis.safety_only,
    )


def test_evidencia_de_substituicao_nao_responde_correcao_sem_dano():
    analysis = analyze_question("Como corrigir uma correia frouxa?")
    bundle = _bundle(_item(
        "correia",
        ContentRole.REPLACEMENT,
        "Remover a correia antiga.",
    ))

    errors = validate_evidence_adequacy(analysis, bundle)

    assert any("repair" in error for error in errors)


def test_pedido_explicito_de_seguranca_exige_evidencia_de_seguranca():
    analysis = analyze_question(
        "Quais verificacoes de seguranca devo fazer antes de mexer na correia?"
    )
    bundle = _bundle(_item(
        "correia",
        ContentRole.VALIDATION,
        "Verificar a estabilidade da correia.",
    ))

    errors = validate_evidence_adequacy(analysis, bundle)

    assert any("segurança" in error for error in errors)


def test_evidencia_precisa_cobrir_todas_as_familias_solicitadas():
    analysis = analyze_question("Como corrigir correia e polia?")
    bundle = _bundle(_item(
        "correia",
        ContentRole.ADJUSTMENT,
        "Ajustar a tensão da correia.",
    ))

    errors = validate_evidence_adequacy(analysis, bundle)

    assert any("polia" in error for error in errors)


def test_resposta_so_com_limitacoes_e_inadequada():
    ctx = _ctx(
        "Como corrigir uma correia frouxa?",
        _bundle(_item(
            "correia",
            ContentRole.ADJUSTMENT,
            "Ajustar a tensão da correia.",
        )),
    )

    errors = validate_answer_adequacy(
        GroundedDraft(unanswered=["A evidência não informa o procedimento."]),
        ctx,
    )

    assert any("nenhuma ação" in error for error in errors)


def test_resposta_precisa_executar_o_verbo_solicitado():
    diagnosis = _item(
        "correia",
        ContentRole.DIAGNOSIS,
        "Identificar as causas do escorregamento.",
    )
    ctx = _ctx(
        "Como corrigir uma correia frouxa?",
        _bundle(diagnosis),
    )
    draft = GroundedDraft(steps=[GroundedStep(
        action="Identificar as causas do escorregamento.",
        family="correia",
        evidence_id=diagnosis.evidence_id,
        quote=diagnosis.chunk.text,
    )])

    errors = validate_answer_adequacy(draft, ctx)

    assert any("repair" in error for error in errors)


def test_papel_do_chunk_nao_mascara_acao_fraca_na_resposta():
    adjustment = _item(
        "correia",
        ContentRole.ADJUSTMENT,
        "Verificar os parafusos antes de ajustar a tensão.",
    )
    ctx = _ctx(
        "Como corrigir uma correia frouxa?",
        _bundle(adjustment),
    )
    draft = GroundedDraft(steps=[GroundedStep(
        action="Verificar os parafusos.",
        family="correia",
        evidence_id=adjustment.evidence_id,
        quote=adjustment.chunk.text,
    )])

    errors = validate_answer_adequacy(draft, ctx)

    assert any("repair" in error for error in errors)


def test_resposta_precisa_cobrir_todas_as_familias():
    belt = _item(
        "correia",
        ContentRole.ADJUSTMENT,
        "Ajustar a tensão da correia.",
    )
    pulley = _item(
        "polia",
        ContentRole.ALIGNMENT,
        "Alinhar a polia.",
    )
    ctx = _ctx("Como corrigir correia e polia?", _bundle(belt, pulley))
    draft = GroundedDraft(steps=[GroundedStep(
        action="Ajustar a tensão da correia.",
        family="correia",
        evidence_id=belt.evidence_id,
        quote=belt.chunk.text,
    )])

    errors = validate_answer_adequacy(draft, ctx)

    assert any("polia" in error for error in errors)


class _OnlyLimitationsRenderer:
    name = "only-limitations"

    def render(self, ctx):
        return json.dumps({
            "steps": [],
            "unanswered": ["A evidência não informa como corrigir."],
        })


def test_router_marca_resposta_so_com_limitacoes_como_insuficiente():
    ctx = _ctx(
        "Como corrigir uma correia frouxa?",
        _bundle(_item(
            "correia",
            ContentRole.ADJUSTMENT,
            "Ajustar a tensão da correia.",
        )),
    )

    outcome = Router(
        _OnlyLimitationsRenderer(),
        TemplateRenderer(),
    ).render(ctx)

    assert outcome.answer_status == "insufficient_evidence"
    assert outcome.degraded is True
    assert any("nenhuma ação" in error for error in outcome.validation_errors)
