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


# Radicais amplos como ``ajust\w*`` tambem casam substantivos ("ajustes") e
# podem substituir uma consulta historica por uma orientacao de risco. As
# terminacoes abaixo aceitam apenas formas verbais comuns. A pequena excecao
# nominal "de ajuste" e removida antes da busca porque "ajuste" tambem e uma
# forma valida do imperativo.
_AR_FORMS = r"(?:ar|ando|ou|o|a|am|amos|aram|ava|avam|e|em)"
_ER_FORMS = r"(?:er|endo|eu|o|a|am|e|em|emos|eram|ia|iam)"
_IR_FORMS = r"(?:ir|indo|iu|o|a|am|e|em|imos|iram|ia|iam)"
_INTERVENTION = re.compile(
    rf"\b(?:"
    rf"ajust{_AR_FORMS}|(?:re)?apert{_AR_FORMS}|"
    rf"instal{_AR_FORMS}|desmont{_AR_FORMS}|"
    rf"alinh{_AR_FORMS}|lubrific{_AR_FORMS}|repar{_AR_FORMS}|"
    rf"remov{_ER_FORMS}|mex{_ER_FORMS}|abr{_IR_FORMS}|"
    rf"substitu(?:ir|indo|iu|o|a|am|i|em|imos|iram|ia|iam)|"
    rf"corrig(?:ir|indo|iu|o|e|em|imos|iram|ia|iam)|corrij(?:a|am|o)|"
    rf"troc(?:ar|ando|ou|o|a|am|amos|aram|ava|avam)|troqu(?:e|em)"
    rf")\b"
)
_NOMINAL_INTERVENTION = re.compile(
    r"\b(?:de|do|da|dos|das|sobre)\s+(?:ajuste|aperto|reparo)\b|"
    r"\b(?:ajustes|apertos|reparos)\b"
)
_RUNNING = re.compile(
    r"\b(?:maquina ligada|equipamento ligado|motor ligado|sem parar|operando|"
    r"em funcionamento|funcionando|girando|rodando)\b"
)
_SAFETY_EVIDENCE = re.compile(
    r"\b(?:seguranca|desligar|bloqueio|etiquetagem|ausencia de energia|parada completa)\b"
)


def _has_intervention(normalized: str) -> bool:
    without_nominal_uses = _NOMINAL_INTERVENTION.sub("", normalized)
    return _INTERVENTION.search(without_nominal_uses) is not None


def assess_question_safety(question: str) -> SafetyDecision:
    normalized = normalize_text(question)
    if not _has_intervention(normalized):
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
    if not _has_intervention(normalized):
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
