"""Formatacao pt-BR de numeros e datas.

O historico tem ordens de grandeza que tornam a formatacao necessaria, nao
cosmetica: "11999 ocorrencias" e "1499.88/dia" sao dificeis de ler de relance;
"11.999" e "1.499,88" nao. Python nao formata no padrao brasileiro nativamente
(`locale` depende de o locale existir no sistema operacional, e a imagem
python:3.12-slim nao traz pt_BR), entao a conversao e feita a mao.
"""

from datetime import date, datetime


def inteiro(valor: int | float) -> str:
    """1234567 -> "1.234.567"."""
    return f"{int(valor):,}".replace(",", ".")


def decimal(valor: float, casas: int = 2) -> str:
    """1499.88 -> "1.499,88"."""
    texto = f"{valor:,.{casas}f}"
    # Troca em duas etapas com um marcador: substituir "," por "." primeiro
    # transformaria o separador decimal em milhar no passo seguinte.
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def porcentagem(parte: float, total: float, casas: int = 0) -> str:
    """Divisao protegida: total zero devolve "—", nao ZeroDivisionError."""
    if not total:
        return "—"
    return f"{decimal(100 * parte / total, casas)}%"


def _para_data(valor: str | date | datetime) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if not valor:
        return None
    try:
        # fromisoformat cobre "2026-06-01" e "2026-06-01T10:00:00+00:00".
        return datetime.fromisoformat(valor).date()
    except ValueError:
        return None


def data(valor: str | date | datetime) -> str:
    """ISO -> "01/06/2026". Valor invalido volta como recebido, sem estourar."""
    convertida = _para_data(valor)
    return convertida.strftime("%d/%m/%Y") if convertida else str(valor or "—")


def data_curta(valor: str | date | datetime) -> str:
    """ISO -> "01/06", para eixo de grafico onde o ano e redundante."""
    convertida = _para_data(valor)
    return convertida.strftime("%d/%m") if convertida else str(valor or "—")


def periodo(inicio, fim) -> str:
    """Janela legivel: "01/06/2026 a 08/06/2026"."""
    if not inicio and not fim:
        return "—"
    return f"{data(inicio)} a {data(fim)}"


def dias_no_periodo(inicio, fim) -> int | None:
    """Quantos dias a janela cobre, inclusive nas duas pontas.

    E o denominador de frequencia_por_dia (ver occurrence_stats): sem ele, a
    media diaria na tela nao tem como ser interpretada.
    """
    comeco, termino = _para_data(inicio), _para_data(fim)
    if comeco is None or termino is None:
        return None
    return max((termino - comeco).days + 1, 1)
