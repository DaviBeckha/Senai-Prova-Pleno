from dataclasses import dataclass
from enum import StrEnum

from app.core.maintenance_intent import MaintenanceAction


class ChatIntent(StrEnum):
    PROCEDURE = "procedure"
    DOCUMENT_STATUS = "document_status"
    HISTORY = "history"
    CLARIFICATION = "clarification"
    OUT_OF_SCOPE = "out_of_scope"
    STATE = "state"


class QueryScope(StrEnum):
    FOCUSED = "focused"
    COMPLETE = "complete"


@dataclass(frozen=True)
class QuestionAnalysis:
    original: str
    normalized: str
    intent: ChatIntent
    explicit_families: tuple[str, ...] = ()
    candidate_families: tuple[str, ...] = ()
    negated_families: tuple[str, ...] = ()
    scope: QueryScope = QueryScope.FOCUSED
    requested_actions: tuple[MaintenanceAction, ...] = ()
    conditions: frozenset[str] = frozenset()
    requires_safety: bool = False

    @property
    def needs_clarification(self) -> bool:
        return self.intent is ChatIntent.CLARIFICATION


@dataclass(frozen=True)
class ChatReport:
    status: str
    message: str
    families: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    renderer: str | None = None
    degraded: bool = False
    limitations: tuple[str, ...] = ()
    # Por que a geracao foi rejeitada pela validacao de fundamentacao. Distingue
    # "modelo fora do ar" de "modelo inventou" — os dois chegam com
    # degraded=True, mas so o segundo traz motivos aqui.
    validation_errors: tuple[str, ...] = ()
