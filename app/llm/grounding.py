"""Valida cada acao gerada contra a evidencia que ela alega citar.

Premissa do modulo: *instrucao de prompt nao e garantia*. O prompt pede que o
modelo nao invente EPIs, torques ou etapas; aqui isso e VERIFICADO. Quatro
conferencias por passo:

1. o evidence_id existe no contexto recuperado;
2. a familia declarada bate com a da evidencia;
3. a citacao e substring literal do trecho (normalizada);
4. a acao e lexicalmente sustentada pela citacao e nao introduz numeros novos.

Qualquer passo reprovado invalida o rascunho INTEIRO — meia resposta
fundamentada e meia inventada continua sendo uma resposta inventada.
"""

import json
import re
import unicodedata

from app.chat.context import ChatContext
from app.llm.contracts import GroundedDraft
from app.rag.search import EvidenceItem

_FENCE = re.compile(r"^\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60$", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos",
    "e", "em", "na", "nas", "no", "nos", "o", "os", "para", "por",
    "um", "uma",
}
# Fracao minima dos tokens significativos da acao que precisa aparecer na
# citacao. Abaixo disso a acao esta parafraseando algo que a fonte nao diz.
_MIN_LEXICAL_SUPPORT = 0.60


class GroundingValidationError(ValueError):
    pass


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(ch for ch in decomposed if not unicodedata.combining(ch)).split()
    )


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _WORD.findall(_normalize(value))
        if token not in _STOPWORDS
    }


def evidence_items_for(ctx) -> tuple[EvidenceItem, ...]:
    """Evidencia identificada dos dois contextos.

    ChatContext ja traz EvidenceItem do Plano 2. DiagnosisContext (/eventos)
    tem apenas chunks anonimos, entao os IDs sao derivados da ordem — o mesmo
    esquema `familia:E{n}` que build_user_prompt mostra ao modelo, para que a
    validacao seja identica nos dois caminhos.
    """
    if isinstance(ctx, ChatContext):
        return ctx.retrieval.items
    return tuple(
        EvidenceItem(
            f"{ctx.family}:E{position}",
            ctx.family,
            chunk,
            None,
        )
        for position, chunk in enumerate(ctx.chunks, start=1)
    )


def parse_grounded_draft(raw: str) -> GroundedDraft:
    cleaned = _FENCE.sub("", raw.strip())
    try:
        return GroundedDraft.model_validate(json.loads(cleaned))
    except (json.JSONDecodeError, ValueError) as exc:
        raise GroundingValidationError(f"JSON estruturado inválido: {exc}") from exc


def _resolve_evidence(evidence: dict[str, EvidenceItem], step) -> EvidenceItem | None:
    """Casa o evidence_id declarado com um item realmente recuperado.

    Tolera a abreviacao que os modelos produzem na pratica — "E2" em vez de
    "correia:E2", ja que `family` e um campo separado do contrato. Isso e
    formato, nao fundamentacao: o ID resolvido continua tendo de apontar para
    um trecho REAL. Corrigir isso via prompt seria confiar na obediencia do
    modelo, justamente o que este modulo existe para nao fazer.
    """
    exact = evidence.get(step.evidence_id)
    if exact is not None:
        return exact
    qualified = evidence.get(f"{step.family}:{step.evidence_id}")
    if qualified is not None:
        return qualified
    suffix = f":{step.evidence_id}"
    candidates = [
        item for key, item in evidence.items() if key.endswith(suffix)
    ]
    # So resolve quando nao ha ambiguidade: com duas familias, um "E1" solto
    # poderia ser de qualquer uma delas.
    return candidates[0] if len(candidates) == 1 else None


def validate_grounded_draft(draft: GroundedDraft, ctx) -> tuple[str, ...]:
    evidence = {item.evidence_id: item for item in evidence_items_for(ctx)}
    errors: list[str] = []
    for position, step in enumerate(draft.steps, start=1):
        item = _resolve_evidence(evidence, step)
        if item is None:
            errors.append(
                f"passo {position}: evidência desconhecida {step.evidence_id}"
            )
            continue
        if step.family != item.family:
            errors.append(f"passo {position}: família não corresponde à evidência")
        if _normalize(step.quote) not in _normalize(item.chunk.text):
            errors.append(f"passo {position}: citação não encontrada na evidência")
            continue
        # Numeros sao o caso mais perigoso: um torque ou uma folga inventada
        # tem consequencia fisica e passa despercebida em texto fluente.
        if not set(_NUMBER.findall(step.action)) <= set(_NUMBER.findall(step.quote)):
            errors.append(f"passo {position}: número sem suporte na citação")
        action_tokens = _tokens(step.action)
        quote_tokens = _tokens(step.quote)
        support_ratio = (
            len(action_tokens & quote_tokens) / len(action_tokens)
            if action_tokens
            else 0.0
        )
        if support_ratio < _MIN_LEXICAL_SUPPORT:
            errors.append(
                f"passo {position}: ação possui suporte lexical de "
                f"{support_ratio:.2f}, abaixo de {_MIN_LEXICAL_SUPPORT:.2f}"
            )
    if not draft.steps and not draft.unanswered:
        errors.append("rascunho vazio")
    return tuple(errors)


def format_grounded_draft(draft: GroundedDraft, ctx) -> str:
    evidence = {item.evidence_id: item for item in evidence_items_for(ctx)}
    lines: list[str] = []
    for family in dict.fromkeys(step.family for step in draft.steps):
        lines.append(f"### {family.replace('_', ' ')}")
        for step in (item for item in draft.steps if item.family == family):
            # Mesma resolucao da validacao: o formatador so roda depois dela,
            # entao todo passo aqui ja tem evidencia correspondente.
            resolved = _resolve_evidence(evidence, step)
            source = resolved.chunk
            lines.append(
                f"- {step.action} [{source.source} — seção {source.section}; "
                f"evidência {resolved.evidence_id}]"
            )
    if draft.unanswered:
        lines.append("### Limitações")
        lines.extend(f"- {item}" for item in draft.unanswered)
    context_limitations = getattr(ctx, "limitations", ())
    if context_limitations:
        if "### Limitações" not in lines:
            lines.append("### Limitações")
        lines.extend(f"- {item}" for item in context_limitations)
    return "\n".join(lines)
