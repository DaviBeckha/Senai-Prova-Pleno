import re
from dataclasses import dataclass

STATE_FAMILIES = {"normal", "baseline", "teste", "acelerando", "motor_desligado"}
FAULT_FAMILIES = {
    "rolamento_inner", "rolamento_outer", "rolamento_ball", "rolamento_combination",
    "desalinhado", "desbalanceado", "correia", "polia", "cocked_rotor",
    "eccentric_rotor", "ventoinha", "falta_fase",
}


@dataclass(frozen=True)
class LabelInfo:
    raw: str
    family: str
    kind: str


# Identificador interno -> nome que o operador le na tela e no texto gerado.
#
# Os slugs sao chave de dominio: aparecem em Document.family e
# SensorReading.family (banco), no filtro de secao do RAG (doc_family) e na
# allowlist _FAMILY_RE do POST /documentos. Renomea-los quebraria o banco, o
# indice e o contrato. Por isso a traducao vive AQUI, como camada de
# apresentacao, e nunca como renomeacao — quem persiste continua vendo
# "cocked_rotor", quem le a tela ve "Rotor desalinhado no eixo".
#
# Fonte unica: consumido por app/chat/responses.py (texto do chat),
# app/pipeline.py (mensagens de diagnostico) e GET /familias (vocabulario do
# dashboard). O teste de completude em tests/test_labels.py quebra se uma
# familia nova entrar em FAULT_FAMILIES/STATE_FAMILIES sem rotulo aqui.
DISPLAY_LABELS: dict[str, str] = {
    # Falhas
    "rolamento_inner": "Rolamento — pista interna",
    "rolamento_outer": "Rolamento — pista externa",
    "rolamento_ball": "Rolamento — esferas",
    "rolamento_combination": "Rolamento — falha combinada",
    "desalinhado": "Desalinhamento",
    "desbalanceado": "Desbalanceamento",
    "correia": "Correia",
    "polia": "Polia",
    "cocked_rotor": "Rotor desalinhado no eixo",
    "eccentric_rotor": "Rotor excêntrico",
    "ventoinha": "Ventoinha",
    "falta_fase": "Falta de fase",
    # Estados de operacao
    "normal": "Normal",
    "baseline": "Linha de base",
    "teste": "Teste",
    "acelerando": "Em aceleração",
    "motor_desligado": "Motor desligado",
    # Desfecho de normalize_label quando nenhuma regra casa
    "desconhecido": "Não identificado",
}


def display_label(family: str) -> str:
    """Rotulo em portugues de uma familia, com degradacao previsivel.

    Uma familia sem entrada em DISPLAY_LABELS cai no antigo comportamento de
    app/chat/responses.py::_display (troca "_" por espaco) em vez de levantar:
    um rotulo imperfeito na tela e preferivel a uma resposta de diagnostico
    que falha com 500. O teste de completude cobre o caso esperado; este
    fallback cobre o inesperado.
    """
    return DISPLAY_LABELS.get(family) or family.replace("_", " ")


_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"rolamento_inner"), "rolamento_inner"),
    (re.compile(r"rolamento_outer"), "rolamento_outer"),
    (re.compile(r"rolamento_ball"), "rolamento_ball"),
    (re.compile(r"rolamento_comb"), "rolamento_combination"),
    # desalinhado com tolerância a typos: desalinhado, desalinhamento
    (re.compile(r"desal[a-z]*inhad|desalinh"), "desalinhado"),
    # desbalanceado com regex apertada: exige d[d]?[a-z]*e[d]?[a-z]*s + (bal|aba|ban)
    # cobre: desbalanceado, desbalanceamento, desabalanceado, ddesbalanceado,
    # dedesbalanceado, desbanlanceado, desabanceado
    # NUNCA match em dele/desle/motor_deslegado/adelerando
    (re.compile(r"d[d]?[a-z]*e[d]?[a-z]*s[a-z]*(bal[a-z]*n|aba[a-z]*n|ban[a-z]*c)"), "desbalanceado"),
    (re.compile(r"correia"), "correia"),
    (re.compile(r"polia"), "polia"),
    (re.compile(r"cock"), "cocked_rotor"),          # cobre cockecocked
    (re.compile(r"eccentric"), "eccentric_rotor"),
    (re.compile(r"ventoinha"), "ventoinha"),
    (re.compile(r"falta_fase"), "falta_fase"),
    (re.compile(r"nor[a-z]*l"), "normal"),          # cobre normla
    (re.compile(r"baseline"), "baseline"),
    (re.compile(r"acelerando"), "acelerando"),
    (re.compile(r"mo[rt]+or_desligado"), "motor_desligado"),  # cobre mortor
    # tes colocada no fim: match apenas inicio/posição (^|_) e seguido de
    # t/fim/$/_: evita capturar rolamento_outes ou tesbalanceado
    (re.compile(r"(^|_)(new_)?tes(t|$|_)"), "teste"),
]


def normalize_label(raw: str) -> LabelInfo:
    text = raw.strip().lower()
    for pattern, family in _RULES:
        if pattern.search(text):
            kind = "estado" if family in STATE_FAMILIES else "falha"
            return LabelInfo(raw=raw, family=family, kind=kind)
    return LabelInfo(raw=raw, family="desconhecido", kind="desconhecido")
