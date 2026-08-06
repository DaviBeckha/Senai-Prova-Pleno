import re
from enum import StrEnum

from app.core.text import normalize_text


class MaintenanceAction(StrEnum):
    DIAGNOSE = "diagnose"
    INSPECT = "inspect"
    ADJUST = "adjust"
    ALIGN = "align"
    LUBRICATE = "lubricate"
    REPAIR = "repair"
    REPLACE = "replace"
    VALIDATE = "validate"


class ContentRole(StrEnum):
    SAFETY = "safety"
    DIAGNOSIS = "diagnosis"
    INSPECTION = "inspection"
    ADJUSTMENT = "adjustment"
    ALIGNMENT = "alignment"
    LUBRICATION = "lubrication"
    REPLACEMENT = "replacement"
    VALIDATION = "validation"
    GENERAL = "general"


_ACTION_PATTERNS = (
    (MaintenanceAction.INSPECT, re.compile(r"\b(?:inspecion\w*|verific\w*)\b")),
    (MaintenanceAction.ADJUST, re.compile(r"\b(?:ajust\w*|apert\w*|reapert\w*)\b")),
    (MaintenanceAction.ALIGN, re.compile(r"\b(?:alinh\w*)\b")),
    (MaintenanceAction.LUBRICATE, re.compile(r"\b(?:lubrific\w*|relubrific\w*)\b")),
    (
        MaintenanceAction.REPLACE,
        re.compile(r"\b(?:substitu\w*|troc\w*|troqu\w*)\b"),
    ),
    (MaintenanceAction.VALIDATE, re.compile(r"\b(?:valid\w*|confirm\w*|test\w*)\b")),
    (
        MaintenanceAction.DIAGNOSE,
        re.compile(r"\b(?:diagnostic\w*|identific\w*|causas?)\b"),
    ),
    (
        MaintenanceAction.REPAIR,
        re.compile(r"\b(?:corrij\w*|corrig\w*|repar\w*|trat\w*|procedimento)\b"),
    ),
)

_CONDITION_PATTERNS = {
    "dano": re.compile(r"\b(?:dano|danific\w*)\b"),
    "desgaste": re.compile(r"\b(?:desgast\w*)\b"),
    "trinca": re.compile(r"\b(?:trinca|trincas|rachadur\w*)\b"),
    "contaminacao": re.compile(r"\b(?:contamin\w*)\b"),
    "falha_estrutural": re.compile(r"\bfalha estrutural\b"),
}

_SAFETY_REQUEST = re.compile(
    r"\b(?:seguranca|deslig\w*|bloque\w*|etiquet\w*|"
    r"ausencia de energia|parada completa)\b"
)


def detect_actions(value: str) -> tuple[MaintenanceAction, ...]:
    normalized = normalize_text(value)
    actions = [
        action
        for action, pattern in _ACTION_PATTERNS
        if pattern.search(normalized)
    ]
    return tuple(dict.fromkeys(actions))


def detect_conditions(value: str) -> frozenset[str]:
    normalized = normalize_text(value)
    return frozenset(
        name
        for name, pattern in _CONDITION_PATTERNS.items()
        if pattern.search(normalized)
    )


def is_safety_request(value: str) -> bool:
    return bool(_SAFETY_REQUEST.search(normalize_text(value)))


def classify_content_role(
    section_path: tuple[str, ...],
    text: str,
) -> ContentRole:
    path = normalize_text(" ".join(section_path))
    content = normalize_text(text)

    path_rules = (
        (ContentRole.SAFETY, r"\bseguranca\b"),
        (ContentRole.VALIDATION, r"\b(?:validacao|criterios? de aceitacao)\b"),
        (ContentRole.REPLACEMENT, r"\b(?:substituicao|instalacao d[oa] nov)\w*\b"),
        (ContentRole.ALIGNMENT, r"\balinhamento\b"),
        (ContentRole.LUBRICATION, r"\b(?:lubrificacao|relubrificacao)\b"),
        (ContentRole.ADJUSTMENT, r"\b(?:ajuste|tensao|correia frouxa)\b"),
        (ContentRole.INSPECTION, r"\b(?:inspecao|verificacao)\b"),
        (ContentRole.DIAGNOSIS, r"\b(?:diagnostico|sintomas|tipos? de falhas?)\b"),
    )
    for role, pattern in path_rules:
        if re.search(pattern, path):
            return role

    content_rules = (
        (ContentRole.SAFETY, r"\b(?:bloqueio|etiquetagem|ausencia de energia)\b"),
        (ContentRole.REPLACEMENT, r"\b(?:substituir|remover .* antiga|instalar nov)\w*\b"),
        (ContentRole.ALIGNMENT, r"\b(?:alinhar|alinhamento)\b"),
        (ContentRole.LUBRICATION, r"\b(?:lubrificar|relubrificar)\b"),
        (ContentRole.ADJUSTMENT, r"\b(?:ajustar|reapertar|tensao recomendada)\b"),
        (ContentRole.VALIDATION, r"\b(?:validar|criterios? de aceitacao)\b"),
        (ContentRole.INSPECTION, r"\b(?:inspecionar|verificar)\b"),
        (ContentRole.DIAGNOSIS, r"\b(?:diagnosticar|causas?|sintomas?)\b"),
    )
    for role, pattern in content_rules:
        if re.search(pattern, content):
            return role
    return ContentRole.GENERAL
