"""Cobertura documental e cadastro de novos procedimentos.

A versao anterior era cega para escrita: nao havia como ver o que ja estava
cadastrado. O usuario subia um arquivo, recebia 409 "documento ja cadastrado" e
nao tinha meio de descobrir o que existia. O campo de familia era texto livre,
entao digitar "Ventoinha" ou "ventoínha" tomava 422 da allowlist do servidor sem
explicar o porque.

GET /documentos e GET /familias resolvem os dois: a lista do que existe e o
vocabulario fechado para o formulario.
"""

import streamlit as st

import api
import estado
import formato

st.title("Documentos orientativos")

try:
    familias = estado.carregar_familias()
    documentos = estado.carregar_documentos()
except api.ErroDeApi as erro:
    st.error(str(erro))
    st.stop()

documentadas, total = familias.cobertura()
descobertas = familias.sem_documento()

col1, col2 = st.columns([1, 2])
col1.metric("Cobertura documental", f"{documentadas} de {total}",
            help="Famílias de falha com ao menos um documento cadastrado.")
with col2:
    st.markdown("**Por que isso importa**")
    st.caption(
        "Família de falha sem documento nunca recebe recomendação: o "
        "diagnóstico reconhece a falha e se contém, sem chamar o modelo. "
        "Cadastrar um documento é o que habilita a orientação."
    )

if descobertas:
    st.warning(
        "**Sem documento orientativo:** "
        + ", ".join(item["rotulo"] for item in descobertas)
        + ". Eventos destas famílias vão terminar em contenção.",
    )
else:
    st.success("Todas as famílias de falha têm documento cadastrado.")

st.divider()

# --- O que ja esta cadastrado --------------------------------------------

st.subheader("Cadastrados")
if not documentos:
    st.info(
        "Nenhum documento cadastrado. Se a API acabou de subir com banco novo, "
        "o bootstrap registra os documentos padrão — recarregue em instantes.",
    )
else:
    st.dataframe(
        [
            {
                "Família": documento["rotulo"],
                "Título": documento["titulo"],
                "Cadastrado em": formato.data(documento["cadastrado_em"]),
                "Identificador": documento["familia"],
            }
            for documento in documentos
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        f"{len(documentos)} documento(s). O caminho do arquivo em disco não é "
        "exposto pela API."
    )

st.divider()

# --- Cadastro ------------------------------------------------------------

st.subheader("Registrar novo documento")
st.caption(
    "O arquivo é fatiado em trechos e indexado para recuperação. PDF sem camada "
    "de texto extraível é recusado — não há OCR."
)

with st.form("cadastro_documento", clear_on_submit=True):
    familia_escolhida = st.selectbox(
        "Família de falha",
        options=[item["familia"] for item in familias.falhas()],
        format_func=lambda slug: (
            familias.rotulo(slug)
            + ("" if familias.documentado(slug) else "  —  sem documento")
        ),
        help="Lista fechada, vinda da própria API. Antes este campo era texto "
             "livre e qualquer grafia fora do identificador interno era "
             "recusada pelo servidor sem explicação.",
    )
    titulo = st.text_input(
        "Título do documento",
        help="Precisa ser único dentro da família — títulos repetidos são "
             "recusados para não duplicar trechos no índice.",
    )
    arquivo = st.file_uploader("Arquivo do procedimento",
                              type=["pdf", "md", "txt"],
                              help="Até 10 MB.")
    enviar = st.form_submit_button("Registrar", type="primary")

if enviar:
    if not arquivo or not titulo.strip():
        # Validacao antes da chamada: um 422 do servidor por campo vazio seria
        # uma ida a rede para dizer o que a tela ja sabe.
        st.error("Informe o título e selecione o arquivo.")
    else:
        try:
            with st.spinner("Enviando e indexando os trechos…"):
                resultado = api.registrar_documento(
                    familia_escolhida, titulo.strip(), arquivo.name,
                    arquivo.getvalue(),
                    arquivo.type or "application/octet-stream",
                )
            estado.invalidar_documentos()
            st.success(
                f"Documento registrado para **{familias.rotulo(familia_escolhida)}**: "
                f"{resultado['trechos_indexados']} trecho(s) indexado(s). "
                "A família passa a receber recomendação.",
            )
            st.rerun()
        except api.ApiRecusou as erro:
            # A API tem mensagem propria e especifica para cada recusa (titulo
            # duplicado, extensao, encoding, tamanho, documento sem conteudo
            # util). Repassar o detalhe dela e melhor que uma frase generica.
            if erro.status == 409:
                st.error(
                    f"Já existe documento com o título “{titulo.strip()}” para "
                    f"{familias.rotulo(familia_escolhida)}. Use outro título ou "
                    "confira a lista acima.",
                )
            else:
                st.error(erro.detalhe)
        except api.ErroDeApi as erro:
            st.error(str(erro))
