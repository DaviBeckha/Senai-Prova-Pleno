"""Quanta confianca o voto kNN realmente sustenta.

O backend ja se contem quando duas ou mais familias empatam no maior numero de
votos. Este modulo apresenta a distribuicao de modo auditavel. Nao aplica um
limiar arbitrario a vitorias unicas: o suporte continua visivel, mas somente um
empate exato transforma o resultado em inconclusivo.

Modulo sem dependencia de Streamlit ou Plotly, de proposito: a regra e o que
mais importa acertar, e assim ela e testavel como funcao pura.
"""

from dataclasses import dataclass, field

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
    def inconclusiva(self) -> bool:
        return self.houve_empate

    def motivo(self, rotular=str) -> str:
        """Frase que explica por que o resultado nao e conclusivo.

        `rotular` traduz slug para rotulo em portugues (normalmente
        Familias.rotulo); o default mantem o modulo utilizavel sem vocabulario
        carregado.
        """
        if not self.inconclusiva:
            return ""
        if self.houve_empate:
            nomes = ", ".join(
                rotular(familia)
                for familia in (self.vencedora, *self.empatadas)
            )
            return (
                f"Classificação inconclusiva: {len(self.empatadas) + 1} famílias "
                f"empataram com {self.votos} de {self.total} votos "
                f"({nomes}). Nenhuma família foi escolhida; confirme os sintomas "
                "e colete novas medições."
            )
        return ""


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
