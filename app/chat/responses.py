"""Respostas do chat que nao dependem de RAG nem de LLM.

Todo caminho aqui e deterministico: mesma pergunta, mesma resposta, sem
chamada de rede. Sao os desfechos em que gerar texto com modelo seria pior
que responder o fato — familia sem documento, sintoma ambiguo, pergunta fora
do dominio, contagem de historico.
"""

from collections.abc import Callable

from app.chat.types import ChatReport


def _display(family: str) -> str:
    """Identificador interno -> forma legivel ao operador (falta_fase -> falta fase)."""
    return family.replace("_", " ")


def _names(families: tuple[str, ...]) -> str:
    return ", ".join(_display(family) for family in families)


def document_status_report(
    families: tuple[str, ...],
    has_document: Callable[[str], bool],
) -> ChatReport:
    if not families:
        # "Existe documento cadastrado?" sem dizer para o que. Sem esta guarda
        # os dois ramos abaixo seriam falsos e a mensagem final sairia vazia.
        return ChatReport(
            "needs_clarification",
            (
                "Para verificar o cadastro preciso saber de qual falha ou "
                "componente se trata. Informe, por exemplo, correia, polia ou "
                "rolamento."
            ),
        )
    documented = tuple(family for family in families if has_document(family))
    undocumented = tuple(family for family in families if family not in documented)
    if documented and not undocumented:
        return ChatReport(
            "documented",
            f"Sim. Existe documento orientativo cadastrado para: {_names(documented)}.",
            families,
        )
    if undocumented and not documented:
        return ChatReport(
            "undocumented",
            (
                "Não. Ainda não existe documento orientativo cadastrado para: "
                f"{_names(undocumented)}."
            ),
            families,
        )
    return ChatReport(
        "partially_documented",
        (
            f"Com documento: {_names(documented)}. "
            f"Sem documento: {_names(undocumented)}."
        ),
        families,
    )


def undocumented_report(families: tuple[str, ...]) -> ChatReport:
    return ChatReport(
        "undocumented",
        (
            f"Reconheci o problema como {_names(families)}, mas ainda não existe "
            "documento orientativo cadastrado para essa manutenção."
        ),
        families,
    )


def clarification_report(candidates: tuple[str, ...]) -> ChatReport:
    return ChatReport(
        "needs_clarification",
        (
            "Os sintomas podem ter mais de uma causa. Confirme o componente ou "
            f"a falha antes de solicitar o procedimento. Possibilidades: "
            f"{_names(candidates)}."
        ),
        candidates,
    )


def out_of_scope_report() -> ChatReport:
    return ChatReport(
        "out_of_scope",
        (
            "Consigo responder somente sobre falhas e procedimentos de manutenção "
            "industrial cadastrados. Informe o componente, a falha ou os sintomas."
        ),
    )


def state_report(families: tuple[str, ...]) -> ChatReport:
    return ChatReport(
        "state",
        (
            f"{_names(families)} representa estado de operação, não uma falha "
            "com ação corretiva."
        ),
        families,
    )


def history_report(
    families: tuple[str, ...],
    stats_by_family: dict,
) -> ChatReport:
    lines = []
    for family in families:
        stats = stats_by_family[family]
        lines.append(
            f"{_display(family)}: {stats.total} ocorrências; "
            f"{stats.freq_per_day} por dia; período de "
            f"{stats.first_seen[:10]} a {stats.last_seen[:10]}."
        )
    return ChatReport(
        "answered",
        "\n".join(lines),
        families,
    )
