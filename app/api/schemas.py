from pydantic import BaseModel, create_model

from app.data.loader import FEATURE_COLUMNS

# EventIn e gerado dinamicamente a partir de FEATURE_COLUMNS: as 23 features
# numericas viram campos obrigatorios (float), entao aparecem no Swagger e
# qualquer feature ausente ou nula vira 422 automatico da validacao Pydantic.
EventIn = create_model(
    "EventIn",
    **{c: (float, ...) for c in FEATURE_COLUMNS},
    modo=(str | None, None),
)


class DiagnosisOut(BaseModel):
    status: str
    family: str
    message: str
    total_ocorrencias: int
    freq_per_day: float
    sources: list[str]
    renderer: str | None
    degraded: bool
    family_votes: dict[str, int]


class ChatIn(BaseModel):
    pergunta: str
    modo: str | None = None


class ChatOut(BaseModel):
    resposta: str
    fontes: list[str]
    degraded: bool
