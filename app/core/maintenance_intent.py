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


_REGULAR_AR_SUFFIX = (
    r"(?:ar|ares|armos|ardes|arem|ando|"
    r"o|a|as|amos|ais|am|ei|aste|ou|astes|aram|"
    r"ava|avas|avamos|aveis|avam|"
    r"ara|aras|aramos|areis|arao|arei|aremos|"
    r"aria|arias|ariamos|arieis|ariam|"
    r"e|es|emos|eis|em|asse|asses|assemos|asseis|assem)"
)
_TOUCH_FRAGMENT = (
    rf"toc{_REGULAR_AR_SUFFIX}|toqu(?:e|es|emos|eis|em|ei)"
)
_LEAN_FRAGMENT = rf"encost{_REGULAR_AR_SUFFIX}"
_HANDLE_FRAGMENT = rf"manipul{_REGULAR_AR_SUFFIX}"
_PULL_FRAGMENT = rf"pux{_REGULAR_AR_SUFFIX}"
_STRETCH_FRAGMENT = (
    rf"estic{_REGULAR_AR_SUFFIX}|estiqu(?:e|es|emos|eis|em|ei)"
)
_TENSION_FRAGMENT = rf"tension{_REGULAR_AR_SUFFIX}"
_LOOSEN_FRAGMENT = rf"solt{_REGULAR_AR_SUFFIX}"
_CALIBRATE_FRAGMENT = rf"calibr{_REGULAR_AR_SUFFIX}"
_CLEAN_FRAGMENT = rf"limp{_REGULAR_AR_SUFFIX}"
_DO_FRAGMENT = (
    r"(?:faz(?:er|endo|ia|ias|iamos|ieis|iam|emos|em)?|"
    r"fac(?:o|a|as|amos|am)|"
    r"fiz(?:este|emos|estes|eram|esse|esses|essemos|esseis|essem|"
    r"er|eres|ermos|erdes|erem)?|"
    r"fez|far(?:ei|as|a|emos|eis|ao|ia|ias|iamos|ieis|iam)|"
    r"feit[oa]s?)"
)
_MAINTENANCE_PHRASE_FRAGMENT = (
    rf"{_DO_FRAGMENT}\s+(?:(?:a|uma)\s+)?manutencao"
)
_MEASURE_FRAGMENT = (
    r"(?:med(?:ir|ires|irmos|irdes|irem|indo|"
    r"e|es|imos|is|em|i|iste|iu|istes|iram|"
    r"ia|ias|iamos|ieis|iam|"
    r"irei|iras|ira|iremos|ireis|irao|"
    r"iria|irias|iriamos|irieis|iriam|"
    r"isse|isses|issemos|isseis|issem)|"
    r"mec(?:o|a|as|amos|am))"
)
_MEASUREMENT_MODIFIER = (
    r"(?:(?:novamente|agora|diretamente|manualmente|primeiro|"
    r"antes|depois|cuidadosamente|outra vez)\s+){0,2}"
)
_TENSION_MEASUREMENT_FRAGMENT = (
    rf"{_MEASURE_FRAGMENT}\s+{_MEASUREMENT_MODIFIER}(?:a\s+)?tensao"
)
_PASSIVE_AUXILIARY_FRAGMENT = (
    r"(?:sao|foi|foram|sera|serao|seria|seriam|seja|sejam|"
    r"fosse|fossem|(?:vai|vao|deve|devem|pode|podem|precisa|precisam)"
    r"\s+ser|tem\s+que\s+ser|esta(?:o)?\s+sendo|"
    r"estava(?:m)?\s+sendo|estara(?:o)?\s+sendo|"
    r"tem\s+sido|tinha(?:m)?\s+sido)"
)
_PASSIVE_ACTION_PARTICIPLE_FRAGMENT = (
    r"(?:toc|encost|manipul|pux|estic|tension|solt|calibr)ad[oa]s?|"
    r"solt[oa]s?|limpad[oa]s?|limp[oa]s?"
)
_PRESENT_PASSIVE_PARTICIPLE_FRAGMENT = (
    rf"(?:{_PASSIVE_ACTION_PARTICIPLE_FRAGMENT}|"
    r"medid[oa]s?|feit[oa]s?)"
)
_ATTRIBUTIVE_PHYSICAL_ADJECTIVE = re.compile(
    rf"^(?:{_PRESENT_PASSIVE_PARTICIPLE_FRAGMENT}|"
    r"corret[oa]s?|adequad[oa]s?|abert[oa]s?|"
    r"(?:ajust|apert|reapert|alinh|lubrific|repar|consert|trat|"
    r"instal|desmont|troc)ad[oa]s?|"
    r"removid[oa]s?|mexid[oa]s?|substituid[oa]s?|corrigid[oa]s?)$"
)
_PRESENT_PASSIVE_INTERVENTION = re.compile(
    rf"\b(?P<subject>[a-z0-9_-]+)\s+e\s+"
    rf"(?:{_PRESENT_PASSIVE_PARTICIPLE_FRAGMENT})\b"
)
_INVERTED_PRESENT_TENSION_MEASUREMENT = re.compile(
    r"\be\s+medid[oa]s?\b[^?.;]{0,80}\btensao\b"
)
_INVERTED_PRESENT_MAINTENANCE = re.compile(
    r"\be\s+feit[oa]s?\b[^?.;]{0,80}\bmanutencao\b"
)
_PRESENT_TENSION_MEASUREMENT = re.compile(
    rf"(?:\btensao\b[^?.;]{{0,80}}\be\s+medid[oa]s?\b|"
    rf"{_INVERTED_PRESENT_TENSION_MEASUREMENT.pattern})"
)
_PRESENT_MAINTENANCE_INTERVENTION = re.compile(
    rf"(?:\bmanutencao\b[^?.;]{{0,80}}\be\s+feit[oa]s?\b|"
    rf"{_INVERTED_PRESENT_MAINTENANCE.pattern})"
)
_ADJUSTMENT_PARTICIPLE_FRAGMENT = (
    r"(?:pux|estic|tension|solt|calibr)ad[oa]s?|solt[oa]s?"
)
_REPAIR_PARTICIPLE_FRAGMENT = (
    r"(?:toc|encost|manipul|limp)ad[oa]s?|limp[oa]s?"
)
_PASSIVE_PHYSICAL_INTERVENTION = re.compile(
    rf"\b{_PASSIVE_AUXILIARY_FRAGMENT}\s+"
    rf"(?:{_PASSIVE_ACTION_PARTICIPLE_FRAGMENT})\b"
)
_PASSIVE_TENSION_MEASUREMENT = re.compile(
    rf"(?:\btensao\b[^?.;]{{0,80}}\b"
    rf"{_PASSIVE_AUXILIARY_FRAGMENT}\s+medid[oa]s?\b|"
    rf"\b{_PASSIVE_AUXILIARY_FRAGMENT}\s+medid[oa]s?\b"
    rf"[^?.;]{{0,80}}\btensao\b)"
)
_PASSIVE_MAINTENANCE_INTERVENTION = re.compile(
    rf"(?:\bmanutencao\b[^?.;]{{0,80}}\b"
    rf"{_PASSIVE_AUXILIARY_FRAGMENT}\s+feit[oa]s?\b|"
    rf"\b{_PASSIVE_AUXILIARY_FRAGMENT}\s+feit[oa]s?\b"
    rf"[^?.;]{{0,80}}\bmanutencao\b)"
)
_ADDITIONAL_PHYSICAL_FRAGMENT = "|".join((
    _TOUCH_FRAGMENT,
    _LEAN_FRAGMENT,
    _HANDLE_FRAGMENT,
    _PULL_FRAGMENT,
    _STRETCH_FRAGMENT,
    _TENSION_FRAGMENT,
    _LOOSEN_FRAGMENT,
    _CALIBRATE_FRAGMENT,
    _CLEAN_FRAGMENT,
))


_ACTION_PATTERNS = (
    (
        MaintenanceAction.INSPECT,
        re.compile(
            rf"\b(?:inspecion\w*|verific\w*|"
            rf"{_TENSION_MEASUREMENT_FRAGMENT}|"
            rf"{_PASSIVE_TENSION_MEASUREMENT.pattern}|"
            rf"{_PRESENT_TENSION_MEASUREMENT.pattern})\b"
        ),
    ),
    (
        MaintenanceAction.ADJUST,
        re.compile(
            rf"\b(?:ajust\w*|apert\w*|reapert\w*|{_PULL_FRAGMENT}|"
            rf"{_STRETCH_FRAGMENT}|{_TENSION_FRAGMENT}|"
            rf"{_LOOSEN_FRAGMENT}|{_CALIBRATE_FRAGMENT})\b"
            rf"|\b(?:{_ADJUSTMENT_PARTICIPLE_FRAGMENT})\b"
        ),
    ),
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
            rf"procedimento|{_TOUCH_FRAGMENT}|{_LEAN_FRAGMENT}|"
            rf"{_HANDLE_FRAGMENT}|{_CLEAN_FRAGMENT}|"
            rf"{_MAINTENANCE_PHRASE_FRAGMENT}|"
            rf"{_REPAIR_PARTICIPLE_FRAGMENT}|"
            rf"{_PASSIVE_MAINTENANCE_INTERVENTION.pattern}|"
            rf"{_PRESENT_MAINTENANCE_INTERVENTION.pattern})\b"
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
    r"remov(?:er|endo|eu|emos|eram|ia|iam|a|am)|"
    r"mex(?:er|a|am|endo|eu|e|em|o|i|emos|eram|ia|iam|id[oa]s?)|"
    r"abr(?:ir|a|am|e|em|o|i|imos|iram|ia|iam|indo|iu)|abert[oa]s?|"
    r"substitu(?:ir|indo|iu|o|a|am|i|em|imos|iram|ia|iam)|"
    r"corrig(?:ir|indo|iu|o|e|em|imos|iram|ia|iam)|corrij(?:a|am|o)|"
    r"troc(?:ar|ando|ou|o|amos|aram|ava|avam)|troqu(?:e|em)|"
    rf"{_ADDITIONAL_PHYSICAL_FRAGMENT}|"
    rf"{_MAINTENANCE_PHRASE_FRAGMENT}|"
    rf"{_TENSION_MEASUREMENT_FRAGMENT}"
)
_EXPLICIT_PHYSICAL_INTERVENTION = re.compile(
    rf"\b(?:{_EXPLICIT_PHYSICAL_FRAGMENT})\b"
)
_AMBIGUOUS_IMPERATIVE_FRAGMENT = (
    r"ajust(?:e|em)|(?:re)?apert(?:e|em)|alinh(?:e|em)|"
    r"(?:re)?lubrifiqu(?:e|em)|"
    r"(?:repar|consert|trat|instal|desmont)(?:e|em)|"
    r"toqu(?:e|em)|encost(?:e|em)|manipul(?:e|em)|pux(?:e|em)|"
    r"estiqu(?:e|em)|tension(?:e|em)|solt(?:e|em)|calibr(?:e|em)|"
    r"limp(?:e|em)|fac(?:a|am)\s+(?:a\s+)?manutencao|"
    r"mec(?:a|am)\s+(?:a\s+)?tensao"
)
_AMBIGUOUS_IMPERATIVE = re.compile(
    rf"\b(?:{_AMBIGUOUS_IMPERATIVE_FRAGMENT})\b"
)
_COORDINATED_IMPERATIVE = re.compile(
    rf"\b(?:e|mas|ou|tambem|depois|entao)\s+(?:por favor\s+)?"
    rf"(?:{_AMBIGUOUS_IMPERATIVE_FRAGMENT})\b"
)
_EXPLANATION_REQUEST = re.compile(
    r"\b(?:o que significa|o que (?:e|sao)|qual (?:e )?a definicao|"
    r"qual (?:e )?a diferenca|para que serve|explique|defina|conceitue)\b"
    r"|\b(?:como funciona|qual (?:e )?a funcao|o que faz|fale sobre)\b"
)
_PURE_CONCEPTUAL_REQUEST = re.compile(
    rf"^(?:"
    rf"qual (?:e )?a diferenca entre\s+"
    rf"(?:{_EXPLICIT_PHYSICAL_FRAGMENT})\b\s+e\s+"
    rf"(?:{_EXPLICIT_PHYSICAL_FRAGMENT})\b|"
    r"o que significa\b|"
    rf"o que e\s+(?:{_EXPLICIT_PHYSICAL_FRAGMENT})\b|"
    r"qual (?:e )?a (?:definicao|funcao|diferenca)\b|"
    r"para que serve\b|como funciona\b|o que faz\b|fale sobre\b|"
    r"defina\b|conceitue\b|"
    r"explique(?:\s+para mim)?\s+(?:"
    r"o que significa\b|"
    rf"o que e\s+(?:{_EXPLICIT_PHYSICAL_FRAGMENT})\b|"
    r"qual (?:e )?a (?:definicao|funcao|diferenca)\b|"
    r"para que serve\b|como funciona\b"
    r")"
    r")"
)
_CONCEPTUAL_CLAUSE_SEPARATOR = re.compile(
    r"\b(?:e|mas|ou|tambem|depois|entao)\b"
)
_CONCEPTUAL_CLAUSE_PREFIX = re.compile(
    r"^(?:o que significa|o que e|qual (?:e )?a "
    r"(?:definicao|funcao|diferenca)|para que serve|como funciona|"
    r"fale sobre|defina|conceitue|explique)\b"
)
_PROCEDURAL_NOMINAL_CUE = re.compile(
    r"\b(?:procedimento|passo a passo|etapas?|forma de)\b"
)
_FACTUAL_REQUEST = re.compile(
    r"\b(?:custo|preco|valor|data|prazo|responsavel)\b|"
    r"\best(?:a|ao)\s+(?:corret[oa]s?|adequad[oa]s?)\b"
)
_STATIVE_FACTUAL_REQUEST = re.compile(
    r"\best(?:a|ao)\s+(?:corret[oa]s?|adequad[oa]s?)\b"
)
_STATIVE_PHYSICAL_ADJECTIVE = re.compile(
    rf"\b(?:{_PASSIVE_ACTION_PARTICIPLE_FRAGMENT}|"
    r"medid[oa]s?|feit[oa]s?)"
    r"(?=\s+est(?:a|ao)\s+(?:corret[oa]s?|adequad[oa]s?)\b)"
)
_STATIVE_COORDINATED_PHYSICAL_ADJECTIVE = re.compile(
    rf"\best(?:a|ao)\s+(?:corret[oa]s?|adequad[oa]s?)\s+e\s+"
    rf"(?:{_PRESENT_PASSIVE_PARTICIPLE_FRAGMENT})\b"
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
    if _STATIVE_FACTUAL_REQUEST.search(normalized):
        without_stative_description = (
            _STATIVE_COORDINATED_PHYSICAL_ADJECTIVE.sub(
                " ",
                normalized,
            )
        )
        without_stative_description = _STATIVE_PHYSICAL_ADJECTIVE.sub(
            " ",
            without_stative_description,
        )
        without_stative_description = _STATIVE_FACTUAL_REQUEST.sub(
            " ",
            without_stative_description,
        )
        return not has_explicit_physical_intervention(
            without_stative_description
        )
    return bool(
        _FACTUAL_REQUEST.search(normalized)
        and not has_explicit_physical_intervention(normalized)
    )


def _has_passive_physical_intervention(normalized: str) -> bool:
    if any(
        pattern.search(normalized)
        for pattern in (
            _PASSIVE_PHYSICAL_INTERVENTION,
            _PASSIVE_TENSION_MEASUREMENT,
            _PASSIVE_MAINTENANCE_INTERVENTION,
            _PRESENT_TENSION_MEASUREMENT,
            _PRESENT_MAINTENANCE_INTERVENTION,
        )
    ):
        return True
    return any(
        not _ATTRIBUTIVE_PHYSICAL_ADJECTIVE.fullmatch(
            match.group("subject")
        )
        for match in _PRESENT_PASSIVE_INTERVENTION.finditer(normalized)
    )


def _has_follow_up_physical_action(
    normalized: str,
    conceptual_end: int,
) -> bool:
    remainder = normalized[conceptual_end:]
    clauses = _CONCEPTUAL_CLAUSE_SEPARATOR.split(remainder)[1:]
    for raw_clause in clauses:
        clause = raw_clause.lstrip(" ,;:")
        clause = re.sub(r"^por favor\s+", "", clause)
        if _CONCEPTUAL_CLAUSE_PREFIX.match(clause):
            continue
        if (
            _EXPLICIT_PHYSICAL_INTERVENTION.search(clause)
            or _AMBIGUOUS_IMPERATIVE.match(clause)
            or _has_passive_physical_intervention(clause)
        ):
            return True
    return False


def has_explicit_physical_intervention(value: str) -> bool:
    normalized = normalize_text(value)
    if (
        _COORDINATED_IMPERATIVE.search(normalized)
        or _AMBIGUOUS_IMPERATIVE.match(normalized)
    ):
        return True
    conceptual = _PURE_CONCEPTUAL_REQUEST.match(normalized)
    if (
        conceptual
        and not _has_follow_up_physical_action(
            normalized,
            conceptual.end(),
        )
    ):
        return False
    return bool(
        _EXPLICIT_PHYSICAL_INTERVENTION.search(normalized)
        or _has_passive_physical_intervention(normalized)
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
    if is_explanation_request(value):
        return False
    if is_factual_request(value):
        return False
    if has_explicit_physical_intervention(normalized):
        return True
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
