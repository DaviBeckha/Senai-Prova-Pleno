from app.llm.base import DiagnosisContext


class TemplateRenderer:
    name = "template"

    def render(self, ctx: DiagnosisContext) -> str:
        lines = [
            f"DEFEITO IDENTIFICADO: {ctx.family}",
            f"HISTORICO: {ctx.stats.total} ocorrencias similares "
            f"({ctx.stats.freq_per_day}/dia, de {ctx.stats.first_seen[:10]} "
            f"a {ctx.stats.last_seen[:10]}).",
            "ACOES DE CORRECAO (extraidas dos procedimentos):",
        ]
        for c in ctx.chunks:
            lines.append(f"- [{c.source} — secao {c.section}] {c.text[:400]}")
        lines.append("FONTE: " + ", ".join(sorted({c.source for c in ctx.chunks})))
        return "\n".join(lines)
