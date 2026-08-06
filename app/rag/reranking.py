from dataclasses import replace

from app.chat.types import QuestionAnalysis
from app.core.maintenance_intent import (
    ContentRole,
    MaintenanceAction,
    REPLACEMENT_CONDITIONS,
    classify_content_role,
    roles_for_action,
)
from app.core.text import normalize_text
from app.rag.search import SearchHit


def _effective_actions(
    analysis: QuestionAnalysis,
) -> tuple[MaintenanceAction, ...]:
    if analysis.safety_only:
        return ()
    return analysis.requested_actions


def replacement_is_allowed(analysis: QuestionAnalysis) -> bool:
    return (
        MaintenanceAction.REPLACE in analysis.requested_actions
        or bool(analysis.conditions & REPLACEMENT_CONDITIONS)
    )


def _enrich_role(hit: SearchHit) -> SearchHit:
    if hit.chunk.content_role != ContentRole.GENERAL:
        return hit
    role = classify_content_role(hit.chunk.section_path, hit.chunk.text)
    if role == ContentRole.GENERAL:
        return hit
    return SearchHit(replace(hit.chunk, content_role=role), hit.score)


def rerank_score(hit: SearchHit, analysis: QuestionAnalysis) -> float:
    score = hit.score
    requested_roles = {
        role
        for action in _effective_actions(analysis)
        for role in roles_for_action(action)
    }
    if hit.chunk.content_role in requested_roles:
        score += 0.35

    normalized_context = normalize_text(
        " ".join(hit.chunk.section_path) + " " + hit.chunk.text
    )
    score += 0.08 * sum(
        condition.replace("_", " ") in normalized_context
        for condition in analysis.conditions
    )
    if (
        hit.chunk.content_role == ContentRole.REPLACEMENT
        and not replacement_is_allowed(analysis)
    ):
        score -= 1.0
    return score


def rerank_hits(
    hits: list[SearchHit],
    analysis: QuestionAnalysis,
) -> list[SearchHit]:
    enriched = [_enrich_role(hit) for hit in hits]
    return sorted(
        enriched,
        key=lambda hit: rerank_score(hit, analysis),
        reverse=True,
    )


def select_procedure_hits(
    hits: list[SearchHit],
    analysis: QuestionAnalysis,
    *,
    k: int,
    complete: bool,
) -> list[SearchHit]:
    ranked = rerank_hits(hits, analysis)
    actions = _effective_actions(analysis)
    if actions:
        requested_roles = {
            role
            for action in actions
            for role in roles_for_action(action)
        }
        if not replacement_is_allowed(analysis):
            requested_roles.discard(ContentRole.REPLACEMENT)
        matching = [
            hit for hit in ranked
            if hit.chunk.content_role in requested_roles
        ]
        if complete:
            return matching
        selected: list[SearchHit] = []
        for action in actions:
            action_roles = set(roles_for_action(action))
            if not replacement_is_allowed(analysis):
                action_roles.discard(ContentRole.REPLACEMENT)
            found = next(
                (
                    hit for hit in matching
                    if hit.chunk.content_role in action_roles
                    and hit not in selected
                ),
                None,
            )
            if found is not None:
                selected.append(found)
        selected.extend(hit for hit in matching if hit not in selected)
    elif analysis.requires_safety:
        selected = []
    else:
        selected = [
            hit for hit in ranked
            if hit.chunk.content_role not in {
                ContentRole.SAFETY,
                ContentRole.VALIDATION,
            }
        ]
    return selected if complete else selected[:k]
