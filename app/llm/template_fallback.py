from app.llm.base import RenderContext
from app.llm.grounding import evidence_items_for


class TemplateRenderer:
    """Ultimo degrau: so evidencia crua, nenhuma sintese.

    E usado quando o redator primario falhou OU quando o que ele escreveu nao
    passou na validacao de fundamentacao. Nos dois casos a resposta nao pode
    conter nada que nao esteja literalmente nos trechos recuperados — se a
    degradacao parafraseasse, reintroduziria exatamente o risco que a
    validacao acabou de barrar.

    Atende os dois contextos (evento e chat) via evidence_items_for.
    """

    name = "template"

    def render(self, ctx: RenderContext) -> str:
        lines = [
            "Não foi possível validar uma resposta gerada. "
            "Abaixo estão somente os trechos recuperados:"
        ]
        for item in evidence_items_for(ctx):
            chunk = item.chunk
            lines.append(
                f"- [{item.evidence_id}; {chunk.source} — seção "
                f"{chunk.section}] {chunk.text}"
            )
        limitations = getattr(ctx, "limitations", ())
        if limitations:
            lines.append("Limitações:")
            lines.extend(f"- {limitation}" for limitation in limitations)
        return "\n".join(lines)
