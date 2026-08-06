import pytest

from app.guardrails.safety import SafetyOutcome, assess_question_safety


@pytest.mark.parametrize("question", (
    "Posso mexer na correia com o motor ligado?",
    "Mexa na polia com a máquina ligada.",
    "Estou mexendo na peça com o equipamento funcionando.",
    "Ele mexeu no conjunto sem parar o motor.",
    "Nós mexemos na correia com o motor ligado.",
    "Eles mexeram na polia com a máquina ligada.",
    "Posso alinhar a polia com o motor ligado?",
    "Posso lubrificar o rolamento com o motor ligado?",
    "Posso reapertar os parafusos com o motor ligado?",
    "Posso reparar o conjunto com o motor ligado?",
))
def test_variacoes_de_mexer_com_maquina_ligada_geram_orientacao(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ADVISE_LIVE_INTERVENTION
    assert "Não realize a intervenção" in decision.message
    assert "EPIs" in decision.message
    assert "desligue completamente" in decision.message
    assert "bloqueio" in decision.message
    assert "ausência de energia" in decision.message


def test_intervencao_normal_gera_aviso_preventivo():
    decision = assess_question_safety("Como trocar a correia?")

    assert decision.outcome is SafetyOutcome.ADVISE_INTERVENTION
    assert decision.message.startswith("Antes de qualquer intervenção")


def test_palavra_mexerica_nao_e_intervencao():
    decision = assess_question_safety(
        "A mexerica está ao lado do motor ligado."
    )

    assert decision.outcome is SafetyOutcome.ALLOW
    assert decision.message == ""


@pytest.mark.parametrize("question", (
    "Existe documento de ajuste da correia para motor ligado?",
    "Quantos ajustes ocorreram com o motor ligado no histórico?",
    "Existe documento de instalação da correia com o equipamento ligado?",
    "Quantas substituições ocorreram com a máquina ligada?",
))
def test_consulta_nominal_nao_e_tratada_como_intervencao(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ALLOW
    assert decision.message == ""
