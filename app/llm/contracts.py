"""Contrato de saida do redator: acoes com evidencia, nao texto livre.

Cada passo carrega a citacao literal que o sustenta, para que a validacao em
app/llm/grounding.py possa conferir afirmacao por afirmacao — em vez de
confiar que o modelo seguiu a instrucao de nao inventar.
"""

from pydantic import BaseModel, Field


class GroundedStep(BaseModel):
    action: str = Field(min_length=1, max_length=500)
    family: str = Field(min_length=1, max_length=64)
    evidence_id: str = Field(min_length=1, max_length=96)
    quote: str = Field(min_length=1, max_length=600)


class GroundedDraft(BaseModel):
    steps: list[GroundedStep] = Field(default_factory=list, max_length=20)
    # Partes da pergunta que a evidencia nao responde. Um rascunho so com
    # `unanswered` e VALIDO: o modelo declarando que nao sabe e o resultado
    # desejado, nao uma falha.
    unanswered: list[str] = Field(default_factory=list, max_length=10)
