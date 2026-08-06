"""Traducao de identificadores para o texto que aparece na tela.

Os rotulos de familia vem de GET /familias — a API e a dona do vocabulario.
Repetir o mapa aqui recriaria a divergencia que este trabalho removeu: antes,
o dashboard reimplementava normalize_label sobre o proprio banner.xlsx.

Os status, ao contrario, sao traduzidos aqui: `sem_documento` e o identificador
do contrato, "Sem documento orientativo" e a frase que o operador le. A API nao
tem por que carregar prosa de interface.
"""

# Status do diagnostico (POST /eventos) -> titulo e explicacao na tela.
#
# O identificador cru ("sem_documento") aparecia direto no st.info da versao
# anterior. Dizer o que o desfecho significa importa mais que exibir o enum:
# "sem_documento" nao informa que o sistema se conteve de proposito.
DIAGNOSTICO = {
    "diagnostico": (
        "Diagnóstico emitido",
        "Falha reconhecida, com documento orientativo cadastrado e trechos "
        "recuperados do índice.",
    ),
    "sem_documento": (
        "Sem documento orientativo",
        "A falha foi reconhecida, mas não há procedimento cadastrado para ela "
        "— ou nenhum trecho utilizável foi recuperado. O sistema se conteve em "
        "vez de recomendar sem fonte.",
    ),
    "estado": (
        "Estado de operação",
        "O evento corresponde a uma condição normal de funcionamento, não a "
        "uma falha com ação corretiva.",
    ),
}

# Status do chat (POST /chat) -> titulo e explicacao.
CHAT = {
    "respondido": (
        "Respondido com fonte",
        "A resposta cita trechos recuperados de documento cadastrado.",
    ),
    "sem_documento": (
        "Sem documento cadastrado",
        "A falha foi reconhecida, mas não existe procedimento cadastrado para "
        "ela.",
    ),
    "evidencia_insuficiente": (
        "Evidência insuficiente",
        "Existe documento, porém nenhum trecho atingiu o limite mínimo de "
        "relevância. Nada foi gerado sem fonte.",
    ),
    "recusado_seguranca": (
        "Recusado por segurança",
        "O pedido envolvia intervenção com o equipamento em funcionamento.",
    ),
    "recusado_interno": (
        "Recusado",
        "O pedido tentava obter instruções internas do sistema.",
    ),
    "precisa_esclarecimento": (
        "Precisa de esclarecimento",
        "Os sintomas descritos admitem mais de uma causa.",
    ),
    "fora_de_escopo": (
        "Fora de escopo",
        "A pergunta não trata de falha ou procedimento de manutenção "
        "cadastrado.",
    ),
    "estado": (
        "Estado de operação",
        "O termo citado descreve condição normal, não falha.",
    ),
    "documentado": (
        "Documentado",
        "Existe procedimento cadastrado para o que foi perguntado.",
    ),
    "parcialmente_documentado": (
        "Parcialmente documentado",
        "Parte das famílias citadas tem procedimento cadastrado, parte não.",
    ),
}

# Quem escreveu o texto. Distingue sintese de modelo de recorte deterministico
# — e a diferenca entre "o modelo redigiu" e "o validador rejeitou e caiu no
# template", que a versao anterior da tela nao mostrava no diagnostico.
REDATOR = {
    "ollama": "modelo local (Ollama)",
    "openai": "modelo remoto (OpenAI)",
    "template": "extração determinística dos trechos",
}


def titulo_diagnostico(status: str) -> str:
    return DIAGNOSTICO.get(status, (status, ""))[0]


def explicacao_diagnostico(status: str) -> str:
    return DIAGNOSTICO.get(status, ("", ""))[1]


def titulo_chat(status: str) -> str:
    return CHAT.get(status, (status, ""))[0]


def explicacao_chat(status: str) -> str:
    return CHAT.get(status, ("", ""))[1]


def nome_redator(redator: str | None) -> str:
    if not redator:
        return "resposta determinística (sem modelo)"
    return REDATOR.get(redator, redator)


class Familias:
    """Vocabulario de familias carregado de GET /familias.

    Envolver a lista crua em um objeto evita espalhar
    `next(f for f in familias if f["familia"] == x)` pelas paginas, e da um
    lugar unico para o comportamento de familia desconhecida (rotula com o
    proprio slug em vez de estourar KeyError no meio da renderizacao).
    """

    def __init__(self, itens: list[dict]) -> None:
        self._itens = list(itens)
        self._por_slug = {item["familia"]: item for item in self._itens}

    def __len__(self) -> int:
        return len(self._itens)

    def rotulo(self, familia: str) -> str:
        item = self._por_slug.get(familia)
        return item["rotulo"] if item else familia

    def e_falha(self, familia: str) -> bool:
        item = self._por_slug.get(familia)
        return bool(item) and item["tipo"] == "falha"

    def documentado(self, familia: str) -> bool:
        item = self._por_slug.get(familia)
        return bool(item) and bool(item["documentado"])

    def falhas(self) -> list[dict]:
        return [item for item in self._itens if item["tipo"] == "falha"]

    def estados(self) -> list[dict]:
        return [item for item in self._itens if item["tipo"] == "estado"]

    def slugs_de_falha(self) -> list[str]:
        return [item["familia"] for item in self.falhas()]

    def sem_documento(self) -> list[dict]:
        """Familias de falha sem procedimento cadastrado.

        E a lista que explica, na tela, exatamente quando o sistema vai se
        conter: estas familias nunca recebem recomendacao.
        """
        return [item for item in self.falhas() if not item["documentado"]]

    def cobertura(self) -> tuple[int, int]:
        falhas = self.falhas()
        return sum(1 for item in falhas if item["documentado"]), len(falhas)
