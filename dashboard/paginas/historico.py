"""Historico do corpus: o que existe nos dados antes de qualquer diagnostico.

Os dois graficos vem de GET /historico/resumo — agregados do MESMO DataFrame
que alimenta o motor de similaridade. Antes, esta pagina lia banner.xlsx do
proprio disco e reaplicava normalize_label: se o seed do banco divergisse do
arquivo, o grafico mostrava um corpus e o kNN usava outro.
"""

import streamlit as st

import api
import estado
import formato
import graficos

st.title("Histórico de leituras")
st.caption(
    "Base real usada pelo motor de similaridade e pelo cálculo de estatísticas "
    "de ocorrência. Serve para situar quais famílias existem, quão "
    "desbalanceadas são e como se distribuem no tempo."
)

try:
    resumo = estado.carregar_historico()
    familias = estado.carregar_familias()
except api.ErroDeApi as erro:
    st.error(str(erro), icon="⚠️")
    st.stop()

por_familia = resumo["por_familia"]
falhas = [item for item in por_familia if item["tipo"] == "falha"]
estados = [item for item in por_familia if item["tipo"] == "estado"]

if not por_familia:
    # Empty state honesto: eixo em branco nao informa que nao ha dado.
    st.info(
        "Nenhuma leitura no histórico. Semeie a tabela `sensor_readings` "
        "(primeiro boot da API com `DATA_FILE` apontando para o dataset).",
        icon="📭",
    )
    st.stop()

total_falhas = sum(item["ocorrencias"] for item in falhas)
total_estados = sum(item["ocorrencias"] for item in estados)
janela = resumo["janela"]
dias = formato.dias_no_periodo(janela["primeira"], janela["ultima"])

col1, col2, col3, col4 = st.columns(4)
col1.metric("Leituras", formato.inteiro(resumo["total_leituras"]))
col2.metric("Famílias de falha", str(len(falhas)),
            help="Famílias distintas com ao menos uma ocorrência no histórico.")
col3.metric("Período", formato.periodo(janela["primeira"], janela["ultima"]),
            help=f"{dias} dias" if dias else None)
col4.metric("Proporção de falha",
            formato.porcentagem(total_falhas, resumo["total_leituras"]),
            help=f"{formato.inteiro(total_falhas)} leituras de falha e "
                 f"{formato.inteiro(total_estados)} de estado de operação.")

st.divider()

# --- Ocorrencias por familia ---------------------------------------------

st.subheader("Ocorrências por família de falha")
st.caption(
    "Uma leitura rotulada por ocorrência. O desbalanceamento entre famílias é "
    "o que explica a incerteza do voto kNN na página de diagnóstico."
)
st.plotly_chart(
    graficos.ocorrencias_por_familia(falhas, familias.rotulo),
    use_container_width=True,
    theme="streamlit",
)

with st.expander("Ver como tabela"):
    # Alternativa acessivel ao grafico: leitor de tela nao le uma figura, e tres
    # cores da paleta ficam abaixo de 3:1 no tema claro — a regra de alivio da
    # skill de dataviz pede rotulo visivel ou vista de tabela, e aqui ha as duas.
    st.dataframe(
        [
            {
                "Família de falha": familias.rotulo(item["familia"]),
                "Ocorrências": item["ocorrencias"],
                "Identificador": item["familia"],
                "Documento cadastrado": "sim" if familias.documentado(item["familia"]) else "não",
            }
            for item in sorted(falhas, key=lambda i: -i["ocorrencias"])
        ],
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# --- Falhas ao longo do tempo --------------------------------------------

st.subheader("Falhas ao longo do tempo")

ordem = graficos.ordem_canonica(falhas)
padrao = ordem[:5]
selecionadas = st.multiselect(
    "Famílias exibidas",
    options=ordem,
    default=padrao,
    format_func=familias.rotulo,
    max_selections=graficos.MAX_SERIES,
    help=f"Até {graficos.MAX_SERIES} famílias por vez. A paleta tem "
         f"{graficos.MAX_SERIES} cores validadas para distinção segura, "
         "inclusive para daltonismo — acima disso a nona série seria uma cor "
         "gerada, indistinguível de outra.",
)

if not selecionadas:
    st.info("Selecione ao menos uma família para ver a série temporal.", icon="👆")
else:
    dias_por_familia = [
        item for item in resumo["por_dia"] if item["familia"] in set(selecionadas)
    ]
    st.plotly_chart(
        graficos.falhas_ao_longo_do_tempo(
            dias_por_familia, selecionadas, ordem, familias.rotulo),
        use_container_width=True,
        theme="streamlit",
    )
    st.caption(
        "A cor de cada família é fixa: mudar a seleção não repinta as que "
        "permanecem. Famílias além da oitava em volume reaparecem com o mesmo "
        "tom em traço tracejado, para que a identidade nunca dependa só da cor."
    )
