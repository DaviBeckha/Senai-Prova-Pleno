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


_ACTION_ROLES = {
    MaintenanceAction.DIAGNOSE: frozenset({
        ContentRole.DIAGNOSIS,
        ContentRole.INSPECTION,
    }),
    MaintenanceAction.INSPECT: frozenset({ContentRole.INSPECTION}),
    MaintenanceAction.ADJUST: frozenset({ContentRole.ADJUSTMENT}),
    MaintenanceAction.ALIGN: frozenset({ContentRole.ALIGNMENT}),
    MaintenanceAction.LUBRICATE: frozenset({ContentRole.LUBRICATION}),
    MaintenanceAction.REPAIR: frozenset({
        ContentRole.ADJUSTMENT,
        ContentRole.ALIGNMENT,
        ContentRole.LUBRICATION,
        ContentRole.REPLACEMENT,
    }),
    MaintenanceAction.REPLACE: frozenset({ContentRole.REPLACEMENT}),
    MaintenanceAction.VALIDATE: frozenset({ContentRole.VALIDATION}),
}

_INTERVENTION_ACTIONS = frozenset({
    MaintenanceAction.ADJUST,
    MaintenanceAction.ALIGN,
    MaintenanceAction.LUBRICATE,
    MaintenanceAction.REPAIR,
    MaintenanceAction.REPLACE,
})

REPLACEMENT_CONDITIONS = frozenset({
    "dano",
    "desgaste",
    "trinca",
    "contaminacao",
    "falha_estrutural",
})


_ACTION_PATTERNS = (
    (MaintenanceAction.INSPECT, re.compile(r"\b(?:inspecion\w*|verific\w*)\b")),
    (MaintenanceAction.ADJUST, re.compile(r"\b(?:ajust\w*|apert\w*|reapert\w*)\b")),
    (MaintenanceAction.ALIGN, re.compile(r"\b(?:alinh\w*)\b")),
    (MaintenanceAction.LUBRICATE, re.compile(r"\b(?:lubrific\w*|relubrific\w*)\b")),
    (
        MaintenanceAction.REPLACE,
        re.compile(r"\b(?:substitu\w*|troc\w*|troqu\w*|remov\w*|instal\w*)\b"),
    ),
    (MaintenanceAction.VALIDATE, re.compile(r"\b(?:valid\w*|confirm\w*|test\w*)\b")),
    (
        MaintenanceAction.DIAGNOSE,
        re.compile(r"\b(?:diagnostic\w*|identific\w*|causas?)\b"),
    ),
    (
        MaintenanceAction.REPAIR,
        re.compile(
            r"\b(?:corrij\w*|corrig\w*|consert\w*|repar\w*|trat\w*|"
            r"procedimento)\b"
        ),
    ),
)

# Acoes fisicas genericas que devem acionar seguranca, mas nao descrevem uma
# categoria de evidencia para reranking. Mantê-las separadas evita transformar
# "verificacoes de seguranca antes de mexer" em pedido de reparo no analisador.
_GENERIC_PHYSICAL_INTERVENTION = re.compile(
    r"\b(?:mex(?:er|a|am|endo|eu|e|em|o|i|emos|eram|ia|iam|id[oa]s?)|"
    r"abr(?:ir|a|am|e|em|o|imos|iram|ia|iam|indo|iu)|abert[oa]s?|"
    r"desmont\w*)\b"
)

_EXPLANATION_REQUEST = re.compile(
    r"\b(?:o que significa|o que (?:e|sao)|qual (?:e )?a definicao|"
    r"qual (?:e )?a diferenca|para que serve|explique|defina|conceitue)\b"
)
_ADDITIONAL_ACTION_CLAUSE = re.compile(
    r"\b(?:e|tambem)\s+(?P<clause>"
    r"(?:como|posso|devo|preciso|quero|vou|precisamos)\b.*)$"
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
_SAFETY_ONLY_REQUEST = re.compile(
    r"\b(?:verificacoes?|medidas?|cuidados?) de seguranca\b"
)


def detect_actions(value: str) -> tuple[MaintenanceAction, ...]:
    normalized = normalize_text(value)
    if _EXPLANATION_REQUEST.search(normalized):
        additional = _ADDITIONAL_ACTION_CLAUSE.search(normalized)
        if additional is None:
            return ()
        normalized = additional.group("clause")
    # "verificações de segurança" descreve o tema da pergunta, não uma
    # inspeção de manutenção. Removemos somente essa expressão para ainda
    # preservar ações explícitas adicionais, como "inspecionar a correia".
    normalized = _SAFETY_ONLY_REQUEST.sub(" seguranca ", normalized)
    actions = [
        action
        for action, pattern in _ACTION_PATTERNS
        if pattern.search(normalized)
    ]
    specific_correction = {
        MaintenanceAction.ADJUST,
        MaintenanceAction.ALIGN,
        MaintenanceAction.LUBRICATE,
        MaintenanceAction.REPLACE,
    }
    if MaintenanceAction.REPAIR in actions and any(
        action in specific_correction for action in actions
    ):
        actions.remove(MaintenanceAction.REPAIR)
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


def is_safety_only_request(value: str) -> bool:
    normalized = normalize_text(value)
    additional = _ADDITIONAL_ACTION_CLAUSE.search(normalized)
    has_additional_action = bool(
        additional
        and (
            detect_actions(additional.group("clause"))
            or _GENERIC_PHYSICAL_INTERVENTION.search(
                additional.group("clause")
            )
        )
    )
    return bool(
        _SAFETY_REQUEST.search(normalized)
        and _SAFETY_ONLY_REQUEST.search(normalized)
        and not has_additional_action
    )


def roles_for_action(action: MaintenanceAction) -> frozenset[ContentRole]:
    return _ACTION_ROLES[action]


def is_intervention_action(action: MaintenanceAction) -> bool:
    return action in _INTERVENTION_ACTIONS


def requests_physical_intervention(
    value: str,
    actions: tuple[MaintenanceAction, ...] | None = None,
) -> bool:
    classified_actions = detect_actions(value) if actions is None else actions
    return (
        any(is_intervention_action(action) for action in classified_actions)
        or bool(_GENERIC_PHYSICAL_INTERVENTION.search(normalize_text(value)))
    )


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
