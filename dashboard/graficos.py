"""Figuras Plotly, em portugues e com cor atribuida por funcao.

Modulo sem Streamlit: recebe o JSON da API, devolve `go.Figure`. E o que
permite testar eixo, legenda, ordem e cor sem subir a interface.

O que estava errado na versao anterior (dashboard/app.py):

  px.bar(falhas["family"].value_counts())

Passar uma Series faz o Plotly nomear o eixo de valores como "count" e criar
uma legenda espuria "variable=count" — dois textos em ingles que nao vinham dos
dados, e sim do default da biblioteca. O eixo de categorias saia como "family",
e os valores das categorias eram os slugs crus (cocked_rotor, eccentric_rotor,
rolamento_inner...). No grafico de linha, `color="family"` punha "family" como
titulo de legenda.

Cor: a paleta e a instancia de referencia da skill de dataviz, coluna escura,
que passa os seis checks nas DUAS superficies do Streamlit (#ffffff e #0e1117)
— faixa de luminosidade, piso de croma, separacao para daltonismo (pior par
adjacente ΔE 8.4 protan), piso de visao normal (ΔE 19.3) e contraste >= 3:1.
A coluna clara nao serve: seu violeta cai para 2.21 de contraste no tema
escuro, e o Streamlit 1.40.2 nao informa ao Python qual tema o navegador esta
usando, entao uma unica paleta precisa servir aos dois.
"""

import plotly.graph_objects as go

# Ordem fixa dos slots categoricos. A ordem E o mecanismo de seguranca para
# daltonismo (pares adjacentes validados), nao escolha estetica — nao reordenar
# sem revalidar.
PALETA = [
    "#3987e5",  # azul
    "#d95926",  # laranja
    "#199e70",  # aqua
    "#c98500",  # amarelo
    "#d55181",  # magenta
    "#008300",  # verde
    "#9085e9",  # violeta
    "#e66767",  # vermelho
]

# Hue unico para magnitude de uma so medida (contagem de ocorrencias). Usar as
# oito cores num grafico de uma serie codificaria identidade onde nao existe
# identidade — cada barra e a mesma grandeza, so muda o valor.
COR_MAGNITUDE = PALETA[0]

# Enfase versus recessivo, para o grafico de votos: a distincao ali e
# "vencedora / demais", nao identidade de familia. Cinza da propria paleta,
# invariante de tema, com 3.6:1 no claro e 5.3:1 no escuro.
COR_RECESSIVA = "#898781"

# Maximo de series simultaneas na serie temporal. A paleta valida oito slots; a
# nona serie nunca e uma cor gerada (regra da skill). Com 12 familias de falha,
# o excedente e resolvido por codificacao composta — ver estilo_de_familia.
MAX_SERIES = len(PALETA)

# Separador pt-BR para todo numero renderizado pelo Plotly (eixo, hover,
# rotulo direto): decimal "," e milhar ".".
_SEPARADORES = ",."


def ordem_canonica(por_familia: list[dict]) -> list[str]:
    """Ordem de referencia das familias: volume total, decrescente.

    E propriedade do corpus inteiro, nao da selecao da tela. Por isso serve
    como chave de cor estavel: filtrar familias no multiselect nao repinta as
    que sobraram.
    """
    return [
        item["familia"]
        for item in sorted(por_familia,
                           key=lambda item: (-item["ocorrencias"], item["familia"]))
    ]


def estilo_de_familia(familia: str, ordem: list[str]) -> tuple[str, str | None]:
    """Cor e tracejado de uma familia, em funcao apenas dela mesma.

    A regra "cor segue a entidade, nunca sua posicao" exige que a cor dependa
    somente da familia e da ordem canonica — ambas estaveis. Como ha 12
    familias de falha e 8 slots validados, as que passam do oitavo lugar reusam
    um hue com tracejado: identidade fica em cor + traco, nao em cor sozinha, e
    duas familias nunca ficam indistinguiveis.
    """
    try:
        posicao = ordem.index(familia)
    except ValueError:
        # Familia fora do resumo (corpus sem ocorrencias dela): cor recessiva,
        # tracejada, em vez de KeyError no meio da renderizacao.
        return COR_RECESSIVA, "dot"
    return PALETA[posicao % len(PALETA)], None if posicao < len(PALETA) else "dash"


def _base(figura: go.Figure, altura: int) -> go.Figure:
    """Chrome comum. O tema (superficie, grade, tipografia) fica com o
    Streamlit: `st.plotly_chart(..., theme="streamlit")` adapta a claro/escuro,
    o que fixar cor de grade aqui impediria."""
    figura.update_layout(
        height=altura,
        separators=_SEPARADORES,
        margin=dict(l=8, r=8, t=8, b=8),
        hoverlabel=dict(font_size=13),
    )
    return figura


def ocorrencias_por_familia(por_familia: list[dict], rotular) -> go.Figure:
    """Barra horizontal: quantas leituras de cada familia de falha.

    Horizontal por causa do rotulo: "Rolamento — pista interna" e
    "Rotor desalinhado no eixo" nao cabem num eixo X com 12 categorias sem
    girar o texto ou truncar. No eixo Y cada um ocupa uma linha inteira.

    Uma serie so, entao sem legenda — o titulo do grafico ja nomeia a medida —
    e com rotulo direto em cada barra, que dispensa ler o eixo para saber o
    valor.
    """
    dados = sorted(por_familia, key=lambda item: item["ocorrencias"])
    figura = go.Figure(go.Bar(
        x=[item["ocorrencias"] for item in dados],
        y=[rotular(item["familia"]) for item in dados],
        orientation="h",
        marker_color=COR_MAGNITUDE,
        # Cantos arredondados apenas na ponta do dado, ancorada na linha de base.
        marker_cornerradius=4,
        text=[f"{item['ocorrencias']:,}".replace(",", ".") for item in dados],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,.0f} ocorrências<extra></extra>",
    ))
    figura.update_xaxes(title_text="Ocorrências", showgrid=True, zeroline=False)
    figura.update_yaxes(title_text=None)
    # Espaco a direita para o rotulo direto nao ser cortado na barra maior.
    figura.update_layout(xaxis_range=[0, max(
        (item["ocorrencias"] for item in dados), default=1) * 1.18])
    return _base(figura, altura=max(280, 34 * len(dados) + 60))


def falhas_ao_longo_do_tempo(por_dia: list[dict], familias_visiveis: list[str],
                             ordem: list[str], rotular) -> go.Figure:
    """Linha: ocorrencias por dia, uma serie por familia selecionada.

    Legenda sempre presente (mais de uma serie) e identidade tambem no traco,
    para as familias que reusam hue. Hover unificado no eixo X: com varias
    series, comparar o mesmo dia exige ver todas as series de uma vez, nao uma
    por vez.
    """
    figura = go.Figure()
    for familia in familias_visiveis:
        pontos = sorted(
            (item for item in por_dia if item["familia"] == familia),
            key=lambda item: item["dia"],
        )
        if not pontos:
            continue
        cor, tracejado = estilo_de_familia(familia, ordem)
        figura.add_trace(go.Scatter(
            x=[item["dia"] for item in pontos],
            y=[item["ocorrencias"] for item in pontos],
            name=rotular(familia),
            mode="lines",
            line=dict(color=cor, width=2, dash=tracejado),
            hovertemplate="%{y:,.0f}<extra>%{fullData.name}</extra>",
        ))
    figura.update_xaxes(title_text="Data", tickformat="%d/%m", showgrid=False)
    figura.update_yaxes(title_text="Ocorrências", showgrid=True, zeroline=False,
                        rangemode="tozero")
    figura.update_layout(
        hovermode="x unified",
        legend=dict(title_text="Família de falha", orientation="h",
                    yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return _base(figura, altura=380)


def votos_do_knn(votos_ordenados: list[tuple[str, int]], vencedoras: set[str],
                 total: int, rotular) -> go.Figure:
    """Barra horizontal: quantos dos N vizinhos votaram em cada familia.

    O grafico mais importante da tela. A API classifica pela familia mais
    votada e devolve `status: "diagnostico"` sem qualificar o quanto ela venceu
    — numa avaliacao local do modo offline, tres repeticoes do mesmo payload de
    correia elegeram a familia com 9 de 50 votos, empatada com duas outras. A
    versao anterior da tela resumia isso a um caption com o top-3 e a frase
    "voto de 50 vizinhos mais proximos", que se le como conclusao firme.

    A distincao aqui e enfase (vencedora/empatadas versus demais), nao
    identidade de familia: duas cores, nao oito. E a cor nao carrega o sentido
    sozinha — o rotulo direto traz voto e percentual, e a pagina exibe o texto
    de inconclusividade acima do grafico.
    """
    dados = list(reversed(votos_ordenados))
    figura = go.Figure(go.Bar(
        x=[votos for _, votos in dados],
        y=[rotular(familia) for familia, _ in dados],
        orientation="h",
        marker_color=[
            COR_MAGNITUDE if familia in vencedoras else COR_RECESSIVA
            for familia, _ in dados
        ],
        marker_cornerradius=4,
        text=[
            f"{votos} de {total}"
            + (f" ({100 * votos / total:.0f}%)".replace(".", ",") if total else "")
            for _, votos in dados
        ],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:,.0f} votos<extra></extra>",
    ))
    figura.update_xaxes(title_text=f"Votos entre os {total} vizinhos mais próximos",
                        showgrid=True, zeroline=False,
                        range=[0, max((v for _, v in dados), default=1) * 1.35])
    figura.update_yaxes(title_text=None)
    return _base(figura, altura=max(240, 32 * len(dados) + 60))


def ocorrencias_por_dia(por_dia: dict[str, int]) -> go.Figure:
    """Sparkline da janela historica da familia diagnosticada.

    Sem eixo, sem grade, sem legenda: e um complemento da metrica ao lado, para
    mostrar se as ocorrencias se concentram num periodo ou se distribuem — nao
    um grafico para leitura de valores, que ficam no hover.
    """
    dias = sorted(por_dia)
    figura = go.Figure(go.Scatter(
        x=dias,
        y=[por_dia[dia] for dia in dias],
        mode="lines",
        line=dict(color=COR_MAGNITUDE, width=2),
        fill="tozeroy",
        fillcolor="rgba(57, 135, 229, 0.15)",
        hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.0f} ocorrências<extra></extra>",
    ))
    figura.update_xaxes(visible=False)
    figura.update_yaxes(visible=False, rangemode="tozero")
    figura.update_layout(showlegend=False)
    return _base(figura, altura=110)
