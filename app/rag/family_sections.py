"""Isolamento das secoes especificas de cada subtipo de rolamento.

doc1_rolamentos.md cobre os quatro subtipos no MESMO documento: seguranca,
inspecao, correcao e validacao valem para todos, mas o diagnostico e mutuamente
exclusivo — pista externa (BPFO), pista interna (BPFI), elementos rolantes
(BSF) e gaiola (FTF) tem frequencias caracteristicas diferentes.

Sem este filtro, a familia `rolamento_inner` indexa tambem a secao de BSF e o
modelo pode citar a frequencia do defeito errado com aparencia de fundamentacao.
As secoes comuns permanecem em todas as familias de proposito: sao o
procedimento que o operador precisa independentemente do subtipo.
"""

from dataclasses import replace

from app.rag.chunking import Chunk

# Prefixos como o chunker os formata: `4.1 Defeito...` no documento vira a
# secao `"4.1. Defeito..."`, e `12. Diagnostico...` vira `"12. Diagnostico..."`.
_BEARING_PREFIXES: dict[str, tuple[str, ...]] = {
    "rolamento_outer": ("4.1.", "12."),
    "rolamento_inner": ("4.2.", "13."),
    "rolamento_ball": ("4.3.", "14."),
    "rolamento_combination": (
        "4.1.",
        "4.2.",
        "4.3.",
        "4.4.",
        "12.",
        "13.",
        "14.",
        "15.",
    ),
}
_ALL_SPECIFIC_PREFIXES = tuple(
    dict.fromkeys(
        prefix
        for prefixes in _BEARING_PREFIXES.values()
        for prefix in prefixes
    )
)


def _is_specific(section: str) -> bool:
    return section.startswith(_ALL_SPECIFIC_PREFIXES)


def filter_chunks_for_family(
    chunks: list[Chunk],
    family: str,
) -> list[Chunk]:
    """Mantem as secoes comuns e apenas o diagnostico do subtipo pedido.

    Familias que nao sao de rolamento (`allowed is None`) passam inteiras: o
    documento delas ja e dedicado, nao ha o que separar.
    """
    allowed = _BEARING_PREFIXES.get(family)
    result: list[Chunk] = []
    for chunk in chunks:
        if allowed is not None and _is_specific(chunk.section):
            if not chunk.section.startswith(allowed):
                continue
        result.append(replace(chunk, doc_family=family))
    return result
