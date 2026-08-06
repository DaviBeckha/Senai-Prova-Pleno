"""Quanta confianca o voto kNN realmente sustenta.

A API devolve `status: "diagnostico"` sempre que a familia vencedora tem
documento e trechos — independentemente de ela ter vencido com 56% ou com 18%
dos votos, e independentemente de ter havido empate no topo. Uma avaliacao local
do modo offline mostrou o caso extremo: tres repeticoes do mesmo payload de
correia elegeram a familia com **9 de 50 votos, empatada com rolamento_outer e
rolamento_ball**, e a tela anunciava "Status: diagnostico | Familia: correia —
voto de 50 vizinhos mais proximos", que se le como conclusao firme.

Criar um status "inconclusivo" no backend e a correcao de fundo, e esta nao e a
camada para isso: mudaria o contrato e o comportamento do guardrail. O que a
interface pode e deve fazer agora e nao afirmar mais confianca do que os votos
sustentam.

Modulo sem dependencia de Streamlit ou Plotly, de proposito: a regra e o que
mais importa acertar, e assim ela e testavel como funcao pura.
"""

from dataclasses import dataclass, field

# Abaixo deste suporte, a familia vencedora e tratada como hipotese.
#
# O limiar vem da propria avaliacao local: os desfechos julgados corretos na
# revisao manual tinham 56% de suporte (estado normal, 28/50), enquanto os
# julgados de baixa confianca tinham 18% (correia, 9/50, com empate triplo) e
# 26% (ventoinha, 13/50). 40% fica entre os dois grupos sem separar nenhum caso
# ao meio.
SUPORTE_MINIMO = 0.40


@dataclass(frozen=True)
class Confianca:
    vencedora: str
    votos: int
    total: int
    empatadas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def suporte(self) -> float:
        """Fracao dos vizinhos consultados que votou na vencedora."""
        return self.votos / self.total if self.total else 0.0

    @property
    def houve_empate(self) -> bool:
        return bool(self.empatadas)

    @property
    def suporte_baixo(self) -> bool:
        return self.suporte < SUPORTE_MINIMO

    @property
    def inconclusiva(self) -> bool:
        return self.houve_empate or self.suporte_baixo

    def motivo(self, rotular=str) -> str:
        """Frase que explica por que o resultado nao e conclusivo.

        `rotular` traduz slug para rotulo em portugues (normalmente
        Familias.rotulo); o default mantem o modulo utilizavel sem vocabulario
        carregado.
        """
        if not self.inconclusiva:
            return ""
        if self.houve_empate:
            nomes = ", ".join(rotular(familia) for familia in self.empatadas)
            return (
                f"Classificação inconclusiva: {len(self.empatadas) + 1} famílias "
                f"empataram com {self.votos} de {self.total} votos "
                f"({rotular(self.vencedora)}, {nomes}). O desempate foi pela ordem "
                "do histórico, não por evidência. Trate como hipótese."
            )
        return (
            f"Confiança baixa: a família vencedora reuniu apenas {self.votos} de "
            f"{self.total} votos. As demais somam a maioria — trate como hipótese "
            "e confirme pelo rótulo real ou por inspeção."
        )


def avaliar(votos_por_familia: dict[str, int], vizinhos_consultados: int) -> Confianca | None:
    """Le a distribuicao de votos do diagnostico.

    Devolve None quando nao ha votos — os desfechos "estado" e "sem_documento"
    tambem trazem a distribuicao, mas um relatorio vindo de um pipeline falso ou
    de uma versao antiga da API pode nao trazer, e a tela nao deve quebrar por
    isso.

    O total usado e `vizinhos_consultados` (k=50 clampado ao tamanho do
    historico), NAO a soma dos votos: sao a mesma grandeza no pipeline real,
    mas usar o campo explicito evita que um arredondamento futuro na
    distribuicao mude silenciosamente o denominador do suporte.
    """
    if not votos_por_familia:
        return None
    maximo = max(votos_por_familia.values())
    no_topo = sorted(
        familia for familia, votos in votos_por_familia.items() if votos == maximo
    )
    total = vizinhos_consultados or sum(votos_por_familia.values())
    return Confianca(
        vencedora=no_topo[0],
        votos=maximo,
        total=total,
        empatadas=tuple(no_topo[1:]),
    )


def ordenar_votos(votos_por_familia: dict[str, int]) -> list[tuple[str, int]]:
    """Votos do maior para o menor, com desempate alfabetico estavel.

    Ordem estavel importa no grafico: sem o desempate por nome, duas
    renderizacoes da mesma resposta poderiam trocar barras empatadas de lugar.
    """
    return sorted(votos_por_familia.items(), key=lambda item: (-item[1], item[0]))
