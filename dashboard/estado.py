"""Estado da sessao e leituras cacheadas.

Duas coisas que a versao anterior nao tinha, e cuja ausencia era bug visivel:

1. O resultado do diagnostico vivia dentro de `if st.button(...)`. Como o
   Streamlit reexecuta o script inteiro a cada interacao, o bloco so renderizava
   na execucao em que o botao foi clicado: sortear um evento, ler o diagnostico e
   em seguida digitar no chat abaixo fazia o diagnostico DESAPARECER da tela.
2. O chat renderizava um par pergunta/resposta que era destruido no rerun
   seguinte — nao havia historico de conversa.

Os dois se resolvem guardando o resultado em st.session_state em vez de
depender do fluxo de execucao. As chaves ficam todas aqui para nao se
espalharem como strings soltas pelas paginas.
"""

import streamlit as st

# Import plano, nao `from dashboard import ...`: o Streamlit poe o diretorio do
# script principal em sys.path, entao `dashboard/` e a raiz de import em tempo
# de execucao. Os modulos puros (formato, confianca, graficos, vocabulario) nao
# importam nada do dashboard justamente para poderem ser carregados nos dois
# modos — como `dashboard.formato` na suite de testes e como `formato` aqui.
import api
from vocabulario import Familias

DIAGNOSTICO = "diagnostico_atual"
AMOSTRA = "amostra_atual"
MENSAGENS = "chat_mensagens"
MODO = "modo_llm"


# --- Leituras cacheadas ---------------------------------------------------
#
# O TTL evita que o dashboard fique preso a um estado antigo da API sem exigir
# invalidacao manual. Cobertura documental usa TTL curto porque muda por acao do
# proprio usuario, na pagina de documentos; o vocabulario e o historico so mudam
# com reinicio da API ou reseed.

@st.cache_data(ttl=300, show_spinner=False)
def _familias_cru() -> list[dict]:
    return api.familias()


def carregar_familias() -> Familias:
    return Familias(_familias_cru())


@st.cache_data(ttl=300, show_spinner=False)
def carregar_historico() -> dict:
    return api.historico_resumo()


@st.cache_data(ttl=30, show_spinner=False)
def carregar_documentos() -> list[dict]:
    return api.documentos()


def invalidar_documentos() -> None:
    """Chamada apos um upload bem-sucedido.

    Limpa tambem o vocabulario: registrar um documento muda o campo
    `documentado` de GET /familias, que alimenta o indicador de cobertura em
    todas as paginas.
    """
    carregar_documentos.clear()
    _familias_cru.clear()


@st.cache_data(ttl=10, show_spinner=False)
def carregar_saude() -> dict:
    """TTL de 10s: e um indicador ao vivo, mas nao vale uma chamada por rerun —
    o Streamlit reexecuta o script a cada tecla digitada em um input."""
    return api.saude()


# --- Modo do LLM ---------------------------------------------------------

def modo() -> str:
    """Offline (Ollama local) ou online (OpenAI).

    Ficava dentro da aba de chat e desaparecia nas outras. Agora vive na
    sidebar, entao precisa de um default explicito para quem abrir direto em
    /diagnostico por deep link, sem passar pela sidebar antes.
    """
    return st.session_state.get(MODO, "offline")


def definir_modo(online: bool) -> None:
    st.session_state[MODO] = "online" if online else "offline"


# --- Diagnostico ---------------------------------------------------------

def guardar_diagnostico(resposta: dict, amostra: dict) -> None:
    st.session_state[DIAGNOSTICO] = resposta
    st.session_state[AMOSTRA] = amostra


def diagnostico() -> tuple[dict | None, dict | None]:
    return st.session_state.get(DIAGNOSTICO), st.session_state.get(AMOSTRA)


def limpar_diagnostico() -> None:
    st.session_state.pop(DIAGNOSTICO, None)
    st.session_state.pop(AMOSTRA, None)


# --- Chat ----------------------------------------------------------------

def mensagens() -> list[dict]:
    return st.session_state.setdefault(MENSAGENS, [])


def registrar_pergunta(texto: str) -> None:
    mensagens().append({"papel": "user", "texto": texto})


def registrar_resposta(resposta: dict) -> None:
    """Guarda a resposta inteira, nao so o texto.

    Status, fontes, redator, limitacoes e erros de validacao precisam continuar
    disponiveis a cada rerun: sao eles que distinguem uma resposta fundamentada
    de uma contencao, e sem persistir tudo a distincao se perderia na primeira
    reexecucao do script.
    """
    mensagens().append({"papel": "assistant", "resposta": resposta})


def registrar_erro(mensagem: str) -> None:
    mensagens().append({"papel": "assistant", "erro": mensagem})


def limpar_conversa() -> None:
    st.session_state[MENSAGENS] = []
