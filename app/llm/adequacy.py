"""Valida se evidências e respostas atendem ao pedido do usuário."""

from app.chat.context import ChatContext
from app.chat.types import QuestionAnalysis
from app.core.maintenance_intent import (
    ContentRole,
    MaintenanceAction,
    REPLACEMENT_CONDITIONS,
    roles_for_action,
)
from app.llm.contracts import GroundedDraft
from app.llm.grounding import evidence_items_for
from app.rag.search import EvidenceItem, RetrievalBundle


class AnswerAdequacyError(ValueError):
    """A resposta é fundamentada, mas não atende ao que foi pedido."""


def _effective_actions(
    actions: tuple[MaintenanceAction, ...],
    requires_safety: bool,
) -> tuple[MaintenanceAction, ...]:
    if requires_safety and actions == (MaintenanceAction.INSPECT,):
        return ()
    return actions


def _allowed_roles(
    action: MaintenanceAction,
    conditions: frozenset[str],
) -> frozenset[ContentRole]:
    roles = set(roles_for_action(action))
    replacement_allowed = (
        action is MaintenanceAction.REPLACE
        or bool(conditions & REPLACEMENT_CONDITIONS)
    )
    if not replacement_allowed:
        roles.discard(ContentRole.REPLACEMENT)
    return frozenset(roles)


def _items_by_family(
    bundle: RetrievalBundle,
) -> dict[str, tuple[EvidenceItem, ...]]:
    return {
        family.family: family.items
        for family in bundle.families
    }


def validate_evidence_adequacy(
    analysis: QuestionAnalysis,
    bundle: RetrievalBundle,
) -> tuple[str, ...]:
    """Reprova antes do LLM quando o contexto não pode responder ao pedido."""
    found = _items_by_family(bundle)
    actions = _effective_actions(
        analysis.requested_actions,
        analysis.requires_safety,
    )
    errors: list[str] = []
    for family in analysis.explicit_families:
        items = found.get(family, ())
        if not items:
            errors.append(f"família {family}: nenhuma evidência recuperada")
            continue
        if analysis.requires_safety and not any(
            item.chunk.content_role is ContentRole.SAFETY
            for item in items
        ):
            errors.append(f"família {family}: falta evidência de segurança")
        if not actions and not analysis.requires_safety and not any(
            item.chunk.content_role is not ContentRole.SAFETY
            for item in items
        ):
            errors.append(f"família {family}: falta evidência de procedimento")
        for action in actions:
            allowed = _allowed_roles(action, analysis.conditions)
            if not any(item.chunk.content_role in allowed for item in items):
                errors.append(
                    f"família {family}: falta evidência para ação {action.value}"
                )
    return tuple(errors)


def _resolve_step_item(step, ctx: ChatContext) -> EvidenceItem | None:
    evidence = {item.evidence_id: item for item in evidence_items_for(ctx)}
    exact = evidence.get(step.evidence_id)
    if exact is not None:
        return exact
    return evidence.get(f"{step.family}:{step.evidence_id}")


def validate_answer_adequacy(
    draft: GroundedDraft,
    ctx,
) -> tuple[str, ...]:
    """Reprova respostas fundamentadas que não executam o pedido."""
    if not draft.steps:
        return ("resposta não contém nenhuma ação aplicável",)
    if not isinstance(ctx, ChatContext):
        return ()

    actions = _effective_actions(ctx.requested_actions, ctx.requires_safety)
    items_by_step = [
        (step, _resolve_step_item(step, ctx))
        for step in draft.steps
    ]
    errors: list[str] = []
    for family in ctx.families:
        family_steps = [
            (step, item)
            for step, item in items_by_step
            if step.family == family and item is not None
        ]
        if not family_steps:
            errors.append(f"família {family}: nenhuma ação respondida")
            continue
        if ctx.requires_safety and not any(
            item.chunk.content_role is ContentRole.SAFETY
            for _, item in family_steps
        ):
            errors.append(f"família {family}: resposta não cobre segurança")
        for action in actions:
            allowed = _allowed_roles(action, ctx.conditions)
            if not any(
                item.chunk.content_role in allowed
                for _, item in family_steps
            ):
                errors.append(
                    f"família {family}: resposta não executa ação {action.value}"
                )
    return tuple(errors)
