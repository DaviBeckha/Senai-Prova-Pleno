import logging
from dataclasses import dataclass, field

from app.llm.base import RenderContext, Renderer
from app.llm.adequacy import AnswerAdequacyError, validate_answer_adequacy
from app.llm.grounding import (
    GroundingValidationError,
    format_grounded_draft,
    parse_grounded_draft,
    validate_grounded_draft,
)

log = logging.getLogger(__name__)


@dataclass
class RenderOutcome:
    text: str
    renderer: str
    degraded: bool
    # Por que a resposta do redator primario foi rejeitada. Vazio quando ela
    # passou na validacao — o que distingue "modelo indisponivel" de "modelo
    # respondeu, mas sem suporte na evidencia".
    validation_errors: tuple[str, ...] = field(default_factory=tuple)
    answer_status: str = "answered"


class Router:
    """Redator primario com validacao de fundamentacao e degradacao extrativa.

    A validacao fica DENTRO da fronteira primario/fallback de proposito: uma
    resposta sem suporte na evidencia e tratada como falha do redator, do
    mesmo modo que um timeout. O operador nunca ve texto que nao passou pela
    conferencia — na duvida, ve os trechos crus.
    """

    def __init__(self, primary: Renderer, fallback: Renderer) -> None:
        self._primary = primary
        self._fallback = fallback

    def render(self, ctx: RenderContext) -> RenderOutcome:
        try:
            draft = parse_grounded_draft(self._primary.render(ctx))
            errors = validate_grounded_draft(draft, ctx)
            if errors:
                raise GroundingValidationError(" | ".join(errors))
            adequacy_errors = validate_answer_adequacy(draft, ctx)
            if adequacy_errors:
                raise AnswerAdequacyError(" | ".join(adequacy_errors))
            return RenderOutcome(
                format_grounded_draft(draft, ctx),
                self._primary.name,
                False,
            )
        except AnswerAdequacyError as exc:
            errors = tuple(str(exc).split(" | "))
            log.warning(
                "renderer %s produziu resposta fundamentada mas inadequada: %s",
                self._primary.name,
                exc,
            )
            return RenderOutcome(
                (
                    "As evidências recuperadas não permitiram responder à ação "
                    "solicitada com completude. A orientação foi retida."
                ),
                self._fallback.name,
                True,
                errors,
                "insufficient_evidence",
            )
        except Exception as exc:
            log.exception(
                "renderer %s falhou ou produziu resposta sem suporte",
                self._primary.name,
            )
            errors = (
                tuple(str(exc).split(" | "))
                if str(exc)
                else ("falha de renderização sem mensagem",)
            )
            return RenderOutcome(
                self._fallback.render(ctx),
                self._fallback.name,
                True,
                errors,
            )
