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

# Formas verbais explicitas prevalecem sobre marcadores discursivos como
# "explique": se existe "como abrir" ou "e abra", ha uma acao fisica mesmo
# que a primeira clausula seja conceitual. Substantivos como ajuste, troca,
# alinhamento e instalacao ficam fora deste padrao.
_EXPLICIT_PHYSICAL_FRAGMENT = (
    r"ajust(?:ar|ando|ou|o|amos|aram|ava|avam)|"
    r"(?:re)?apert(?:ar|ando|ou|amos|aram|ava|avam)|"
    r"alinh(?:ar|ando|ou|amos|aram|ava|avam)|"
    r"(?:re)?lubrific(?:ar|ando|ou|amos|aram|ava|avam)|"
    r"(?:repar|consert|trat|instal|desmont)"
    r"(?:ar|ando|ou|amos|aram|ava|avam)|"
    r"remov(?:er|endo|eu|emos|eram|ia|iam)|"
    r"mex(?:er|a|am|endo|eu|e|em|o|i|emos|eram|ia|iam|id[oa]s?)|"
    r"abr(?:ir|a|am|e|em|o|i|imos|iram|ia|iam|indo|iu)|abert[oa]s?|"
    r"substitu(?:ir|indo|iu|o|a|am|i|em|imos|iram|ia|iam)|"
    r"corrig(?:ir|indo|iu|o|e|em|imos|iram|ia|iam)|corrij(?:a|am|o)|"
    r"troc(?:ar|ando|ou|o|amos|aram|ava|avam)|troqu(?:e|em)"
)
_EXPLICIT_PHYSICAL_INTERVENTION = re.compile(
    rf"\b(?:{_EXPLICIT_PHYSICAL_FRAGMENT})\b"
)
_AMBIGUOUS_IMPERATIVE_FRAGMENT = (
    r"ajust(?:e|em)|(?:re)?apert(?:e|em)|alinh(?:e|em)|"
    r"(?:re)?lubrifiqu(?:e|em)|"
    r"(?:repar|consert|trat|instal|desmont)(?:e|em)"
)
_AMBIGUOUS_IMPERATIVE = re.compile(
    rf"\b(?:{_AMBIGUOUS_IMPERATIVE_FRAGMENT})\b"
)
_COORDINATED_IMPERATIVE = re.compile(
    rf"\b(?:e|tambem|depois|entao)\s+(?:por favor\s+)?"
    rf"(?:{_AMBIGUOUS_IMPERATIVE_FRAGMENT})\b"
)
_EXPLANATION_REQUEST = re.compile(
    r"\b(?:o que significa|o que (?:e|sao)|qual (?:e )?a definicao|"
    r"qual (?:e )?a diferenca|para que serve|explique|defina|conceitue)\b"
    r"|\b(?:como funciona|qual (?:e )?a funcao|o que faz|fale sobre)\b"
)
_PROCEDURAL_NOMINAL_CUE = re.compile(
    r"\b(?:procedimento|passo a passo|etapas?|forma de)\b"
)
_FACTUAL_REQUEST = re.compile(
    r"\b(?:custo|preco|valor|data|prazo|responsavel)\b|"
    r"\best(?:a|ao)\s+(?:corret[oa]s?|adequad[oa]s?)\b"
)
_ADDITIONAL_ACTION_CLAUSE = re.compile(
    r"\b(?:e|tambem)\s+(?P<clause>[^?]+)$"
)
_PROCEDURAL_CLAUSE_CUE = re.compile(
    r"^(?:como|posso|devo|preciso|quero|vou|precisamos)\b|"
    r"^(?:qual|quais)\b.*\bprocedimento\b|"
    r"^(?:(?:qual|quais)\s+)?(?:as\s+)?etapas\b|"
    r"^(?:o\s+)?passo a passo\b"
)
_SAFETY_CONTEXT_CLAUSE = re.compile(
    r"^(?:(?:as|quais(?: as)?)\s+)?etapas?\s+de\s+"
    r"(?:seguranca|bloqueio|etiquetagem)\b|"
    r"^(?:seguranca|bloqueio|etiquetagem|cuidados?|epis?)\b"
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


def is_explanation_request(value: str) -> bool:
    normalized = normalize_text(value)
    if not _EXPLANATION_REQUEST.search(normalized):
        return False
    if has_explicit_physical_intervention(normalized):
        return False
    return not (
        _PROCEDURAL_NOMINAL_CUE.search(normalized)
        and any(
            action in _INTERVENTION_ACTIONS
            for action in detect_actions(normalized)
        )
    )


def is_factual_request(value: str) -> bool:
    normalized = normalize_text(value)
    return bool(
        _FACTUAL_REQUEST.search(normalized)
        and not has_explicit_physical_intervention(normalized)
    )


def has_explicit_physical_intervention(value: str) -> bool:
    normalized = normalize_text(value)
    return bool(
        _EXPLICIT_PHYSICAL_INTERVENTION.search(normalized)
        or _COORDINATED_IMPERATIVE.search(normalized)
    )


def is_safety_only_request(value: str) -> bool:
    normalized = normalize_text(value)
    additional = _ADDITIONAL_ACTION_CLAUSE.search(normalized)
    clause = additional.group("clause") if additional else ""
    has_additional_action = bool(
        additional
        and not _SAFETY_CONTEXT_CLAUSE.search(clause)
        and (
            (
                _PROCEDURAL_CLAUSE_CUE.search(clause)
                and (
                    detect_actions(clause)
                    or _EXPLICIT_PHYSICAL_INTERVENTION.search(clause)
                    or _AMBIGUOUS_IMPERATIVE.search(clause)
                )
            )
            or _EXPLICIT_PHYSICAL_INTERVENTION.match(clause)
            or _AMBIGUOUS_IMPERATIVE.match(clause)
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
    normalized = normalize_text(value)
    if has_explicit_physical_intervention(normalized):
        return True
    if is_explanation_request(value):
        return False
    classified_actions = detect_actions(value) if actions is None else actions
    return (
        any(is_intervention_action(action) for action in classified_actions)
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
