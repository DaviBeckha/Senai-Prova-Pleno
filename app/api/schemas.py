from pydantic import BaseModel, ConfigDict, create_model

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
    status: str
    resposta: str
    families: list[str]
    fontes: list[str]
    renderer: str | None
    degraded: bool
    limitations: list[str]
    validation_errors: list[str]

    # Dois exemplos no Swagger bastam para mostrar, sem provocar os dois casos
    # ao vivo, a distincao central do projeto: resposta fundamentada (status
    # "answered", com fontes e renderer) versus contencao por falta de
    # documento (status "undocumented", sem fontes nem renderer). Rotulos
    # reais — ver app/pipeline.py::answer_question e
    # app/chat/responses.py::undocumented_report.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "answered",
                    "resposta": (
                        "- Ajustar tensão da correia até atingir a deflexão "
                        "especificada [Doc4.pdf — seção 9.1; evidência correia:E1]."
                    ),
                    "families": ["correia"],
                    "fontes": ["Doc4.pdf"],
                    "renderer": "ollama",
                    "degraded": False,
                    "limitations": [
                        "A evidência não cobre o torque exato de reaperto."
                    ],
                    "validation_errors": [],
                },
                {
                    "status": "undocumented",
                    "resposta": (
                        "Reconheci o problema como falta fase, mas ainda não "
                        "existe documento orientativo cadastrado para essa "
                        "manutenção."
                    ),
                    "families": ["falta_fase"],
                    "fontes": [],
                    "renderer": None,
                    "degraded": False,
                    "limitations": [],
                    "validation_errors": [],
                },
            ]
        }
    )
