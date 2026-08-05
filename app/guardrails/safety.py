"""Contencao de risco fisico, avaliada antes de RAG e LLM.

Duas regras distintas:

1. `assess_question_safety` recusa intervencao com equipamento em
   funcionamento. E conservadora de proposito — exige verbo de intervencao E
   marcador de maquina operando —, para nao confundir observacao dinamica
   ("que ruido devo ouvir com o motor operando?") com ordem de servico.

2. `safety_evidence_limitation` nao recusa: declara. Se a pergunta pede
   intervencao e nenhum trecho recuperado fala de desligamento, bloqueio ou
   seguranca, a resposta sai avisando que nao autoriza execucao. Uma resposta
   tecnicamente correta e perigosa se o operador a ler como liberacao.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.chat.normalization import normalize_text
from app.rag.search import RetrievalBundle


class SafetyOutcome(StrEnum):
    ALLOW = "allow"
    REFUSE_LIVE_INTERVENTION = "refuse_live_intervention"


@dataclass(frozen=True)
class SafetyDecision:
    outcome: SafetyOutcome
    message: str = ""


_INTERVENTION = re.compile(
    r"\b(?:ajustar|apertar|remover|instalar|substituir|abrir|desmontar|corrigir|trocar)\b"
)
_RUNNING = re.compile(
    r"\b(?:maquina ligada|equipamento ligado|motor ligado|sem parar|operando|em funcionamento)\b"
)
_SAFETY_EVIDENCE = re.compile(
    r"\b(?:seguranca|desligar|bloqueio|etiquetagem|ausencia de energia|parada completa)\b"
)


def assess_question_safety(question: str) -> SafetyDecision:
    normalized = normalize_text(question)
    if _INTERVENTION.search(normalized) and _RUNNING.search(normalized):
        return SafetyDecision(
            SafetyOutcome.REFUSE_LIVE_INTERVENTION,
            (
                "Não execute ajuste ou intervenção com o equipamento em "
                "funcionamento. Interrompa a atividade e siga o procedimento "
                "de segurança e autorização vigente da empresa."
            ),
        )
    return SafetyDecision(SafetyOutcome.ALLOW)


def safety_evidence_limitation(
    question: str,
    bundle: RetrievalBundle,
) -> str | None:
    normalized = normalize_text(question)
    if not _INTERVENTION.search(normalized):
        return None
    evidence_text = normalize_text(
        " ".join(item.chunk.text for item in bundle.items)
    )
    if _SAFETY_EVIDENCE.search(evidence_text):
        return None
    return (
        "Nenhuma evidência de segurança, parada ou bloqueio foi recuperada. "
        "Esta resposta não autoriza a execução da intervenção."
    )
