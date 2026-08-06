import pytest
from app.data.labels import (
    DISPLAY_LABELS,
    FAULT_FAMILIES,
    STATE_FAMILIES,
    display_label,
    normalize_label,
)

CASES = [
    ("normal", "normal", "estado"),
    ("normal_2", "normal", "estado"),
    ("normla_carga_3_3", "normal", "estado"),          # typo real
    ("new_normal_6", "normal", "estado"),
    ("motor_desligado", "motor_desligado", "estado"),
    ("mortor_desligado_novo", "motor_desligado", "estado"),  # typo real
    ("new_baseline", "baseline", "estado"),
    ("new_tes", "teste", "estado"),                     # typo real
    ("acelerando", "acelerando", "estado"),
    ("rolamento_inner_2", "rolamento_inner", "falha"),
    ("new_rolamento_comb_3", "rolamento_combination", "falha"),
    ("rolamento_outer_adxl_0", "rolamento_outer", "falha"),
    ("rolamento_ball_pos_2", "rolamento_ball", "falha"),
    ("cocked_rotor_2_pos_2", "cocked_rotor", "falha"),
    ("cockecocked_adxl_0", "cocked_rotor", "falha"),    # typo real
    ("new_cocked_1", "cocked_rotor", "falha"),
    ("desbalanceado_1parafuso", "desbalanceado", "falha"),
    ("desbalanceamento", "desbalanceado", "falha"),
    ("desabalanceado_3", "desbalanceado", "falha"),     # typo real
    ("ddesbalanceado_adxl_0", "desbalanceado", "falha"),
    ("dedesbalanceado_adxl_1", "desbalanceado", "falha"),
    ("desbanlanceado_carga_3_2", "desbalanceado", "falha"),
    ("new_desabanceado_1", "desbalanceado", "falha"),
    ("desalinhado_2", "desalinhado", "falha"),
    ("new_desalinhado_4", "desalinhado", "falha"),
    ("correia_2", "correia", "falha"),
    ("polia_2", "polia", "falha"),
    ("eccentric_rotor_pos_2", "eccentric_rotor", "falha"),
    ("new_eccentric_3", "eccentric_rotor", "falha"),
    ("eccentric_adxl_0", "eccentric_rotor", "falha"),
    ("ventoinha_3", "ventoinha", "falha"),
    ("new_falta_fase_2", "falta_fase", "falha"),
]

@pytest.mark.parametrize("raw,family,kind", CASES)
def test_normalize(raw, family, kind):
    info = normalize_label(raw)
    assert info.family == family
    assert info.kind == kind

def test_unknown_label():
    info = normalize_label("banana_frita_9")
    assert info.family == "desconhecido"
    assert info.kind == "desconhecido"


# Adversarial regression tests: ensure typos of state names never become faults,
# and typos of fault names never become states
ADVERSARIAL_CASES = [
    # State typos that should NOT become faults (estado or desconhecido only)
    ("adelerando", "desconhecido", "desconhecido"),        # typo of acelerando
    ("acdelerando", "desconhecido", "desconhecido"),       # typo of acelerando
    ("motor_deslegado", "desconhecido", "desconhecido"),   # typo of motor_desligado
    ("motor_desleigado", "desconhecido", "desconhecido"),  # typo of motor_desligado
    # Fault typos that should NOT become states
    ("rolamento_outes", "desconhecido", "desconhecido"),   # typo of rolamento_outer
    ("tesbalanceado", "desconhecido", "desconhecido"),     # typo mixing teste + balanceado
]

@pytest.mark.parametrize("raw,family,kind", ADVERSARIAL_CASES)
def test_adversarial_regression(raw, family, kind):
    """Ensure state typos never match fault patterns and vice versa."""
    info = normalize_label(raw)
    # Critical: state names should NEVER be misclassified as fault
    if kind == "estado":
        assert info.kind != "falha", f"{raw} was misclassified as fault (family={info.family})"
    # Critical: fault names should NEVER be misclassified as state
    elif kind == "falha":
        assert info.kind != "estado", f"{raw} was misclassified as state (family={info.family})"
    # Final check
    assert info.family == family
    assert info.kind == kind


# --- Camada de apresentacao: rotulo em portugues ---------------------------
#
# Os slugs de familia sao chave de dominio (Document.family, SensorReading.family,
# doc_family do RAG, allowlist do POST /documentos). A traducao vive em
# DISPLAY_LABELS como camada de apresentacao — nunca como renomeacao.


def test_toda_familia_conhecida_tem_rotulo_em_portugues():
    """Teste de completude: familia nova sem rotulo quebra aqui, nao na tela.

    display_label degrada para family.replace("_", " ") quando falta a entrada,
    o que evita 500 mas deixaria "cocked rotor" no meio de uma frase em
    portugues — exatamente o vazamento que DISPLAY_LABELS existe para fechar.
    """
    for family in FAULT_FAMILIES | STATE_FAMILIES:
        assert family in DISPLAY_LABELS, f"familia sem rotulo em portugues: {family}"


def test_nenhum_rotulo_carrega_underscore_ou_slug_cru():
    for family, rotulo in DISPLAY_LABELS.items():
        assert "_" not in rotulo, f"{family}: rotulo ainda com underscore ({rotulo})"
        assert rotulo != family or family in {"correia", "polia", "normal", "teste"}, (
            f"{family}: rotulo identico ao slug"
        )


def test_display_label_traduz_os_slugs_em_ingles():
    # As seis familias que apareciam em ingles nos graficos e no chat.
    assert display_label("rolamento_inner") == "Rolamento — pista interna"
    assert display_label("rolamento_outer") == "Rolamento — pista externa"
    assert display_label("rolamento_ball") == "Rolamento — esferas"
    assert display_label("rolamento_combination") == "Rolamento — falha combinada"
    assert display_label("cocked_rotor") == "Rotor desalinhado no eixo"
    assert display_label("eccentric_rotor") == "Rotor excêntrico"


def test_display_label_degrada_sem_levantar_para_familia_desconhecida():
    # Um rotulo imperfeito na tela e preferivel a um 500 no diagnostico.
    assert display_label("familia_que_nao_existe") == "familia que nao existe"
