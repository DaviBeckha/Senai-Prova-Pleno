from app.chat.catalog import (
    COMPLETE_SCOPE_PHRASES,
    DOCUMENT_STATUS_PHRASES,
    FAMILY_ALIASES,
    HISTORY_PHRASES,
    SYMPTOM_RULES,
)
from app.chat.normalization import find_phrase_spans, is_negated, normalize_text
from app.chat.types import ChatIntent, QueryScope, QuestionAnalysis
from app.data.labels import STATE_FAMILIES
from app.core.maintenance_intent import (
    detect_actions,
    detect_conditions,
    is_explanation_request,
    is_safety_only_request,
    is_safety_request,
)


def _ordered_family_mentions(
    normalized: str,
) -> tuple[tuple[str, int, bool], ...]:
    mentions: list[tuple[str, int, bool]] = []
    for family, aliases in FAMILY_ALIASES.items():
        for start, end, _ in find_phrase_spans(normalized, aliases):
            # `end` importa para aliases de varias palavras: sem ele a janela
            # de negacao posposta terminaria na primeira palavra do alias.
            mentions.append((family, start, is_negated(normalized, start, end)))
    return tuple(sorted(mentions, key=lambda item: item[1]))


def _deduplicate(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _symptom_candidates(normalized: str) -> tuple[str, ...]:
    words = frozenset(normalized.split())
    candidates: list[str] = []
    for rule in SYMPTOM_RULES:
        if rule.required_terms <= words:
            candidates.extend(rule.candidates)
    return _deduplicate(candidates)


def analyze_question(question: str) -> QuestionAnalysis:
    normalized = normalize_text(question)
    explanation = is_explanation_request(normalized)
    requested_actions = () if explanation else detect_actions(normalized)
    conditions = detect_conditions(normalized)
    requires_safety = is_safety_request(normalized)
    safety_only = is_safety_only_request(normalized)
    mentions = _ordered_family_mentions(normalized)
    explicit = _deduplicate(
        [family for family, _, negated in mentions if not negated]
    )
    negated = _deduplicate(
        [family for family, _, is_rejected in mentions if is_rejected]
    )
    scope = (
        QueryScope.COMPLETE
        if any(phrase in normalized for phrase in COMPLETE_SCOPE_PHRASES)
        else QueryScope.FOCUSED
    )
    if any(phrase in normalized for phrase in DOCUMENT_STATUS_PHRASES):
        return QuestionAnalysis(
            question,
            normalized,
            ChatIntent.DOCUMENT_STATUS,
            explicit,
            negated_families=negated,
            scope=scope,
            requested_actions=requested_actions,
            conditions=conditions,
            requires_safety=requires_safety,
            safety_only=safety_only,
        )
    if explicit and any(phrase in normalized for phrase in HISTORY_PHRASES):
        return QuestionAnalysis(
            question,
            normalized,
            ChatIntent.HISTORY,
            explicit,
            negated_families=negated,
            scope=scope,
            requested_actions=requested_actions,
            conditions=conditions,
            requires_safety=requires_safety,
            safety_only=safety_only,
        )
    if explicit and all(family in STATE_FAMILIES for family in explicit):
        return QuestionAnalysis(
            question,
            normalized,
            ChatIntent.STATE,
            explicit,
            negated_families=negated,
            scope=scope,
            requested_actions=requested_actions,
            conditions=conditions,
            requires_safety=requires_safety,
            safety_only=safety_only,
        )
    if explicit:
        return QuestionAnalysis(
            question,
            normalized,
            (
                ChatIntent.EXPLANATION
                if explanation
                else ChatIntent.PROCEDURE
            ),
            explicit,
            negated_families=negated,
            scope=scope,
            requested_actions=requested_actions,
            conditions=conditions,
            requires_safety=requires_safety,
            safety_only=safety_only,
        )
    candidates = _symptom_candidates(normalized)
    if candidates:
        return QuestionAnalysis(
            question,
            normalized,
            ChatIntent.CLARIFICATION,
            candidate_families=candidates,
            negated_families=negated,
            scope=scope,
            requested_actions=requested_actions,
            conditions=conditions,
            requires_safety=requires_safety,
            safety_only=safety_only,
        )
    return QuestionAnalysis(
        question,
        normalized,
        ChatIntent.OUT_OF_SCOPE,
        negated_families=negated,
        scope=scope,
        requested_actions=requested_actions,
        conditions=conditions,
        requires_safety=requires_safety,
        safety_only=safety_only,
    )
