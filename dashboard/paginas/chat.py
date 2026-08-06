"""Chat sobre falhas e procedimentos cadastrados.

A versao anterior renderizava um par pergunta/resposta que era destruido no
rerun seguinte: nao havia historico de conversa. Agora as mensagens vivem em
st.session_state e sao re-renderizadas com todos os seus metadados — status,
fontes, redator, limitacoes e motivos de rejeicao —, que sao justamente o que
distingue uma resposta fundamentada de uma contencao.
"""

import streamlit as st

import api
import estado
import tempo
import vocabulario

st.title("Chat de manutenção")

try:
    familias = estado.carregar_familias()
except api.ErroDeApi as erro:
    st.error(str(erro))
    st.stop()

col_intro, col_limpar = st.columns([4, 1], vertical_alignment="bottom")
with col_intro:
    st.caption(
        "Responde apenas sobre falhas e procedimentos com documento cadastrado. "
        "Quando não há fonte suficiente, o sistema diz isso em vez de gerar "
        "orientação."
    )
with col_limpar:
    if st.button("Limpar conversa", use_container_width=True,
                 disabled=not estado.mensagens()):
        estado.limpar_conversa()
        st.rerun()


def _mostrar_resposta(resposta: dict) -> None:
    status = resposta["status"]
    st.markdown(resposta["resposta"])

    st.caption(f"**{vocabulario.titulo_chat(status)}** — "
               f"{vocabulario.explicacao_chat(status)}")
    if resposta.get("_tempo_total") is not None:
        st.caption(f"Tempo total: {resposta['_tempo_total']:.2f}s")

    if resposta["familias"]:
        rotulos = " · ".join(familias.rotulo(f) for f in resposta["familias"])
        st.caption(f"Famílias reconhecidas: {rotulos}")

    if resposta["fontes"]:
        st.caption("Fontes: " + ", ".join(resposta["fontes"]))

    st.caption(f"Redator: {vocabulario.nome_redator(resposta['redator'])}")

    if resposta["degradado"]:
        # Duas causas distintas chegam com degradado=True, e a diferenca importa:
        # sem erros_de_validacao, o modelo nao respondeu; com eles, o modelo
        # respondeu e o validador de fundamentacao recusou o texto.
        if resposta["erros_de_validacao"]:
            st.warning(
                "**Geração rejeitada pela validação de fundamentação.** O modelo "
                "respondeu, mas o texto não teve suporte suficiente nos trechos "
                "citados; o que aparece acima é extração determinística.",
            )
        else:
            st.warning(
                "**Modelo indisponível.** A resposta acima vem de extração "
                "determinística dos trechos recuperados, não de geração.",
            )

    if resposta["erros_de_validacao"]:
        with st.expander(f"Motivos da rejeição "
                         f"({len(resposta['erros_de_validacao'])})"):
            for motivo in resposta["erros_de_validacao"]:
                st.markdown(f"— {motivo}")

    if resposta["limitacoes"]:
        with st.expander(f"Limitações declaradas "
                         f"({len(resposta['limitacoes'])})", expanded=True):
            for limitacao in resposta["limitacoes"]:
                st.markdown(f"— {limitacao}")

    if status == "fora_de_escopo":
        # Numa avaliacao local, variacoes naturais foram classificadas como fora
        # de escopo por falta de alias ("esferas do rolamento" falhou; "esfera do
        # rolamento" funcionou). Listar o vocabulario reconhecido transforma um
        # beco sem saida em proxima tentativa.
        with st.expander("Famílias que o sistema reconhece"):
            for item in familias.falhas():
                marca = "" if item["documentado"] else "  _(sem documento)_"
                st.markdown(f"— {item['rotulo']}{marca}")


for mensagem in estado.mensagens():
    with st.chat_message(mensagem["papel"]):
        if "texto" in mensagem:
            st.markdown(mensagem["texto"])
        elif "erro" in mensagem:
            st.error(mensagem["erro"])
        else:
            _mostrar_resposta(mensagem["resposta"])

pergunta = st.chat_input("Ex.: como corrigir uma correia frouxa?")
if pergunta:
    estado.registrar_pergunta(pergunta)
    with st.chat_message("user"):
        st.markdown(pergunta)

    modo = estado.modo()
    espera = ("~30 s na mediana em CPU, mais em pedido de procedimento completo."
              if modo == "offline" else "Consultando o modelo remoto.")
    with st.chat_message("assistant"):
        try:
            with st.spinner(f"Consultando… {espera}"):
                execucao = tempo.medir(lambda: api.perguntar(pergunta, modo))
            resposta = execucao.valor
            resposta["_tempo_total"] = execucao.elapsed_seconds
            estado.registrar_resposta(resposta)
            _mostrar_resposta(resposta)
        except api.ErroDeApi as erro:
            estado.registrar_erro(str(erro))
            st.error(str(erro))

if not estado.mensagens():
    st.caption("Sugestões:")
    documentadas = [item for item in familias.falhas() if item["documentado"]]
    for item in documentadas[:4]:
        st.caption(f"— Como corrigir {item['rotulo'].lower()}?")
    sem_documento = familias.sem_documento()
    if sem_documento:
        st.caption(
            f"— Existe documento cadastrado para "
            f"{sem_documento[0]['rotulo'].lower()}?  "
            "_(demonstra a contenção por falta de fonte)_"
        )
