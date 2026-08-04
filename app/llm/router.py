import logging
from dataclasses import dataclass

from app.llm.base import DiagnosisContext, Renderer

log = logging.getLogger(__name__)


@dataclass
class RenderOutcome:
    text: str
    renderer: str
    degraded: bool


class Router:
    def __init__(self, primary: Renderer, fallback: Renderer) -> None:
        self._primary = primary
        self._fallback = fallback

    def render(self, ctx: DiagnosisContext) -> RenderOutcome:
        try:
            return RenderOutcome(self._primary.render(ctx), self._primary.name, False)
        except Exception:
            log.exception("renderer %s falhou; degradando", self._primary.name)
            return RenderOutcome(self._fallback.render(ctx), self._fallback.name, True)
