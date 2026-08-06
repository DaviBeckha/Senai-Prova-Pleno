import re
from enum import StrEnum

from app.chat.normalization import normalize_text


class MaintenanceAction(StrEnum):
    DIAGNOSE = "diagnose"
    INSPECT = "inspect"
    ADJUST = "adjust"
    ALIGN = "align"
    LUBRICATE = "lubricate"
    REPAIR = "repair"
    REPLACE = "replace"
    VALIDATE = "validate"


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
