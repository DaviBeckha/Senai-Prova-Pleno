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
