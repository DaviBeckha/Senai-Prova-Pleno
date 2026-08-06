"""Cliente HTTP da API. Unico ponto do dashboard que fala rede.

Antes, `httpx.post` aparecia em quatro pontos de dashboard/app.py, cada um com
seu proprio `except httpx.ConnectError` e a mesma string de erro repetida —
que ainda mandava "suba a API com uvicorn", instrucao errada quando o stack
sobe por docker compose.

O dashboard tambem nao importa nada de app/ nem le arquivo do disco: todo dado
vem daqui. Isso e o que permite a imagem do dashboard nao carregar app/,
scripts/ nem banner.xlsx.
"""

import os

import httpx


class ErroDeApi(Exception):
    """Base para tudo que impede uma resposta util da API."""


class ApiIndisponivel(ErroDeApi):
    def __init__(self) -> None:
        super().__init__(
            "Não foi possível falar com a API. Verifique se ela está no ar em "
            f"{API_URL} e tente de novo."
        )


class ApiNaoPronta(ErroDeApi):
    """A API respondeu, mas o bootstrap ainda nao terminou (503)."""

    def __init__(self) -> None:
        super().__init__(
            "A API está no ar, porém ainda inicializando (carga do histórico, "
            "motor de similaridade e modelo de embeddings). Aguarde e recarregue."
        )


class ApiExpirou(ErroDeApi):
    def __init__(self, segundos: float) -> None:
        super().__init__(
            f"A API não respondeu em {segundos:.0f}s. No modo offline a geração "
            "roda em CPU e pode passar de 4 minutos em perguntas de "
            "procedimento completo — repita ou tente uma pergunta mais específica."
        )


class ApiRecusou(ErroDeApi):
    """4xx/5xx com mensagem propria da API (campo `detail` do FastAPI)."""

    def __init__(self, status: int, detalhe: str) -> None:
        self.status = status
        self.detalhe = detalhe
        super().__init__(detalhe or f"A API respondeu com erro {status}.")


API_URL = os.environ.get("API_URL", "http://localhost:8000")


def _resolver_timeout() -> float:
    """Le DASHBOARD_TIMEOUT do ambiente com fallback defensivo.

    330s = OLLAMA_TIMEOUT maximo (300s) + folga de rede, para o dashboard
    nunca desistir antes da API/Ollama. Uma env vazia ou nao-numerica nao
    pode derrubar o import do modulo — cai no mesmo default 330.
    """
    try:
        return float(os.environ.get("DASHBOARD_TIMEOUT", "330"))
    except ValueError:
        return 330.0


TIMEOUT = _resolver_timeout()


def _detalhe(resposta: httpx.Response) -> str:
    """Extrai o `detail` do FastAPI, sem confiar que o corpo seja JSON.

    Um 500 do servidor de aplicacao pode vir como HTML; nesse caso a mensagem
    generica do status e melhor que uma excecao de parse dentro do handler de
    erro.
    """
    try:
        corpo = resposta.json()
    except ValueError:
        return ""
    if isinstance(corpo, dict):
        detalhe = corpo.get("detail")
        if isinstance(detalhe, str):
            return detalhe
        if detalhe is not None:
            # 422 da validacao do Pydantic: detail e uma lista de erros.
            return "; ".join(
                str(item.get("msg", item)) if isinstance(item, dict) else str(item)
                for item in detalhe
            )
    return ""


def _requisitar(metodo: str, caminho: str, *, timeout: float | None = None,
                **kwargs):
    limite = TIMEOUT if timeout is None else timeout
    try:
        resposta = httpx.request(metodo, f"{API_URL}{caminho}",
                                 timeout=limite, **kwargs)
    except httpx.TimeoutException as exc:
        raise ApiExpirou(limite) from exc
    except httpx.TransportError as exc:
        # TransportError cobre ConnectError, ReadError, resolucao de DNS e
        # conexao derrubada no meio — do ponto de vista de quem olha a tela,
        # sao todos "a API nao esta acessivel".
        raise ApiIndisponivel() from exc
    if resposta.status_code == 503:
        raise ApiNaoPronta()
    if resposta.status_code >= 400:
        raise ApiRecusou(resposta.status_code, _detalhe(resposta))
    return resposta.json()


# --- Leitura ---------------------------------------------------------------

def saude() -> dict:
    """GET /health. Timeout curto: e um indicador, nao uma operacao.

    Sem o limite proprio, uma API pendurada deixaria a sidebar de todas as
    paginas travada pelos 330s do timeout de geracao.
    """
    return _requisitar("GET", "/health", timeout=5.0)


def familias() -> list[dict]:
    """GET /familias — vocabulario: slug, rotulo em portugues, tipo, cobertura."""
    return _requisitar("GET", "/familias", timeout=15.0)


def documentos() -> list[dict]:
    return _requisitar("GET", "/documentos", timeout=15.0)


def historico_resumo() -> dict:
    """GET /historico/resumo — agregados do mesmo corpus que alimenta o kNN."""
    return _requisitar("GET", "/historico/resumo", timeout=30.0)


def amostra(familia: str) -> dict:
    """GET /eventos/amostra — sorteia uma leitura real da familia."""
    return _requisitar("GET", "/eventos/amostra", timeout=30.0,
                       params={"familia": familia})


# --- Escrita ---------------------------------------------------------------

def diagnosticar(features: dict, modo: str) -> dict:
    return _requisitar("POST", "/eventos", json={**features, "modo": modo})


def perguntar(pergunta: str, modo: str) -> dict:
    return _requisitar("POST", "/chat", json={"pergunta": pergunta, "modo": modo})


def registrar_documento(familia: str, titulo: str, nome_arquivo: str,
                        conteudo: bytes, tipo_mime: str) -> dict:
    return _requisitar(
        "POST", "/documentos",
        files={"file": (nome_arquivo, conteudo, tipo_mime)},
        data={"familia": familia, "titulo": titulo},
    )
