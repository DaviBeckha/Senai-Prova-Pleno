"""Diagnostico de um evento real do historico.

Tres coisas que a versao anterior nao mostrava e que mudam a leitura do
resultado:

1. Quanto o voto kNN realmente sustenta. A API responde `status: "diagnostico"`
   tanto para 56% de suporte quanto para 18% com empate triplo, e a tela dizia
   apenas "voto de 50 vizinhos mais proximos" — que se le como conclusao firme.
2. Se o texto veio do modelo ou de extracao deterministica. O campo `degradado`
   existia no contrato e nao era renderizado aqui: numa avaliacao local do modo
   offline, 43,75% das geracoes foram rejeitadas pelo grounding e cairam no
   template.
3. Quais documentos fundamentaram a resposta. `fontes` chegava e era ignorado.

E o resultado agora sobrevive ao rerun: antes vivia dentro de `if st.button()`,
entao qualquer interacao posterior o apagava da tela.
"""

import streamlit as st

import api
import confianca as conf
import estado
import formato
import graficos
import vocabulario

st.title("Diagnóstico de evento")

try:
    familias = estado.carregar_familias()
except api.ErroDeApi as erro:
    st.error(str(erro), icon="⚠️")
    st.stop()

falhas = familias.falhas()
if not falhas:
    st.error("Vocabulário de famílias vazio — a API não está pronta.", icon="⚠️")
    st.stop()

col_familia, col_acao = st.columns([3, 1], vertical_alignment="bottom")
with col_familia:
    escolhida = st.selectbox(
        "Família de falha",
        options=[item["familia"] for item in falhas],
        format_func=familias.rotulo,
        help="Sorteia uma leitura real desta família no histórico e a envia "
             "para diagnóstico. O identificador interno é preservado; a tela "
             "mostra o rótulo.",
    )
with col_acao:
    sortear = st.button("Sortear e diagnosticar", type="primary",
                        use_container_width=True)

if not familias.documentado(escolhida):
    st.info(
        f"**{familias.rotulo(escolhida)}** não tem documento orientativo "
        "cadastrado. O diagnóstico vai reconhecer a falha e se conter, sem "
        "recomendar ação — é o comportamento esperado, não uma falha do sistema.",
        icon="📄",
    )

if sortear:
    modo = estado.modo()
    espera = ("A geração roda em CPU: ~30 s na mediana, mais em procedimento "
              "completo." if modo == "offline" else "Consultando o modelo remoto.")
    try:
        with st.spinner(f"Sorteando leitura e diagnosticando… {espera}"):
            amostra = api.amostra(escolhida)
            resposta = api.diagnosticar(amostra["features"], modo)
        estado.guardar_diagnostico(resposta, amostra)
    except api.ErroDeApi as erro:
        estado.limpar_diagnostico()
        st.error(str(erro), icon="⚠️")

resposta, amostra = estado.diagnostico()
if resposta is None:
    st.caption("Nenhum diagnóstico nesta sessão ainda.")
    st.stop()

st.divider()

# --- Desfecho -------------------------------------------------------------

status = resposta["status"]
st.subheader(vocabulario.titulo_diagnostico(status))
st.caption(vocabulario.explicacao_diagnostico(status))

# --- Confianca do voto kNN ------------------------------------------------
#
# Vem antes da mensagem de proposito: se a classificacao e inconclusiva, isso
# precisa ser lido ANTES da recomendacao, nao depois.

certeza = conf.avaliar(resposta["votos_por_familia"],
                       resposta["vizinhos_consultados"])

col1, col2, col3 = st.columns(3)
col1.metric("Família diagnosticada", resposta["rotulo"])
if certeza:
    col2.metric(
        "Suporte do voto",
        f"{certeza.votos} de {certeza.total}",
        delta=formato.porcentagem(certeza.votos, certeza.total),
        delta_color="off",
        help="Quantos dos vizinhos mais próximos votaram na família vencedora.",
    )
col3.metric("Ocorrências no histórico",
            formato.inteiro(resposta["total_ocorrencias"]),
            help=f"{formato.decimal(resposta['frequencia_por_dia'])} por dia no "
                 f"período de "
                 f"{formato.periodo(resposta['ocorrencias']['primeira'], resposta['ocorrencias']['ultima'])}.")

if certeza and certeza.inconclusiva:
    st.warning(certeza.motivo(familias.rotulo), icon="⚖️")

# --- Rotulo real x diagnostico -------------------------------------------

if amostra:
    familia_real = amostra["familia"]
    concordam = familia_real == resposta["familia"]
    veredito = ("Diagnóstico coincide com o rótulo real."
                if concordam else "Diagnóstico divergiu do rótulo real.")
    # Icone + texto, nunca so cor: a conclusao tem de ser legivel sem depender
    # de distinguir verde de vermelho.
    (st.success if concordam else st.error)(
        f"**{veredito}**  \n"
        f"Rótulo real da leitura: `{amostra['rotulo_original']}` "
        f"→ {familias.rotulo(familia_real)}  \n"
        f"Diagnóstico: {resposta['rotulo']}",
        icon="✅" if concordam else "❌",
    )
    if amostra["features_substituidas"]:
        colunas = ", ".join(f"`{c}`" for c in amostra["features_substituidas"])
        st.caption(
            f"Atenção: {len(amostra['features_substituidas'])} feature(s) desta "
            f"leitura estavam vazias no histórico e foram enviadas como 0.0 "
            f"({colunas}). O dataset original tem artefato de datetime em coluna "
            "numérica em parte das linhas."
        )

# --- Recomendacao ---------------------------------------------------------

st.subheader("Recomendação")

if resposta["degradado"]:
    st.warning(
        "**Texto não produzido pelo modelo.** A geração foi rejeitada pela "
        "validação de fundamentação e o sistema caiu para extração "
        "determinística dos trechos recuperados. Trate como evidência bruta, "
        "não como orientação redigida.",
        icon="🛟",
    )

mensagem = resposta["mensagem"]
# O template extrativo pode despejar dezenas de trechos: numa avaliacao local,
# uma consulta de procedimento completo devolveu 58. Longo demais para ficar
# aberto por default, mas nada e escondido.
if len(mensagem) > 1500:
    st.caption(f"Resposta longa ({formato.inteiro(len(mensagem))} caracteres).")
    with st.expander("Ver a recomendação completa", expanded=False):
        st.markdown(mensagem)
else:
    st.markdown(mensagem)

col_fontes, col_redator = st.columns(2)
with col_fontes:
    if resposta["fontes"]:
        st.markdown("**Fontes**")
        for fonte in resposta["fontes"]:
            st.markdown(f"— {fonte}")
    else:
        st.markdown("**Fontes**")
        st.caption("Nenhuma — o sistema não gerou recomendação fundamentada.")
with col_redator:
    st.markdown("**Redator**")
    st.caption(vocabulario.nome_redator(resposta["redator"]))

if resposta["erros_de_validacao"]:
    with st.expander(
            f"Por que a geração foi rejeitada "
            f"({len(resposta['erros_de_validacao'])} motivo(s))"):
        for motivo in resposta["erros_de_validacao"]:
            st.markdown(f"— {motivo}")
        st.caption(
            "A validação exige que cada ação recomendada tenha suporte léxico "
            "no trecho citado. Abaixo do limiar, a geração é descartada em vez "
            "de exibida."
        )

st.divider()

# --- Distribuicao do voto ------------------------------------------------

if certeza:
    st.subheader("Distribuição do voto kNN")
    st.caption(
        "As famílias se sobrepõem no espaço de features de vibração. A "
        "distribuição completa mostra o quanto a vencedora realmente se separou "
        "das demais — informação que um rótulo único esconde."
    )
    ordenados = conf.ordenar_votos(resposta["votos_por_familia"])
    vencedoras = {certeza.vencedora, *certeza.empatadas}
    st.plotly_chart(
        graficos.votos_do_knn(ordenados, vencedoras, certeza.total,
                              familias.rotulo),
        use_container_width=True,
        theme="streamlit",
    )
    with st.expander("Ver como tabela"):
        st.dataframe(
            [
                {
                    "Família": familias.rotulo(familia),
                    "Votos": votos,
                    "Suporte": formato.porcentagem(votos, certeza.total),
                    "Vencedora": "sim" if familia in vencedoras else "",
                }
                for familia, votos in ordenados
            ],
            use_container_width=True,
            hide_index=True,
        )

# --- Janela historica ----------------------------------------------------

por_dia = resposta["ocorrencias"]["por_dia"]
if por_dia:
    st.subheader(f"Histórico de {resposta['rotulo']}")
    col_janela, col_spark = st.columns([1, 3])
    with col_janela:
        st.metric("Média diária",
                  formato.decimal(resposta["frequencia_por_dia"]))
        st.caption(
            formato.periodo(resposta["ocorrencias"]["primeira"],
                            resposta["ocorrencias"]["ultima"])
        )
        dias = formato.dias_no_periodo(resposta["ocorrencias"]["primeira"],
                                       resposta["ocorrencias"]["ultima"])
        if dias:
            st.caption(f"{dias} dias de janela")
    with col_spark:
        st.plotly_chart(graficos.ocorrencias_por_dia(por_dia),
                        use_container_width=True, theme="streamlit")
