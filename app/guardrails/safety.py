"""Contencao de risco fisico, avaliada antes de RAG e LLM.

Três regras distintas:

1. `assess_question_safety` orienta toda intervencao fisica com uma mensagem
   deterministica sobre EPI, parada completa, bloqueio e ausencia de energia.

2. Se o equipamento esta em funcionamento, a orientacao encerra o fluxo antes
   de RAG e LLM sem fornecer passos executaveis nessas condicoes. A regra exige
   verbo de intervencao E marcador de maquina operando para nao confundir
   observacao dinamica com ordem de servico.

3. `safety_evidence_limitation` declara quando uma pergunta de intervencao
   nao recupera evidencia documental de seguranca. Se a pergunta pede
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
    ADVISE_INTERVENTION = "advise_intervention"
    ADVISE_LIVE_INTERVENTION = "advise_live_intervention"


@dataclass(frozen=True)
class SafetyDecision:
    outcome: SafetyOutcome
    message: str = ""


SAFETY_ADVISORY = (
    "Antes de qualquer intervenção, verifique os EPIs e demais equipamentos "
    "de segurança exigidos pelo procedimento da empresa e confirme que estão "
    "em condições de uso. Para ajustar, remover, instalar ou substituir peças, "
    "desligue completamente o equipamento, aguarde a parada total, aplique "
    "bloqueio e etiquetagem das fontes de energia e confirme a ausência de "
    "energia. Siga o procedimento e a autorização de segurança vigentes."
)
LIVE_INTERVENTION_GUIDANCE = (
    "Não realize a intervenção enquanto o equipamento estiver ligado ou em "
    "movimento.\n\n" + SAFETY_ADVISORY
)


_INTERVENTION = re.compile(
    r"\b(?:ajust\w*|apert\w*|remov\w*|instal\w*|substitu\w*|"
    # "abrir" usa radical estreito, nao abr\w*: a versao ampla casaria
    # tambem substantivos sem relacao, como "abraçadeira" (normalizado
    # "abracadeira"), que aparece no vocabulario de correias/polias.
    # "trocar" tem o mesmo desvio ortografico de "corrigir": a forma
    # imperativo/subjuntivo troca c por qu antes de e ("troque", "troquem").
    r"mex(?:er|a|am|endo|eu|e|em|o|ia|iam)\b|"
    r"abr(?:ir|a|am|indo|iu)\b|desmont\w*|corrij\w*|corrig\w*|troc\w*|troqu\w*)\b"
)
_RUNNING = re.compile(
    r"\b(?:maquina ligada|equipamento ligado|motor ligado|sem parar|operando|"
    r"em funcionamento|funcionando|girando|rodando)\b"
)
_SAFETY_EVIDENCE = re.compile(
    r"\b(?:seguranca|desligar|bloqueio|etiquetagem|ausencia de energia|parada completa)\b"
)


def assess_question_safety(question: str) -> SafetyDecision:
    normalized = normalize_text(question)
    if not _INTERVENTION.search(normalized):
        return SafetyDecision(SafetyOutcome.ALLOW)
    if _RUNNING.search(normalized):
        return SafetyDecision(
            SafetyOutcome.ADVISE_LIVE_INTERVENTION,
            LIVE_INTERVENTION_GUIDANCE,
        )
    return SafetyDecision(SafetyOutcome.ADVISE_INTERVENTION, SAFETY_ADVISORY)


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
