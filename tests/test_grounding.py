import pytest

from app.chat.context import ChatContext
from app.llm.contracts import GroundedDraft, GroundedStep
from app.llm.grounding import (
    GroundingValidationError,
    parse_grounded_draft,
    validate_grounded_draft,
)
from app.rag.chunking import Chunk
from app.rag.search import EvidenceItem, FamilyEvidence, RetrievalBundle


class FakeCtx:
    """Contexto mínimo aceito por evidence_items_for (caminho DiagnosisContext)."""

    def __init__(self, family="correia", chunks=None):
        self.family = family
        self.chunks = chunks if chunks is not None else [
            Chunk("correia", "Doc4.pdf", "9.1 Correia Frouxa",
                  "Afrouxar os parafusos do motor. Aplicar a tensao recomendada de 45 N."),
        ]


def _step(**overrides):
    base = dict(action="Afrouxar os parafusos do motor",
                family="correia", evidence_id="correia:E1",
                quote="Afrouxar os parafusos do motor")
    base.update(overrides)
    return GroundedStep(**base)


# --- Casos do parser ---------------------------------------------------

def test_json_invalido_levanta_erro():
    with pytest.raises(GroundingValidationError):
        parse_grounded_draft("isso nao e json {")


def test_json_com_cerca_markdown_e_aceito():
    raw = '```json\n{"steps": [], "unanswered": ["sem evidencia"]}\n```'
    draft = parse_grounded_draft(raw)
    assert draft.unanswered == ["sem evidencia"]


def test_schema_errado_levanta_erro():
    with pytest.raises(GroundingValidationError):
        parse_grounded_draft('{"steps": [{"acao_errada": "x"}]}')


# --- Casos do validador --------------------------------------------------

def test_evidence_id_inexistente():
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(evidence_id="correia:E99")]), FakeCtx())
    assert any("evidência desconhecida" in e for e in errors)


def test_familia_incompativel_com_evidencia():
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(family="polia", evidence_id="E1")]), FakeCtx())
    assert any("família não corresponde" in e for e in errors)


def test_citacao_inexistente_no_documento():
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(quote="Substituir o rolamento imediatamente")]),
        FakeCtx())
    assert any("citação não encontrada" in e for e in errors)


def test_numero_inventado_na_acao():
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Aplicar a tensao recomendada de 90 N",
            quote="Aplicar a tensao recomendada de 45 N.")]), FakeCtx())
    assert any("número sem suporte" in e for e in errors)


def test_acao_sem_suporte_lexical():
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Realizar balanceamento dinamico completo do rotor principal",
            quote="Afrouxar os parafusos do motor")]), FakeCtx())
    assert any("suporte lexical" in e for e in errors)


def test_rascunho_vazio_e_invalido():
    errors = validate_grounded_draft(GroundedDraft(), FakeCtx())
    assert any("rascunho vazio" in e for e in errors)


def test_rascunho_so_com_unanswered_e_valido():
    errors = validate_grounded_draft(
        GroundedDraft(unanswered=["a evidencia nao cobre o torque exato"]), FakeCtx())
    assert errors == ()


def test_numero_por_extenso_diverge_da_citacao_e_detectado():
    # Sem conversao, findall("noventa N") devolve conjunto VAZIO e vazio e
    # subconjunto de tudo: a conferencia numerica passava vacuamente.
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Aplicar a tensao recomendada de noventa N",
            quote="Aplicar a tensao recomendada de 45 N.")]), FakeCtx())
    assert any("número sem suporte" in e for e in errors)


def test_numero_por_extenso_que_confere_com_a_citacao_e_aceito():
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Aplicar a tensao recomendada de noventa N",
            quote="Aplicar a tensao recomendada de 90 N.",
            evidence_id="correia:E1")]),
        FakeCtx(chunks=[Chunk(
            "correia", "Doc4.pdf", "9.1 Correia Frouxa",
            "Aplicar a tensao recomendada de 90 N.")]))
    assert errors == ()


def test_numero_composto_por_extenso_e_convertido():
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Aplicar a tensao recomendada de quarenta e cinco N",
            quote="Aplicar a tensao recomendada de 45 N.")]), FakeCtx())
    assert errors == ()


def test_numeral_por_extenso_sem_unidade_nao_e_conferido():
    # "dois parafusos" nao e valor de engenharia: exigir que a citacao
    # repetisse o numeral transformaria linguagem natural em reprovacao.
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Afrouxar os dois parafusos do motor",
            quote="Afrouxar os parafusos do motor")]), FakeCtx())
    assert errors == ()


def test_valor_tecnico_em_unanswered_e_sinalizado():
    # `unanswered` e renderizado sob "### Limitacoes", sem citacao e sem fonte
    # ao lado. Um valor de engenharia ali nao tem contra o que ser conferido —
    # e chega ao operador na secao onde ele baixa a guarda.
    errors = validate_grounded_draft(
        GroundedDraft(unanswered=[
            "aplique 200 N de torque no parafuso mesmo sem evidência"
        ]), FakeCtx())
    assert any("valor técnico sem evidência" in e for e in errors)


def test_unanswered_que_nao_declara_ausencia_nao_invalida_o_rascunho():
    # Texto real capturado do qwen2.5:7b-instruct rodando contra os documentos
    # deste projeto: o modelo usa `unanswered` para ecoar o ASSUNTO pendente
    # ("Como corrigir um rotor inclinado" era a propria pergunta), nao para
    # afirmar a ausencia. Exigir marca de ausencia reprovava o rascunho INTEIRO
    # por isso: em 3 de 4 casos medidos, uma resposta com passo ja aprovado nas
    # seis conferencias caiu para template extrativo por defeito de forma em
    # outro campo. A pena era desproporcional ao defeito.
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step()],
                      unanswered=["Como corrigir um rotor inclinado"]),
        FakeCtx())
    assert errors == ()


def test_unanswered_com_numero_sem_unidade_continua_valido():
    errors = validate_grounded_draft(
        GroundedDraft(unanswered=[
            "a evidência não cobre a seção 9.2 do documento"
        ]), FakeCtx())
    assert errors == ()


def test_abreviacao_e1_resolve_sem_ambiguidade():
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(evidence_id="E1")]), FakeCtx())
    assert errors == ()


def test_negacao_sem_suporte_quando_acao_nega_e_evidencia_afirma():
    # Bypass real: a acao inverte o sentido da citacao ("Nao aplicar...")
    # mas o suporte lexical (0,83) ainda passa, porque a citacao contem quase
    # todas as palavras da acao — a unica que falta e justamente "nao".
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Não aplicar a tensao recomendada de 45 N",
            quote="Aplicar a tensao recomendada de 45 N.")]), FakeCtx())
    assert any("negação sem suporte" in e for e in errors)


def test_negacao_sem_suporte_quando_evidencia_nega_e_acao_afirma():
    # Sentido inverso: a citacao nega, a acao afirma. O suporte lexical NAO
    # pega este caso — o denominador da razao e o numero de tokens da ACAO, e
    # a acao (sem "nao") tem 100% de suporte na citacao (que so tem uma
    # palavra a mais).
    ctx = FakeCtx(chunks=[Chunk(
        "correia", "Doc4.pdf", "9.1 Correia Frouxa",
        "Não aplicar graxa em excesso na correia.")])
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Aplicar graxa em excesso na correia",
            quote="Não aplicar graxa em excesso na correia.")]), ctx)
    assert any("negação sem suporte" in e for e in errors)


def test_negacao_presente_nos_dois_lados_continua_valida():
    # Caso legitimo: acao e citacao concordam, as duas negando. Nao pode virar
    # erro so por conter "nao" — a regra so reprova quando os lados divergem.
    ctx = FakeCtx(chunks=[Chunk(
        "correia", "Doc4.pdf", "9.1 Correia Frouxa",
        "Não aplicar graxa em excesso na correia.")])
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(
            action="Não aplicar graxa em excesso na correia",
            quote="Não aplicar graxa em excesso na correia.")]), ctx)
    assert errors == ()


def test_abreviacao_ambigua_entre_familias_e_rejeitada():
    # Contexto de chat com DUAS familias, cada uma trazendo um item "E1" —
    # a familia declarada no passo ("correia", default de _step) nao bate com
    # nenhuma das duas, entao a resolucao por sufixo encontra 2 candidatos e
    # tem de recusar em vez de adivinhar qual "E1" o passo quis dizer.
    bundle = RetrievalBundle(families=(
        FamilyEvidence(
            "polia",
            (EvidenceItem("polia:E1", "polia", Chunk(
                "polia", "Doc5.pdf", "3.2 Excentricidade",
                "Verificar a excentricidade da polia."), 0.9),),
            complete=True,
        ),
        FamilyEvidence(
            "rolamento_outer",
            (EvidenceItem("rolamento_outer:E1", "rolamento_outer", Chunk(
                "rolamento_outer", "Doc1.pdf", "2.1 Pista Externa",
                "Substituir o rolamento com defeito na pista externa."), 0.9),),
            complete=True,
        ),
    ))
    ctx = ChatContext(
        question="como corrigir a falha reportada?",
        families=("polia", "rolamento_outer"),
        stats_by_family={},
        retrieval=bundle,
    )
    errors = validate_grounded_draft(
        GroundedDraft(steps=[_step(evidence_id="E1")]), ctx)
    assert any("evidência desconhecida" in e for e in errors)
