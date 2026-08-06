"""Fallback extrativo com apresentação legível e conteúdo auditável."""

import re

from app.core.maintenance_intent import ContentRole
from app.core.text import normalize_text
from app.data.labels import display_label
from app.llm.base import RenderContext
from app.llm.grounding import evidence_items_for
from app.rag.chunking import Chunk
from app.rag.search import EvidenceItem

_PAGE_MARKER_LINE = re.compile(r"\s*p[aá]gina\s+\d+\s*", re.IGNORECASE)
_TRAILING_PAGE_FOOTER = re.compile(
    r"(?<=[.!?])\s+p[aá]gina\s+\d+\s*$",
    re.IGNORECASE,
)
_PDF_BULLET = re.compile(r"\s*[•●▪]\s*")

_ROLE_TITLES = {
    ContentRole.SAFETY: "Segurança",
    ContentRole.DIAGNOSIS: "Sintomas e diagnóstico",
    ContentRole.INSPECTION: "Inspeção",
    ContentRole.ADJUSTMENT: "Ajuste e correção",
    ContentRole.ALIGNMENT: "Alinhamento",
    ContentRole.LUBRICATION: "Lubrificação",
    ContentRole.REPLACEMENT: "Substituição",
    ContentRole.VALIDATION: "Validação",
    ContentRole.GENERAL: "Informações complementares",
}


def _is_chunk_heading(line: str, chunk: Chunk) -> bool:
    normalized = normalize_text(line)
    candidates = (*chunk.section_path, chunk.section)
    return any(normalized == normalize_text(candidate) for candidate in candidates)


def _clean_chunk_text(chunk: Chunk) -> str:
    """Remove somente artefatos visuais, sem reescrever a evidência."""
    lines = chunk.text.splitlines()
    while lines and _is_chunk_heading(lines[0], chunk):
        lines.pop(0)
    lines = [
        line
        for line in lines
        if _PAGE_MARKER_LINE.fullmatch(line) is None
    ]

    text = "\n".join(lines).strip()
    text = _TRAILING_PAGE_FOOTER.sub("", text).rstrip()
    bullet_parts = _PDF_BULLET.split(text)
    if len(bullet_parts) == 1:
        return text

    intro, *raw_items = bullet_parts
    formatted: list[str] = []
    if intro.strip():
        formatted.extend((intro.strip(), ""))
    formatted.extend(
        f"- {re.sub(r'\s+', ' ', item).strip()}"
        for item in raw_items
        if item.strip()
    )
    return "\n".join(formatted)


def _format_family(
    family: str,
    items: tuple[EvidenceItem, ...],
) -> list[str]:
    grouped: dict[ContentRole, list[str]] = {
        role: [] for role in _ROLE_TITLES
    }
    for item in items:
        text = _clean_chunk_text(item.chunk)
        if text:
            grouped[item.chunk.content_role].append(text)

    lines = [f"### Orientação encontrada para {display_label(family)}"]
    for role, title in _ROLE_TITLES.items():
        if not grouped[role]:
            continue
        lines.extend(("", f"#### {title}", ""))
        for position, text in enumerate(grouped[role]):
            if position:
                lines.append("")
            lines.append(text)
    return lines


class TemplateRenderer:
    """Último degrau: organiza literalmente as evidências recuperadas.

    O fallback não resume nem parafraseia. A limpeza se limita a cabeçalhos
    repetidos, marcadores de página e bullets extraídos do PDF. Identificadores,
    fontes e trechos originais seguem disponíveis no contrato estruturado da
    API, sem poluir a orientação principal.
    """

    name = "template"

    def render(self, ctx: RenderContext) -> str:
        by_family: dict[str, list[EvidenceItem]] = {}
        for item in evidence_items_for(ctx):
            by_family.setdefault(item.family, []).append(item)

        lines: list[str] = []
        for family, items in by_family.items():
            if lines:
                lines.append("")
            lines.extend(_format_family(family, tuple(items)))

        limitations = getattr(ctx, "limitations", ())
        if limitations:
            lines.extend(("", "### Limitações", ""))
            lines.extend(f"- {limitation}" for limitation in limitations)
        return "\n".join(lines)
