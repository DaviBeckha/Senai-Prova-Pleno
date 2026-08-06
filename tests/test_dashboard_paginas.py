"""Cada pagina do dashboard renderiza sem excecao, contra o contrato real.

Usa streamlit.testing.AppTest, que executa o script da pagina de verdade — nao
apenas importa. Isso pega o que um GET na porta 8501 nao pega: o Streamlit
renderiza no cliente, entao a pagina pode estourar e o HTML da casca ainda voltar
200.

As respostas falsas aqui sao copias fieis do contrato de app/api/schemas.py. Se
um campo for renomeado no backend sem ajustar a tela, estes testes quebram — e o
acoplamento entre os dois merece ser verificado, ja que o dashboard passou a ser
cliente puro da API.
"""

import sys
from pathlib import Path

import pytest

_DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"
# As paginas usam import plano (`import api`), porque sob `streamlit run` o
# diretorio do script principal e a raiz de import. Reproduzir isso aqui e o que
# permite executa-las fora do Streamlit.
#
# APPEND, nunca insert(0): dashboard/app.py sombrearia o pacote app/ se viesse
# antes da raiz do projeto no sys.path — `import app` acharia o script do
# Streamlit, um modulo, e `from app.api import ...` falharia com "'app' is not a
# package". E a mesma armadilha que o dashboard antigo contornava com um
# sys.path.insert proprio. No fim da lista, a raiz do projeto (inserida pelo
# pytest) ganha para `app`, e `dashboard/` continua sendo o unico a prover
# `api`, `estado`, `graficos` e companhia.
if str(_DASHBOARD) not in sys.path:
    sys.path.append(str(_DASHBOARD))

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

FAMILIAS = [
    {"familia": "correia", "rotulo": "Correia", "tipo": "falha",
     "documentado": True},
    {"familia": "rolamento_inner", "rotulo": "Rolamento — pista interna",
     "tipo": "falha", "documentado": True},
    {"familia": "ventoinha", "rotulo": "Ventoinha", "tipo": "falha",
     "documentado": False},
    {"familia": "eccentric_rotor", "rotulo": "Rotor excêntrico", "tipo": "falha",
     "documentado": False},
    {"familia": "normal", "rotulo": "Normal", "tipo": "estado",
     "documentado": False},
]

HISTORICO = {
    "total_leituras": 166796,
    "janela": {"primeira": "2026-05-02", "ultima": "2026-06-30"},
    "por_familia": [
        {"familia": "rolamento_inner", "tipo": "falha", "ocorrencias": 24310},
        {"familia": "ventoinha", "tipo": "falha", "ocorrencias": 12299},
        {"familia": "correia", "tipo": "falha", "ocorrencias": 11999},
        {"familia": "eccentric_rotor", "tipo": "falha", "ocorrencias": 900},
        {"familia": "normal", "tipo": "estado", "ocorrencias": 15058},
    ],
    "por_dia": [
        {"dia": "2026-05-02", "familia": "correia", "ocorrencias": 118},
        {"dia": "2026-05-03", "familia": "correia", "ocorrencias": 96},
        {"dia": "2026-05-02", "familia": "ventoinha", "ocorrencias": 40},
        {"dia": "2026-05-02", "familia": "rolamento_inner", "ocorrencias": 210},
    ],
}

DOCUMENTOS = [
    {"familia": "correia", "rotulo": "Correia", "titulo": "Doc4 - Correias",
     "cadastrado_em": "2026-06-01T10:00:00+00:00"},
]

AMOSTRA = {
    "id_externo": 102543,
    "rotulo_original": "correia_2",
    "familia": "correia",
    "features": {"rpm": 1798.0, "temperature_c": 41.2},
    "features_substituidas": ["z_kurtosis"],
}

# Diagnostico com empate no topo: e o caso que a tela precisa denunciar como
# inconclusivo (correia venceu com 9 de 50, empatada com outras duas).
DIAGNOSTICO_EMPATE = {
    "status": "diagnostico",
    "familia": "correia",
    "rotulo": "Correia",
    "mensagem": "Ajustar a tensão da correia até a deflexão especificada.",
    "total_ocorrencias": 11999,
    "frequencia_por_dia": 1499.88,
    "ocorrencias": {
        "primeira": "2026-06-01T00:00:00+00:00",
        "ultima": "2026-06-08T00:00:00+00:00",
        "por_dia": {"2026-06-01": 1500, "2026-06-02": 1499},
    },
    "fontes": ["Doc4.pdf"],
    "redator": "template",
    "degradado": True,
    "erros_de_validacao": ["passo 1: ação possui suporte lexical de 0.40, "
                           "abaixo de 0.60"],
    "evidencias": [{
        "id": "correia:E1",
        "familia": "correia",
        "fonte": "Doc4.pdf",
        "secao": "9.1 Correia Frouxa",
        "trecho": "Ajustar a tensão da correia.",
    }],
    "votos_por_familia": {"correia": 9, "rolamento_outer": 9,
                          "rolamento_ball": 9, "rolamento_inner": 7,
                          "normal": 2},
    "vizinhos_consultados": 50,
}

CHAT_RESPONDIDO = {
    "status": "respondido",
    "resposta": "- Ajustar tensão [Doc4.pdf — seção 9.1].",
    "familias": ["correia"],
    "fontes": ["Doc4.pdf"],
    "redator": "ollama",
    "degradado": False,
    "limitacoes": ["A evidência não cobre o torque exato de reaperto."],
    "erros_de_validacao": [],
    "evidencias": [{
        "id": "correia:E1",
        "familia": "correia",
        "fonte": "Doc4.pdf",
        "secao": "9.1 Correia Frouxa",
        "trecho": "Ajustar a tensão da correia.",
    }],
}


@pytest.fixture(autouse=True)
def api_falsa(monkeypatch):
    """Substitui o cliente HTTP e limpa os caches de st.cache_data.

    Sem o clear, a primeira resposta falsa sobreviveria entre testes e um teste
    passaria com o dado de outro.
    """
    import api
    import estado

    monkeypatch.setattr(api, "saude",
                        lambda: {"status": "ok", "ready": True,
                                 "llm_mode": "offline"})
    monkeypatch.setattr(api, "familias", lambda: list(FAMILIAS))
    monkeypatch.setattr(api, "historico_resumo", lambda: dict(HISTORICO))
    monkeypatch.setattr(api, "documentos", lambda: list(DOCUMENTOS))
    monkeypatch.setattr(api, "amostra", lambda familia: dict(AMOSTRA))
    monkeypatch.setattr(api, "diagnosticar",
                        lambda features, modo: dict(DIAGNOSTICO_EMPATE))
    monkeypatch.setattr(api, "perguntar",
                        lambda pergunta, modo: dict(CHAT_RESPONDIDO))
    monkeypatch.setattr(api, "registrar_documento",
                        lambda *a, **k: {"trechos_indexados": 12})

    for cacheada in (estado._familias_cru, estado.carregar_historico,
                     estado.carregar_documentos, estado.carregar_saude):
        cacheada.clear()
    yield
    for cacheada in (estado._familias_cru, estado.carregar_historico,
                     estado.carregar_documentos, estado.carregar_saude):
        cacheada.clear()


def _rodar(pagina: str) -> "AppTest":
    prova = AppTest.from_file(str(_DASHBOARD / "paginas" / pagina),
                             default_timeout=30)
    prova.run()
    assert not prova.exception, [str(e) for e in prova.exception]
    return prova


def _rodar_app() -> "AppTest":
    """Casca de navegacao: st.navigation + sidebar global.

    O AppTest nao simula o roteamento de paginas, entao `paginas.run()` nao
    executa a pagina default aqui — as quatro sao exercitadas uma a uma por
    _rodar(). O que este caminho verifica e o resto: as quatro st.Page sao
    construidas e aceitas (caminho relativo resolvido, icone valido) e a sidebar
    renderiza estado da API, modo do LLM e cobertura.
    """
    prova = AppTest.from_file(str(_DASHBOARD / "app.py"), default_timeout=30)
    prova.run()
    assert not prova.exception, [str(e) for e in prova.exception]
    return prova


def test_dashboard_no_sys_path_nao_sombreia_o_pacote_app():
    # Regressao: com dashboard/ ANTES da raiz do projeto no sys.path, `import app`
    # resolve para dashboard/app.py — um modulo, nao o pacote — e todo
    # `from app.api import ...` da suite quebra com "'app' is not a package".
    # Verificado: nessa ordem, importar `app` chega a EXECUTAR o script do
    # Streamlit. Passa hoje so por acidente da ordem alfabetica de coleta do
    # pytest, entao a garantia precisa ser explicita.
    import app

    assert hasattr(app, "__path__"), (
        "o pacote app/ foi sombreado por dashboard/app.py — use sys.path.append"
    )
    from app.api import schemas

    assert schemas.DiagnosticoOut


def test_app_monta_navegacao_e_sidebar_sem_excecao():
    _rodar_app()


def test_sidebar_mostra_api_pronta_e_cobertura():
    prova = _rodar_app()

    assert [s.value for s in prova.sidebar.success] == ["API pronta"]
    metricas = {m.label: m.value for m in prova.sidebar.metric}
    assert metricas["Cobertura documental"] == "2 de 4"


def test_sidebar_avisa_bootstrap_em_andamento_sem_tratar_como_erro():
    # ready=False e estado esperado no primeiro boot (carga do historico e ~1 GB
    # de embeddings), nao falha: precisa ser aviso, nao erro.
    import api

    api_pronta = api.saude
    api.saude = lambda: {"status": "ok", "ready": False, "llm_mode": "offline"}
    try:
        import estado
        estado.carregar_saude.clear()
        prova = _rodar_app()
        assert not prova.sidebar.error
        assert "inicializando" in prova.sidebar.warning[0].value
    finally:
        api.saude = api_pronta
        estado.carregar_saude.clear()


def test_sidebar_reporta_api_fora_do_ar_sem_mandar_subir_uvicorn():
    # A mensagem antiga dizia "suba a API com uvicorn app.api.main:app",
    # instrucao errada quando o stack sobe por docker compose.
    import api

    api_pronta = api.saude

    def _cai():
        raise api.ApiIndisponivel()

    api.saude = _cai
    try:
        import estado
        estado.carregar_saude.clear()
        prova = _rodar_app()
        texto = prova.sidebar.error[0].value
        assert "uvicorn" not in texto
        assert "API" in texto
    finally:
        api.saude = api_pronta
        estado.carregar_saude.clear()


def _textos(prova) -> str:
    """Todo texto renderizado, concatenado, para assercoes de conteudo."""
    partes = []
    for colecao in (prova.markdown, prova.caption, prova.warning, prova.error,
                    prova.success, prova.info, prova.subheader, prova.title):
        partes.extend(elemento.value for elemento in colecao)
    for metrica in prova.metric:
        partes.extend([metrica.label, str(metrica.value)])
    return "\n".join(partes)


# --- Historico -------------------------------------------------------------

def test_pagina_historico_renderiza_sem_excecao():
    _rodar("historico.py")


def test_pagina_historico_formata_numeros_em_padrao_brasileiro():
    texto = _textos(_rodar("historico.py"))

    assert "166.796" in texto
    assert "02/05/2026 a 30/06/2026" in texto


def test_pagina_historico_nao_deixa_slug_em_ingles_na_tela():
    # O objetivo do trabalho: nenhum identificador cru onde se le texto.
    prova = _rodar("historico.py")

    texto = _textos(prova)
    for slug in ("eccentric_rotor", "rolamento_inner", "cocked_rotor"):
        assert slug not in texto

    # O seletor de familias e o controle onde o vazamento era mais visivel: ele
    # lista as familias uma a uma. _textos() nao o alcanca, entao a checagem
    # precisa ser explicita — sem ela este teste passaria por omissao.
    exibidas = prova.multiselect[0].options
    assert "Rolamento — pista interna" in exibidas
    assert "Rotor excêntrico" in exibidas
    assert not [rotulo for rotulo in exibidas if "_" in rotulo]


def test_pagina_historico_pre_seleciona_as_cinco_maiores_familias():
    # Doze linhas simultaneas sao ilegiveis; a paleta valida oito series. O
    # default mostra as cinco de maior volume.
    prova = _rodar("historico.py")

    selecionadas = prova.multiselect[0].value
    assert len(selecionadas) <= 5
    assert "rolamento_inner" in selecionadas  # maior volume no fixture


def test_pagina_historico_conta_apenas_familias_de_falha():
    # normal e estado de operacao: entra no total de leituras, nao na contagem
    # de familias de falha nem no grafico.
    metricas = {m.label: m.value for m in _rodar("historico.py").metric}

    assert metricas["Famílias de falha"] == "4"


# --- Diagnostico -----------------------------------------------------------

def test_pagina_diagnostico_renderiza_sem_excecao():
    _rodar("diagnostico.py")


def test_pagina_diagnostico_sem_resultado_nao_inventa_conteudo():
    prova = _rodar("diagnostico.py")

    assert "Nenhum diagnóstico nesta sessão ainda." in _textos(prova)


def test_pagina_diagnostico_denuncia_empate_no_voto_knn():
    # O achado central: a API devolve status "diagnostico" para um empate
    # triplo com 18% de suporte, e a tela nao pode apresentar isso como
    # conclusao firme.
    prova = _rodar("diagnostico.py")
    prova.button[0].click().run()
    assert not prova.exception, [str(e) for e in prova.exception]

    texto = _textos(prova)
    assert "inconclusiva" in texto.lower()
    assert "9 de 50" in texto
    assert "hipótese" in texto


def test_pagina_diagnostico_avisa_que_o_texto_nao_veio_do_modelo():
    prova = _rodar("diagnostico.py")
    prova.button[0].click().run()

    texto = _textos(prova)
    assert "não produzido pelo modelo" in texto.lower()
    assert "suporte lexical" in texto


def test_pagina_diagnostico_mostra_fontes_e_redator():
    # Os dois chegavam no contrato e nao eram renderizados nesta tela.
    prova = _rodar("diagnostico.py")
    prova.button[0].click().run()

    texto = _textos(prova)
    assert "Doc4.pdf" in texto
    assert "determinística" in texto


def test_pagina_diagnostico_coloca_evidencia_bruta_em_expansor():
    prova = _rodar("diagnostico.py")
    prova.button[0].click().run()

    assert any(
        expander.label == "Ver evidências e fontes (1)"
        for expander in prova.expander
    )
    assert any(
        "Ajustar a tensão da correia." in bloco.value
        for bloco in prova.code
    )


def test_pagina_diagnostico_compara_rotulo_real_com_o_diagnostico():
    prova = _rodar("diagnostico.py")
    prova.button[0].click().run()

    texto = _textos(prova)
    assert "correia_2" in texto
    assert "coincide" in texto.lower()


def test_pagina_diagnostico_avisa_feature_substituida_por_zero():
    prova = _rodar("diagnostico.py")
    prova.button[0].click().run()

    assert "z_kurtosis" in _textos(prova)


def test_pagina_diagnostico_sobrevive_a_rerun():
    # O bug corrigido: o resultado vivia dentro de `if st.button()`, entao
    # qualquer interacao posterior o apagava da tela.
    prova = _rodar("diagnostico.py")
    prova.button[0].click().run()
    assert "9 de 50" in _textos(prova)

    prova.run()  # rerun sem clicar em nada

    assert not prova.exception, [str(e) for e in prova.exception]
    assert "9 de 50" in _textos(prova)


# --- Chat ------------------------------------------------------------------

def test_pagina_chat_renderiza_sem_excecao():
    _rodar("chat.py")


def test_pagina_chat_guarda_historico_da_conversa():
    # O outro bug: cada pergunta renderizava um par que era destruido no rerun.
    prova = _rodar("chat.py")
    prova.chat_input[0].set_value("como corrigir correia frouxa?").run()
    assert not prova.exception, [str(e) for e in prova.exception]
    assert "Ajustar tensão" in _textos(prova)

    prova.run()  # rerun sem digitar nada

    assert not prova.exception, [str(e) for e in prova.exception]
    texto = _textos(prova)
    assert "como corrigir correia frouxa?" in texto
    assert "Ajustar tensão" in texto


def test_pagina_chat_traduz_o_status_para_frase_legivel():
    prova = _rodar("chat.py")
    prova.chat_input[0].set_value("como corrigir correia?").run()

    texto = _textos(prova)
    assert "Respondido com fonte" in texto
    assert "respondido" not in texto.split("Respondido com fonte")[0]


def test_pagina_chat_mostra_limitacoes_declaradas():
    prova = _rodar("chat.py")
    prova.chat_input[0].set_value("como corrigir correia?").run()

    assert "torque exato" in _textos(prova)


def test_pagina_chat_coloca_evidencia_bruta_em_expansor():
    prova = _rodar("chat.py")
    prova.chat_input[0].set_value("como corrigir correia?").run()

    assert any(
        expander.label == "Ver evidências e fontes (1)"
        for expander in prova.expander
    )
    assert any("Doc4.pdf" in caption.value for caption in prova.caption)
    assert any(
        "Ajustar a tensão da correia." in bloco.value
        for bloco in prova.code
    )


# --- Documentos ------------------------------------------------------------

def test_pagina_documentos_renderiza_sem_excecao():
    _rodar("documentos.py")


def test_pagina_documentos_mostra_cobertura_e_nomeia_as_descobertas():
    prova = _rodar("documentos.py")

    texto = _textos(prova)
    metricas = {m.label: m.value for m in prova.metric}
    assert metricas["Cobertura documental"] == "2 de 4"
    assert "Ventoinha" in texto
    assert "Rotor excêntrico" in texto


def test_pagina_documentos_oferece_familias_como_lista_fechada():
    # Era text_input livre: digitar "Ventoinha" tomava 422 da allowlist do
    # servidor sem explicacao.
    prova = _rodar("documentos.py")

    assert prova.selectbox, "formulário deveria ter selectbox de família"
    campo = prova.selectbox[0]
    # options traz o texto exibido (apos format_func); o valor selecionado e o
    # slug que vai para a API. A tela fala portugues, o contrato fala slug.
    exibidas = campo.options
    assert "Correia" in exibidas
    assert "Ventoinha  —  sem documento" in exibidas
    assert not [texto for texto in exibidas if "_" in texto]
    assert campo.value in {item["familia"] for item in FAMILIAS}


def test_pagina_documentos_nao_oferece_estado_de_operacao_para_cadastro():
    # "normal" nao tem acao corretiva: nao existe procedimento a cadastrar.
    prova = _rodar("documentos.py")

    assert "Normal" not in prova.selectbox[0].options
