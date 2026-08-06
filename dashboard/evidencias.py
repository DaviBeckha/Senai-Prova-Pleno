"""Apresentação auditável das evidências recuperadas pela API."""

from collections.abc import Callable

import streamlit as st


def mostrar_evidencias(
    items: list[dict],
    rotulo: Callable[[str], str],
) -> None:
    """Mantém trechos técnicos acessíveis sem poluir a orientação principal."""
    if not items:
        return

    with st.expander(f"Ver evidências e fontes ({len(items)})"):
        for position, item in enumerate(items):
            if position:
                st.divider()
            st.markdown(
                f"**{rotulo(item['familia'])} · {item['secao']}**"
            )
            st.caption(f"{item['fonte']} · evidência {item['id']}")
            st.code(item["trecho"], language=None)
