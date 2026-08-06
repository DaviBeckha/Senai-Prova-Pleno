"""Apresentação auditável das evidências recuperadas pela API."""

from collections.abc import Callable

import streamlit as st

_FIELDS = ("id", "familia", "fonte", "secao", "trecho")


def normalizar_evidencias(items: object) -> list[dict[str, str]]:
    """Descarta payload parcial em vez de derrubar a página em todo rerun."""
    if not isinstance(items, (list, tuple)):
        return []

    valid: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not all(
            isinstance(item.get(field), str) and item[field].strip()
            for field in _FIELDS
        ):
            continue
        valid.append({field: item[field] for field in _FIELDS})
    return valid


def mostrar_evidencias(
    items: object,
    rotulo: Callable[[str], str],
) -> int:
    """Mantém trechos técnicos acessíveis sem poluir a orientação principal."""
    valid = normalizar_evidencias(items)
    if not valid:
        return 0

    with st.expander(f"Ver evidências e fontes ({len(valid)})"):
        for position, item in enumerate(valid):
            if position:
                st.divider()
            st.markdown(f"**{rotulo(item['familia'])}**")
            st.text(f"Seção: {item['secao']}")
            st.text(f"Documento: {item['fonte']} · Evidência: {item['id']}")
            st.code(item["trecho"], language=None)
    return len(valid)
