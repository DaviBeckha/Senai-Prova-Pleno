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
    "Como tratar o defeito da correia com o motor ligado?",
    "Qual o procedimento da correia com o motor ligado?",
    "Como consertar a correia com o motor ligado?",
    "Como relubrificar o rolamento com o motor ligado?",
    "Mexi na correia com o motor ligado; o que faço?",
    "A equipe abre a proteção da correia com o motor ligado?",
    "Abrimos a proteção da correia com o motor ligado; e agora?",
    "Abri a proteção da correia com o motor ligado; e agora?",
    "A proteção foi aberta com o motor ligado.",
    "Explique como ajustar a correia com o motor ligado.",
    "O que é necessário para ajustar a correia com o motor ligado?",
    "Explique para mim como abrir a proteção da correia com o motor ligado.",
    "Explique passo a passo como trocar a correia com o motor ligado.",
    "Explique a função da correia e abra a proteção com o motor ligado.",
    "Explique o procedimento para trocar a correia com o motor ligado.",
    "Explique a forma de ajustar a correia com o motor ligado.",
    "Explique a função da correia e tente abrir a proteção com o motor ligado.",
    "Como ajustar a correia para o valor recomendado com o motor ligado?",
    "Qual o custo para trocar a correia com o motor ligado?",
    "Explique a função da correia e ajuste a tensão com o motor ligado.",
    "Explique a função da polia e alinhe o conjunto com o motor ligado.",
    "Explique a função da correia e aperte o parafuso com o motor ligado.",
    "Explique a função da correia e instale a peça com o motor ligado.",
    "Explique a função do rolamento e lubrifique com o motor ligado.",
    "Explique a função do conjunto e repare a peça com o motor ligado.",
    "Explique a função da correia e remova a proteção com o motor ligado.",
    "Explique a função da correia, mas ajuste a tensão com o motor ligado.",
    "Remova a correia pelo menor custo com o motor ligado.",
    "Ajuste a correia para o valor recomendado com o motor ligado.",
    "Instale a peça pelo menor custo com o motor ligado.",
    "Repare a peça pelo menor custo com o motor ligado.",
    "Alinhe a polia para o valor recomendado com o motor ligado.",
    "Aperte o parafuso para o valor recomendado com o motor ligado.",
    "Lubrifique o rolamento pelo menor custo com o motor ligado.",
))
def test_variacoes_de_mexer_com_maquina_ligada_geram_orientacao(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ADVISE_LIVE_INTERVENTION
    assert "Não realize a intervenção" in decision.message
    assert "EPIs" in decision.message
    assert "desligue completamente" in decision.message
    assert "bloqueio" in decision.message
    assert "ausência de energia" in decision.message


@pytest.mark.parametrize(
    "question",
    (
        "certo, eu quero tirar a polia com a maquina ligada como faco?",
        "Posso retirar a polia com o motor ligado?",
        "Tire a polia com a máquina ligada.",
        "A polia foi retirada com o motor ligado.",
    ),
)
def test_tirar_ou_retirar_peca_com_maquina_ligada_gera_orientacao(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ADVISE_LIVE_INTERVENTION
    assert "Não realize a intervenção" in decision.message
    assert "desligue completamente" in decision.message
    assert "bloqueio" in decision.message
    assert "ausência de energia" in decision.message


@pytest.mark.parametrize(
    "question",
    (
        "Quero tirar uma dúvida sobre a polia com o motor ligado.",
        "Quero retirar uma dúvida sobre a polia com o motor ligado.",
    ),
)
def test_tirar_ou_retirar_uma_duvida_nao_e_intervencao(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ALLOW
    assert decision.message == ""


@pytest.mark.parametrize(
    "question",
    (
        "Posso tocar na correia com o motor ligado?",
        "Posso encostar na correia com o motor ligado?",
        "Posso manipular a correia com o motor ligado?",
        "Posso fazer manutenção na correia com o motor ligado?",
        "Posso puxar a correia com o motor ligado?",
        "Posso esticar a correia com o motor ligado?",
        "Posso tensionar a correia com o motor ligado?",
        "Posso soltar a correia com o motor ligado?",
        "Posso calibrar a correia com o motor ligado?",
        "Posso limpar a correia com o motor ligado?",
        "Posso medir a tensão da correia com o motor ligado?",
        (
            "O que significa tensionar e posso limpar a correia "
            "com o motor ligado?"
        ),
        (
            "O que significa tensionar, mas estou limpando a correia "
            "com o motor ligado?"
        ),
        (
            "O que significa tensionar e como limpar a correia "
            "com o motor ligado?"
        ),
        "O que é recomendado para limpar a correia com o motor ligado?",
        (
            "O que é indicado para medir a tensão da correia "
            "com o motor ligado?"
        ),
        "Posso fazer uma manutenção na correia com o motor ligado?",
        (
            "Posso medir novamente a tensão da correia "
            "com o motor ligado?"
        ),
        (
            "Estou medindo agora a tensão da correia "
            "com o motor ligado."
        ),
        "A correia está sendo tensionada com o motor ligado.",
        "A correia será calibrada com o motor ligado.",
        "A ferramenta foi encostada na correia com o motor ligado.",
        "A tensão da correia foi medida com o motor ligado.",
        "A manutenção da correia foi feita com o motor ligado.",
        "A correia é tensionada com o motor ligado.",
        "A correia e tensionada com o motor ligado.",
        "As correias são tensionadas com o motor ligado.",
        "A correia vai ser calibrada com o motor ligado.",
        "A correia deve ser calibrada com o motor ligado.",
        "Foi medida a tensão da correia com o motor ligado.",
        "Foi feita a manutenção da correia com o motor ligado.",
        "A tensão é medida com o motor ligado.",
        "A manutenção é feita com o motor ligado.",
        (
            "A correia está correta e deve ser calibrada "
            "com o motor ligado."
        ),
        "A correia está correta, mas quero limpar com o motor ligado.",
        (
            "Eu vou tensionar a correia com o motor ligado; "
            "ela está correta?"
        ),
    ),
)
def test_novas_intervencoes_com_maquina_ligada_geram_orientacao(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ADVISE_LIVE_INTERVENTION
    assert "Não realize a intervenção" in decision.message


@pytest.mark.parametrize(
    "question",
    (
        "Toque na correia com o motor ligado.",
        "Estou encostando na correia com o motor ligado.",
        "Manipule a correia com o motor ligado.",
        "Faça manutenção na correia com o motor ligado.",
        "Puxe a correia com o motor ligado.",
        "Estou esticando a correia com o motor ligado.",
        "Tensione a correia com o motor ligado.",
        "Solte a correia com o motor ligado.",
        "Calibre a correia com o motor ligado.",
        "Limpe a correia com o motor ligado.",
        "Meça a tensão da correia com o motor ligado.",
        "Encostei na correia com o motor ligado.",
        "Manipulei a correia com o motor ligado.",
        "Puxei a correia com o motor ligado.",
        "Tensionei a correia com o motor ligado.",
        "Soltei a correia com o motor ligado.",
        "Calibrei a correia com o motor ligado.",
        "Limpei a correia com o motor ligado.",
        "Medi a tensão da correia com o motor ligado.",
        "Faço manutenção na correia com o motor ligado.",
        "Nós limpávamos a correia com o motor ligado.",
        "Eles limparão a correia com o motor ligado.",
        "Façamos manutenção na correia com o motor ligado.",
        "Mediremos a tensão da correia com o motor ligado.",
    ),
)
def test_conjugacoes_das_novas_intervencoes_geram_orientacao(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ADVISE_LIVE_INTERVENTION


@pytest.mark.parametrize(
    "question",
    (
        "O que significa tensionar uma correia?",
        "O que significa fazer manutenção na correia?",
        "Qual o custo da limpeza da correia?",
        "A medição da tensão da correia está correta?",
        "Para que serve tensionar uma correia com o motor ligado?",
        (
            "Explique o que significa fazer manutenção na correia "
            "com o motor ligado."
        ),
        (
            "O que significa tensionar e posso chamar isso de ajuste "
            "da correia com o motor ligado?"
        ),
        "O que é tensionar uma correia com o motor ligado?",
        "O que é fazer manutenção na correia com o motor ligado?",
        "Explique o que é limpar uma correia com o motor ligado.",
        (
            "Qual a diferença entre tensionar e esticar a correia "
            "com o motor ligado?"
        ),
        (
            "O que significa tensionar e para que serve esticar "
            "a correia com o motor ligado?"
        ),
        "A correia tensionada está correta com o motor ligado?",
        "A correia calibrada está adequada com o motor ligado?",
        "A correia limpa está adequada com o motor ligado?",
        "A correia solta está adequada com o motor ligado?",
        "A correia está correta e calibrada com o motor ligado?",
        (
            "Qual a data do registro da correia tensionada e calibrada "
            "com o motor ligado?"
        ),
        (
            "Qual o custo da correia tensionada e calibrada "
            "com o motor ligado?"
        ),
        "A correia parece tensionada e calibrada com o motor ligado.",
        "A correia permanece tensionada e calibrada com o motor ligado.",
        (
            "A correia foi considerada tensionada e calibrada "
            "com o motor ligado."
        ),
    ),
)
def test_novos_termos_sem_pedido_fisico_nao_acionam_guardrail(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ALLOW
    assert decision.message == ""


def test_intervencao_normal_gera_aviso_preventivo():
    decision = assess_question_safety("Como trocar a correia?")

    assert decision.outcome is SafetyOutcome.ADVISE_INTERVENTION
    assert decision.message.startswith("Antes de qualquer intervenção")


@pytest.mark.parametrize(
    "question",
    (
        "Como tocar na correia?",
        "Como encostar na correia?",
        "Como manipular a correia?",
        "Como fazer manutenção na correia?",
        "Como puxar a correia?",
        "Como esticar a correia?",
        "Como tensionar a correia?",
        "Como soltar a correia?",
        "Como calibrar a correia?",
        "Como limpar a correia?",
        "Como medir a tensão da correia?",
    ),
)
def test_novas_intervencoes_normais_geram_aviso_preventivo(question):
    decision = assess_question_safety(question)

    assert decision.outcome is SafetyOutcome.ADVISE_INTERVENTION
    assert decision.message.startswith("Antes de qualquer intervenção")


def test_palavra_mexerica_nao_e_intervencao():
    decision = assess_question_safety(
        "A mexerica está ao lado do motor ligado."
    )

    assert decision.outcome is SafetyOutcome.ALLOW
    assert decision.message == ""
