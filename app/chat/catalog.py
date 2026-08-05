"""Vocabulario curado do operador.

O casamento e literal e sem fuzzy matching (ver app/chat/normalization.py):
um alias so e reconhecido se aparecer contiguo no texto normalizado. Por isso
o catalogo lista tambem as variantes com copula ("rotor esta inclinado" alem
de "rotor inclinado") — o operador escreve "o rotor esta inclinado", e sem a
variante nenhum alias casaria.
"""

from dataclasses import dataclass

FAMILY_ALIASES: dict[str, tuple[str, ...]] = {
    "rolamento_inner": (
        "rolamento_inner",
        "rolamento interno",
        "pista interna do rolamento",
        "pista interna",
        "inner bearing",
        "bearing interno",
        "inner race",
    ),
    "rolamento_outer": (
        "rolamento_outer",
        "rolamento externo",
        "pista externa do rolamento",
        "pista externa",
        "outer bearing",
        "outer race",
    ),
    "rolamento_ball": (
        "rolamento_ball",
        "esfera do rolamento",
        "elemento rolante",
        "elementos rolantes",
        "bearing ball",
    ),
    "rolamento_combination": (
        "rolamento_combination",
        "falha combinada no rolamento",
        "defeito combinado no rolamento",
    ),
    "desalinhado": (
        "desalinhado",
        "desalinhados",
        "desalinhamento",
        "desalinhmento",
        "eixos desalinhados",
    ),
    "desbalanceado": (
        "desbalanceado",
        "desbalanceados",
        "desbalanceamento",
        "desbalanceamnto",
        "rotor desbalanceado",
    ),
    "correia": ("correia", "correiaa", "belt"),
    "polia": ("polia", "poliaa", "pulley"),
    "cocked_rotor": (
        "cocked_rotor",
        "cocked rotor",
        "rotor inclinado",
        "rotor esta inclinado",
        "rotor torto",
        "rotor esta torto",
    ),
    "eccentric_rotor": (
        "eccentric_rotor",
        "eccentric rotor",
        "rotor excentrico",
        "rotor esta excentrico",
    ),
    "ventoinha": ("ventoinha", "ventilador de refrigeracao"),
    "falta_fase": ("falta_fase", "falta de fase", "perda de fase"),
    "normal": ("operacao normal", "estado normal"),
    "baseline": ("baseline", "linha de base"),
    "teste": ("estado de teste",),
    "acelerando": ("motor acelerando", "estado acelerando"),
    "motor_desligado": ("motor desligado", "equipamento desligado"),
}


@dataclass(frozen=True)
class SymptomRule:
    required_terms: frozenset[str]
    candidates: tuple[str, ...]


SYMPTOM_RULES: tuple[SymptomRule, ...] = (
    SymptomRule(
        frozenset({"chiado", "borracha"}),
        ("correia",),
    ),
    SymptomRule(
        frozenset({"vibrando", "barulho"}),
        (
            "desbalanceado",
            "desalinhado",
            "rolamento_inner",
            "rolamento_outer",
            "correia",
            "polia",
            "cocked_rotor",
        ),
    ),
    SymptomRule(
        frozenset({"vibracao", "axial"}),
        ("desalinhado", "cocked_rotor"),
    ),
)

COMPLETE_SCOPE_PHRASES = (
    "procedimento completo",
    "todas as etapas",
    "sem omitir",
    "passo a passo completo",
)

DOCUMENT_STATUS_PHRASES = (
    "existe documento",
    "documento cadastrado",
    "tem procedimento",
    "ha procedimento",
    "existe manual",
    "ha manual",
)

HISTORY_PHRASES = (
    "quantas ocorrencias",
    "numero de ocorrencias",
    "frequencia por dia",
    "no historico",
)
