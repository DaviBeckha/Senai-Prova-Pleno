"""Dashboard de manutencao prescritiva — navegacao e contexto global.

Cliente puro da API: nao importa nada de app/ nem de scripts/, e nao le arquivo
do disco. A imagem do dashboard nao precisa carregar app/, scripts/ nem o
banner.xlsx de 21 MB.

Quatro paginas com URL propria (st.navigation), no lugar de st.tabs: cada
secao fica compartilhavel por link, o estado de cada uma e independente e o
Streamlit deixa de reexecutar as quatro a cada interacao.
"""

import streamlit as st

import api
import estado

st.set_page_config(
    page_title="Manutenção Prescritiva SENAI",
    layout="wide",
)


def _sidebar_estado_da_api() -> None:
    """Mostra a situacao da API antes de qualquer acao."""
    try:
        saude = estado.carregar_saude()
    except api.ErroDeApi as erro:
        st.sidebar.error(str(erro))
        return

    if saude.get("ready"):
        st.sidebar.success("API pronta")
    else:
        st.sidebar.warning(
            "API no ar, ainda inicializando — carga do histórico, motor de "
            "similaridade e modelo de embeddings (~1 GB no primeiro boot).",
            icon="⏳",
        )


def _sidebar_modo_do_llm() -> None:
    online = st.sidebar.toggle(
        "Modo online (OpenAI)",
        value=estado.modo() == "online",
        help="Desligado: modelo local via Ollama, sem sair da máquina. "
        "Ligado: modelo remoto da OpenAI, requer OPENAI_API_KEY na API.",
    )
    estado.definir_modo(online)
    if online:
        st.sidebar.caption("Redator: modelo remoto (OpenAI).")
    else:
        st.sidebar.caption(
            "Redator: modelo local (Ollama). A geração leva ~30 s na mediana "
            "em CPU e pode passar de 4 min em procedimento completo."
        )


def _sidebar_cobertura() -> None:
    """Resume a cobertura documental em todas as paginas."""
    try:
        familias = estado.carregar_familias()
    except api.ErroDeApi:
        return
    documentadas, total = familias.cobertura()
    st.sidebar.metric(
        "Cobertura documental",
        f"{documentadas} de {total}",
        help="Famílias de falha com documento orientativo cadastrado.",
    )
    descobertas = familias.sem_documento()
    if descobertas:
        with st.sidebar.expander(f"{len(descobertas)} sem documento"):
            for item in descobertas:
                st.write(f"— {item['rotulo']}")


paginas = st.navigation([
    st.Page(
        "paginas/historico.py",
        title="Histórico",
        icon=":material/analytics:",
        url_path="historico",
        default=True,
    ),
    st.Page(
        "paginas/diagnostico.py",
        title="Diagnóstico",
        icon=":material/troubleshoot:",
        url_path="diagnostico",
    ),
    st.Page(
        "paginas/chat.py",
        title="Chat",
        icon=":material/forum:",
        url_path="chat",
    ),
    st.Page(
        "paginas/documentos.py",
        title="Documentos",
        icon=":material/description:",
        url_path="documentos",
    ),
])

st.sidebar.title("Manutenção Prescritiva")
st.sidebar.caption("SENAI SC")
st.sidebar.divider()
_sidebar_estado_da_api()
_sidebar_modo_do_llm()
st.sidebar.divider()
_sidebar_cobertura()

paginas.run()
