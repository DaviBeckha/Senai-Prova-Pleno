import os
import sys
from pathlib import Path

# `streamlit run dashboard/app.py` insere dashboard/ no INICIO do sys.path, e
# entao `import app.*` resolveria para este proprio arquivo (dashboard/app.py)
# em vez do pacote app/ na raiz — "'app' is not a package". Poe a raiz do
# projeto na frente do path para desfazer o sombreamento. Precisa vir antes
# dos imports de app/ e scripts/ abaixo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

from app.data.labels import normalize_label
from scripts.simulator import build_payload

API_URL = os.environ.get("API_URL", "http://localhost:8000")


def _resolve_request_timeout() -> float:
    """Le DASHBOARD_TIMEOUT do ambiente com fallback defensivo.

    330s = OLLAMA_TIMEOUT maximo (300s) + folga de rede, para o dashboard
    nunca desistir antes da API/Ollama. Uma env vazia ou nao-numerica nao
    pode derrubar o import do modulo — cai no mesmo default 330.
    """
    try:
        return float(os.environ.get("DASHBOARD_TIMEOUT", "330"))
    except ValueError:
        return 330.0


REQUEST_TIMEOUT = _resolve_request_timeout()

st.set_page_config(page_title="Manutencao Prescritiva SENAI", layout="wide")
st.title("Manutenção Prescritiva — SENAI SC")


@st.cache_data
def load_data():
    """Load banner.xlsx with family and kind labels already computed."""
    df = pd.read_excel("banner.xlsx")
    infos = df["fault"].astype(str).map(normalize_label)
    df["family"] = [i.family for i in infos]
    df["kind"] = [i.kind for i in infos]
    return df


aba_hist, aba_chat, aba_doc = st.tabs(["Histórico", "Diagnóstico & Chat", "Documentos"])

with aba_hist:
    df = load_data()
    falhas = df[df["kind"] == "falha"]
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Ocorrências por família de falha")
        st.plotly_chart(px.bar(falhas["family"].value_counts()), use_container_width=True)
    with col2:
        st.subheader("Falhas ao longo do tempo")
        serie = falhas.set_index(pd.to_datetime(falhas["created_at"], utc=True))
        por_dia = serie.groupby([serie.index.date, "family"]).size().reset_index(name="n")
        por_dia.columns = ["dia", "family", "n"]
        st.plotly_chart(px.line(por_dia, x="dia", y="n", color="family"),
                        use_container_width=True)

with aba_chat:
    modo_online = st.toggle("Modo online (OpenAI)", value=False)
    modo = "online" if modo_online else "offline"
    st.caption("Desligado = Ollama local (offline). Ligado = gpt-5.6-luna via API.")

    # Seleção de evento: familia ou índice manual
    df = load_data()
    falhas = df[df["kind"] == "falha"]
    familias_unicas = sorted(falhas["family"].unique().tolist())

    familia_selecionada = st.selectbox("Selecione família de falha (ou índice manual)",
                                      options=["(digitar índice de linha)"] + familias_unicas)

    indice_manual = None
    if familia_selecionada == "(digitar índice de linha)":
        indice_manual = st.number_input("Índice da linha", min_value=0,
                                       max_value=len(df) - 1, value=0, step=1)

    if st.button("Sortear evento aleatório da família"):
        if familia_selecionada == "(digitar índice de linha)":
            row = df.iloc[int(indice_manual)]
        else:
            row = falhas[falhas["family"] == familia_selecionada].sample(1).iloc[0]

        # Build payload using the robust function from simulator
        try:
            payload = build_payload(row)
            payload["modo"] = modo

            try:
                r = httpx.post(f"{API_URL}/eventos", json=payload, timeout=REQUEST_TIMEOUT).json()
                # Duas grandezas distintas: neighbor_count é quantos vizinhos o
                # kNN desta consulta de fato votou (top-3 no caption abaixo);
                # total_ocorrencias/freq_per_day é o histórico completo da
                # família vencedora (occurrence_stats), não os vizinhos consultados.
                st.info(f"Status: {r['status']} | Família: {r['family']} — "
                        f"voto de {r['neighbor_count']} vizinhos mais próximos. "
                        f"Histórico da família: {r['total_ocorrencias']} ocorrências "
                        f"({r['freq_per_day']}/dia).")
                st.markdown(r["message"])

                # Comparação honesta: rótulo real vs diagnóstico
                st.divider()
                st.markdown("### Comparação: Rótulo Real × Diagnóstico")
                col_real, col_diag = st.columns(2)
                with col_real:
                    st.markdown(f"**Rótulo Real:** {row['fault']}")
                    st.markdown(f"_Família:_ `{row['family']}`")
                with col_diag:
                    st.markdown(f"**Diagnóstico:** {r['status']}")
                    st.markdown(f"_Família:_ `{r['family']}`")

                votos = r.get("family_votes", {})
                if votos:
                    st.caption("Votos kNN (top-3): " + ", ".join(
                        f"{f}: {v}" for f, v in
                        sorted(votos.items(), key=lambda kv: -kv[1])[:3]))

            except httpx.ConnectError:
                st.error("API indisponível — suba a API com uvicorn app.api.main:app")
            except Exception as e:
                st.error(f"Erro na chamada: {e}")
        except Exception as e:
            st.error(f"Erro ao processar linha: {e}")

    st.divider()
    pergunta = st.chat_input("Pergunte sobre uma falha (ex.: como corrigir correia frouxa?)")
    if pergunta:
        with st.chat_message("user"):
            st.write(pergunta)
        try:
            resp = httpx.post(f"{API_URL}/chat",
                            json={"pergunta": pergunta, "modo": modo},
                            timeout=REQUEST_TIMEOUT).json()
            with st.chat_message("assistant"):
                st.write(resp["resposta"])
                if resp["fontes"]:
                    st.caption("Fontes: " + ", ".join(resp["fontes"]))
                redator = resp.get("renderer") or "determinístico"
                st.caption(f"status: {resp.get('status', '?')} · redator: {redator}")
                if resp.get("degraded"):
                    st.warning(
                        "Resposta em modo degradado (modelo indisponível ou "
                        "rejeitado pela validação)."
                    )
                if resp.get("validation_errors"):
                    st.caption(
                        "Motivos da rejeição: "
                        + "; ".join(resp["validation_errors"])
                    )
                if resp.get("limitations"):
                    st.caption("Limitações:")
                    for limitacao in resp["limitations"]:
                        st.caption(f"- {limitacao}")
        except httpx.ConnectError:
            st.error("API indisponível — suba a API com uvicorn app.api.main:app")
        except Exception as e:
            st.error(f"Erro na chamada: {e}")

with aba_doc:
    st.subheader("Registrar novo documento orientativo")
    up = st.file_uploader("Documento do procedimento", type=["pdf", "md", "txt"])
    fam = st.text_input("Família da falha (ex.: ventoinha)")
    titulo = st.text_input("Título do documento")
    if st.button("Registrar") and up and fam and titulo:
        try:
            r = httpx.post(f"{API_URL}/documentos",
                           files={"file": (up.name, up.getvalue(), "application/pdf")},
                           data={"family": fam, "title": titulo}, timeout=300)
            st.success(f"Documento registrado: {r.json()['chunks']} trechos indexados")
        except httpx.ConnectError:
            st.error("API indisponível — suba a API com uvicorn app.api.main:app")
        except Exception as e:
            st.error(f"Erro ao registrar: {e}")
