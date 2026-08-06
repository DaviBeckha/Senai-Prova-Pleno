"""Camadas puras do dashboard: formatacao, vocabulario, confianca e graficos.

O que da para testar sem subir o Streamlit e justamente o que mais importa
acertar: a regra que decide se um diagnostico e conclusivo, a ordem e a cor das
series, e os rotulos de eixo e legenda que antes saiam em ingles.

Os modulos aqui nao importam nada de dashboard/ nem de app/ — e o que permite
carrega-los como `dashboard.x` daqui e como `x` sob `streamlit run`.
"""

import pytest

from dashboard import confianca, formato, graficos, vocabulario

# Distribuicao real de uma avaliacao local do modo offline: o payload de correia
# elegeu a familia com 9 de 50 votos, EMPATADA com rolamento_outer e
# rolamento_ball. A tela anunciava isso como diagnostico conclusivo.
VOTOS_EMPATE = {
    "correia": 9, "rolamento_outer": 9, "rolamento_ball": 9,
    "rolamento_inner": 7, "rolamento_combination": 7, "cocked_rotor": 5,
    "normal": 2, "eccentric_rotor": 2,
}
# Mesma avaliacao, estado normal: 28 de 50, sem empate — julgado correto.
VOTOS_CONCLUSIVO = {
    "normal": 28, "motor_desligado": 16, "rolamento_combination": 2,
    "baseline": 2, "rolamento_ball": 1, "cocked_rotor": 1,
}
# Mesma avaliacao, ventoinha: venceu sozinha com 13 de 50 — sem empate, porem
# suporte baixo; a revisao manual registrou "confianca do kNN ainda e baixa".
VOTOS_SUPORTE_BAIXO = {
    "ventoinha": 13, "rolamento_combination": 10, "polia": 7, "cocked_rotor": 6,
    "rolamento_ball": 5, "rolamento_outer": 4, "eccentric_rotor": 2, "normal": 2,
    "rolamento_inner": 1,
}


# --- formato ---------------------------------------------------------------

def test_inteiro_usa_ponto_como_separador_de_milhar():
    assert formato.inteiro(166796) == "166.796"
    assert formato.inteiro(11999) == "11.999"
    assert formato.inteiro(0) == "0"


def test_decimal_usa_virgula_decimal_e_ponto_de_milhar():
    # 1499.88 e uma frequencia_por_dia real do historico: sem formatacao, o
    # numero e lido errado por quem espera padrao brasileiro.
    assert formato.decimal(1499.88) == "1.499,88"
    assert formato.decimal(320.38) == "320,38"
    assert formato.decimal(1.5) == "1,50"


def test_porcentagem_protege_divisao_por_zero():
    assert formato.porcentagem(9, 50) == "18%"
    assert formato.porcentagem(0, 0) == "—"


def test_data_converte_iso_para_padrao_brasileiro():
    assert formato.data("2026-06-01") == "01/06/2026"
    assert formato.data("2026-06-01T10:00:00+00:00") == "01/06/2026"
    assert formato.data_curta("2026-06-01") == "01/06"


def test_data_invalida_nao_estoura():
    # Um campo inesperado da API nao deve derrubar a renderizacao da pagina.
    assert formato.data("nao e data") == "nao e data"
    assert formato.data("") == "—"


def test_dias_no_periodo_conta_as_duas_pontas():
    # E o denominador de frequencia_por_dia (ver occurrence_stats).
    assert formato.dias_no_periodo("2026-06-01", "2026-06-08") == 8
    assert formato.dias_no_periodo("2026-06-01", "2026-06-01") == 1
    assert formato.dias_no_periodo("", "") is None


# --- vocabulario -----------------------------------------------------------

def _familias() -> vocabulario.Familias:
    return vocabulario.Familias([
        {"familia": "correia", "rotulo": "Correia", "tipo": "falha",
         "documentado": True},
        {"familia": "eccentric_rotor", "rotulo": "Rotor excêntrico",
         "tipo": "falha", "documentado": False},
        {"familia": "ventoinha", "rotulo": "Ventoinha", "tipo": "falha",
         "documentado": False},
        {"familia": "normal", "rotulo": "Normal", "tipo": "estado",
         "documentado": False},
    ])


def test_familias_rotula_pelo_vocabulario_da_api():
    assert _familias().rotulo("eccentric_rotor") == "Rotor excêntrico"


def test_familias_familia_desconhecida_rotula_com_o_proprio_slug():
    # Melhor um rotulo imperfeito que KeyError no meio da renderizacao.
    assert _familias().rotulo("familia_nova") == "familia_nova"
    assert _familias().documentado("familia_nova") is False


def test_familias_cobertura_conta_apenas_familias_de_falha():
    # Estado de operacao nao tem procedimento corretivo, entao nao entra no
    # denominador da cobertura.
    assert _familias().cobertura() == (1, 3)


def test_familias_sem_documento_lista_as_que_vao_se_conter():
    rotulos = [item["rotulo"] for item in _familias().sem_documento()]
    assert rotulos == ["Rotor excêntrico", "Ventoinha"]
    assert "Normal" not in rotulos


def test_status_do_chat_tem_titulo_e_explicacao_para_todo_desfecho():
    # Os dez status que o contrato HTTP pode devolver (ver _STATUS_CHAT_PT em
    # app/api/schemas.py). Um desfecho sem entrada apareceria na tela como
    # identificador cru, que foi exatamente o problema da versao anterior.
    from app.api.schemas import _STATUS_CHAT_PT

    for status in _STATUS_CHAT_PT.values():
        assert vocabulario.titulo_chat(status) != status
        assert vocabulario.explicacao_chat(status)


def test_status_do_diagnostico_tem_titulo_e_explicacao():
    for status in ("diagnostico", "sem_documento", "estado"):
        assert vocabulario.titulo_diagnostico(status) != status
        assert vocabulario.explicacao_diagnostico(status)


def test_nome_do_redator_distingue_modelo_de_extracao_deterministica():
    assert "Ollama" in vocabulario.nome_redator("ollama")
    assert "determinística" in vocabulario.nome_redator("template")
    assert "sem modelo" in vocabulario.nome_redator(None)


# --- confianca -------------------------------------------------------------

def test_empate_no_topo_torna_a_classificacao_inconclusiva():
    certeza = confianca.avaliar(VOTOS_EMPATE, 50)

    assert certeza.votos == 9
    assert certeza.total == 50
    assert set(certeza.empatadas) == {"rolamento_ball", "rolamento_outer"}
    assert certeza.houve_empate
    assert certeza.inconclusiva


def test_suporte_baixo_sem_empate_nao_aplica_limiar_arbitrario():
    certeza = confianca.avaliar(VOTOS_SUPORTE_BAIXO, 50)

    assert certeza.vencedora == "ventoinha"
    assert not certeza.houve_empate
    assert certeza.suporte == pytest.approx(0.26)
    assert not certeza.inconclusiva
    assert certeza.motivo() == ""


def test_maioria_folgada_e_conclusiva():
    certeza = confianca.avaliar(VOTOS_CONCLUSIVO, 50)

    assert certeza.vencedora == "normal"
    assert certeza.suporte == pytest.approx(0.56)
    assert not certeza.inconclusiva
    assert certeza.motivo() == ""


def test_motivo_do_empate_nomeia_as_familias_e_pede_cautela():
    certeza = confianca.avaliar(VOTOS_EMPATE, 50)
    texto = certeza.motivo(lambda slug: slug.replace("_", " "))

    assert "3 famílias" in texto
    assert "9 de 50" in texto
    assert "hipótese" in texto
    assert "rolamento ball" in texto


def test_suporte_usa_vizinhos_consultados_como_denominador():
    # k=50 e clampado ao tamanho do historico: um corpus pequeno consulta menos
    # vizinhos, e o suporte tem de refletir isso.
    certeza = confianca.avaliar({"correia": 3, "polia": 1}, 4)

    assert certeza.total == 4
    assert certeza.suporte == pytest.approx(0.75)
    assert not certeza.inconclusiva


def test_sem_votos_devolve_none_em_vez_de_estourar():
    assert confianca.avaliar({}, 0) is None


def test_ordenar_votos_desempata_por_nome_para_ordem_estavel():
    # Sem desempate estavel, duas renderizacoes da mesma resposta poderiam
    # trocar barras empatadas de lugar no grafico.
    assert confianca.ordenar_votos(VOTOS_EMPATE)[:3] == [
        ("correia", 9), ("rolamento_ball", 9), ("rolamento_outer", 9),
    ]


# --- graficos --------------------------------------------------------------

POR_FAMILIA = [
    {"familia": "rolamento_inner", "tipo": "falha", "ocorrencias": 24310},
    {"familia": "ventoinha", "tipo": "falha", "ocorrencias": 12299},
    {"familia": "correia", "tipo": "falha", "ocorrencias": 11999},
    {"familia": "eccentric_rotor", "tipo": "falha", "ocorrencias": 900},
]
POR_DIA = [
    {"dia": "2026-06-01", "familia": "correia", "ocorrencias": 118},
    {"dia": "2026-06-02", "familia": "correia", "ocorrencias": 96},
    {"dia": "2026-06-01", "familia": "ventoinha", "ocorrencias": 40},
]
ROTULO = {
    "rolamento_inner": "Rolamento — pista interna",
    "ventoinha": "Ventoinha",
    "correia": "Correia",
    "eccentric_rotor": "Rotor excêntrico",
}


def _rotular(slug: str) -> str:
    return ROTULO.get(slug, slug)


def test_ordem_canonica_e_por_volume_decrescente():
    assert graficos.ordem_canonica(POR_FAMILIA) == [
        "rolamento_inner", "ventoinha", "correia", "eccentric_rotor",
    ]


def test_cor_da_familia_depende_so_da_familia_nao_da_selecao():
    # A regra "cor segue a entidade, nunca sua posicao": filtrar familias no
    # multiselect nao pode repintar as que permanecem.
    ordem = graficos.ordem_canonica(POR_FAMILIA)

    antes = graficos.estilo_de_familia("correia", ordem)
    depois = graficos.estilo_de_familia("correia", ordem)

    assert antes == depois
    assert antes[0] == graficos.PALETA[2]


def test_familia_alem_do_oitavo_slot_reusa_hue_com_tracejado():
    # A paleta valida oito slots e a nona serie nunca e uma cor gerada. Com 12
    # familias de falha, o excedente ganha identidade em cor + traco.
    ordem = [f"familia_{i}" for i in range(12)]

    cor_1, traco_1 = graficos.estilo_de_familia("familia_0", ordem)
    cor_9, traco_9 = graficos.estilo_de_familia("familia_8", ordem)

    assert cor_1 == cor_9
    assert traco_1 is None
    assert traco_9 == "dash"


def test_familia_fora_da_ordem_nao_estoura():
    cor, traco = graficos.estilo_de_familia("desconhecida", ["correia"])

    assert cor == graficos.COR_RECESSIVA
    assert traco == "dot"


def test_grafico_de_ocorrencias_rotula_eixo_em_portugues():
    # O bug original: px.bar(Series) nomeava o eixo de valores como "count" e
    # criava uma legenda espuria "variable=count".
    figura = graficos.ocorrencias_por_familia(POR_FAMILIA, _rotular)

    assert figura.layout.xaxis.title.text == "Ocorrências"
    assert figura.layout.yaxis.title.text is None
    assert "count" not in str(figura.layout.to_plotly_json())


def test_grafico_de_ocorrencias_usa_rotulo_em_portugues_nas_categorias():
    figura = graficos.ocorrencias_por_familia(POR_FAMILIA, _rotular)

    categorias = list(figura.data[0].y)
    assert "Rolamento — pista interna" in categorias
    assert "Rotor excêntrico" in categorias
    assert not [c for c in categorias if "_" in c]


def test_grafico_de_ocorrencias_ordena_crescente_para_barra_horizontal():
    # Barra horizontal cresce de baixo para cima: a maior tem de ficar no topo.
    figura = graficos.ocorrencias_por_familia(POR_FAMILIA, _rotular)

    assert list(figura.data[0].x) == [900, 11999, 12299, 24310]


def test_grafico_de_ocorrencias_usa_hue_unico_e_nao_tem_legenda():
    # Uma serie so: colorir as barras por familia codificaria identidade onde
    # existe apenas magnitude da mesma medida.
    figura = graficos.ocorrencias_por_familia(POR_FAMILIA, _rotular)

    assert len(figura.data) == 1
    assert figura.data[0].marker.color == graficos.COR_MAGNITUDE


def test_serie_temporal_nomeia_legenda_e_eixos_em_portugues():
    # O bug original: color="family" punha "family" como titulo de legenda e o
    # eixo de valores saia como "n".
    figura = graficos.falhas_ao_longo_do_tempo(
        POR_DIA, ["correia", "ventoinha"],
        graficos.ordem_canonica(POR_FAMILIA), _rotular)

    assert figura.layout.legend.title.text == "Família de falha"
    assert figura.layout.xaxis.title.text == "Data"
    assert figura.layout.yaxis.title.text == "Ocorrências"
    assert [t.name for t in figura.data] == ["Correia", "Ventoinha"]


def test_serie_temporal_ignora_familia_sem_ponto_no_periodo():
    figura = graficos.falhas_ao_longo_do_tempo(
        POR_DIA, ["correia", "eccentric_rotor"],
        graficos.ordem_canonica(POR_FAMILIA), _rotular)

    assert [t.name for t in figura.data] == ["Correia"]


def test_grafico_de_votos_destaca_vencedora_e_recessiva_as_demais():
    ordenados = confianca.ordenar_votos({"correia": 9, "polia": 2})
    figura = graficos.votos_do_knn(ordenados, {"correia"}, 50, _rotular)

    # A ordem vem invertida: barra horizontal cresce de baixo para cima, entao
    # a vencedora e o ULTIMO elemento para aparecer no topo do grafico.
    assert list(figura.data[0].marker.color) == [
        graficos.COR_RECESSIVA, graficos.COR_MAGNITUDE,
    ]


def test_grafico_de_votos_mostra_voto_e_percentual_em_rotulo_direto():
    # A cor nao pode carregar o sentido sozinha: o valor fica escrito na barra.
    ordenados = confianca.ordenar_votos({"correia": 9, "polia": 2})
    figura = graficos.votos_do_knn(ordenados, {"correia"}, 50, _rotular)

    assert "9 de 50 (18%)" in list(figura.data[0].text)


def test_grafico_de_votos_marca_todas_as_empatadas_como_vencedoras():
    ordenados = confianca.ordenar_votos(VOTOS_EMPATE)
    certeza = confianca.avaliar(VOTOS_EMPATE, 50)
    vencedoras = {certeza.vencedora, *certeza.empatadas}

    figura = graficos.votos_do_knn(ordenados, vencedoras, 50, _rotular)

    destacadas = sum(1 for cor in figura.data[0].marker.color
                     if cor == graficos.COR_MAGNITUDE)
    assert destacadas == 3


def test_sparkline_nao_mostra_eixo_nem_legenda():
    figura = graficos.ocorrencias_por_dia({"2026-06-01": 2, "2026-06-02": 1})

    assert figura.layout.xaxis.visible is False
    assert figura.layout.yaxis.visible is False
    assert figura.layout.showlegend is False


def test_todos_os_graficos_usam_separador_decimal_brasileiro():
    figuras = [
        graficos.ocorrencias_por_familia(POR_FAMILIA, _rotular),
        graficos.falhas_ao_longo_do_tempo(
            POR_DIA, ["correia"], graficos.ordem_canonica(POR_FAMILIA), _rotular),
        graficos.votos_do_knn([("correia", 9)], {"correia"}, 50, _rotular),
        graficos.ocorrencias_por_dia({"2026-06-01": 2}),
    ]

    for figura in figuras:
        assert figura.layout.separators == ",."


def test_paleta_tem_oito_slots_e_o_maximo_de_series_acompanha():
    # Se alguem acrescentar um hue sem revalidar, MAX_SERIES nao pode ficar
    # dessincronizado do tamanho real da paleta.
    assert len(graficos.PALETA) == 8
    assert graficos.MAX_SERIES == len(graficos.PALETA)
