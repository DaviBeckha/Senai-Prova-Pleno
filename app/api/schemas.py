"""Contrato HTTP em portugues.

Os relatorios internos (DiagnosisReport, ChatReport) mantem nomes em ingles: os
valores de `status` sao identificadores de maquina de estado, asseridos em
dezenas de pontos da suite, e renomea-los ali seria mudar logica para arrumar
vocabulario. A traducao acontece AQUI, no limite HTTP, pelas fabricas
`de_relatorio` de cada modelo — o cliente ve portugues, o nucleo continua
estavel.

As 23 features do EventIn seguem em ingles de proposito: sao os nomes das
colunas do banner.xlsx e de sensor_readings (ver app/data/loader.py
FEATURE_COLUMNS e app/data/models.py SensorReading). Renomea-las exigiria
migration, novo mapeamento do dataset e invalidaria os fixtures de demo/ —
sao identidade de dado, nao texto de interface.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.data.labels import display_label
from app.data.loader import FEATURE_COLUMNS

# EventIn e gerado dinamicamente a partir de FEATURE_COLUMNS: as 23 features
# numericas viram campos obrigatorios (float), entao aparecem no Swagger e
# qualquer feature ausente ou nula vira 422 automatico da validacao Pydantic.
EventIn = create_model(
    "EventIn",
    **{c: (float, ...) for c in FEATURE_COLUMNS},
    modo=(str | None, None),
)

# Status interno do ChatReport -> status do contrato HTTP.
#
# Alem de traduzir, isto CONVERGE o vocabulario dos dois endpoints: /eventos ja
# devolvia "sem_documento" e "estado", e o /chat usava "undocumented" e "state"
# para as mesmas ideias. Depois do mapa, os dois falam a mesma lingua e o
# dashboard tem uma tabela de traducao unica.
_STATUS_CHAT_PT = {
    "answered": "respondido",
    "undocumented": "sem_documento",
    "insufficient_evidence": "evidencia_insuficiente",
    "refused_unsafe": "recusado_seguranca",
    "refused_internal": "recusado_interno",
    "needs_clarification": "precisa_esclarecimento",
    "out_of_scope": "fora_de_escopo",
    "state": "estado",
    "documented": "documentado",
    "partially_documented": "parcialmente_documentado",
}


def status_chat_pt(status: str) -> str:
    """Traduz o status interno do chat, degradando para o proprio valor.

    Um status novo no pipeline que ainda nao tenha entrada aqui atravessa cru
    em vez de virar 500 na serializacao. O teste de completude em
    tests/test_api.py cobre o conjunto conhecido.
    """
    return _STATUS_CHAT_PT.get(status, status)


def status_diagnostico_pt(status: str) -> str:
    if status == "insufficient_evidence":
        return "evidencia_insuficiente"
    return status


class JanelaOcorrencias(BaseModel):
    """Periodo coberto pelo historico da familia diagnosticada.

    Sem a janela, `frequencia_por_dia` e ininteligivel: 1.499,88/dia medido em
    8 dias e outra afirmacao que o mesmo numero medido em 47 dias.
    """
    primeira: str
    ultima: str
    por_dia: dict[str, int]


class EvidenciaOut(BaseModel):
    """Trecho recuperado que sustenta ou contextualiza uma resposta."""

    id: str
    familia: str
    fonte: str
    secao: str
    trecho: str

    @classmethod
    def de_item(cls, item) -> "EvidenciaOut":
        return cls(
            id=item.evidence_id,
            familia=item.family,
            fonte=item.chunk.source,
            secao=item.chunk.section,
            trecho=item.chunk.text,
        )


class DiagnosticoOut(BaseModel):
    status: str
    familia: str | None
    rotulo: str
    mensagem: str
    total_ocorrencias: int
    frequencia_por_dia: float
    ocorrencias: JanelaOcorrencias
    fontes: list[str]
    redator: str | None
    degradado: bool
    # Por que a geracao foi rejeitada pela validacao de fundamentacao. Sem
    # este campo, uma resposta em template extrativo chega indistinguivel de
    # uma geracao aceita — e numa avaliacao local do modo offline
    # (qwen2.5:7b-instruct em CPU, 16 geracoes) 7 delas, 43,75%, foram
    # rejeitadas pelo grounding e cairam no template.
    erros_de_validacao: list[str]
    # Distribuicao completa do voto kNN, nao so a familia vencedora: na mesma
    # avaliacao, tres repeticoes do payload de correia elegeram a familia com
    # 9 de 50 votos, EMPATADA com rolamento_outer e rolamento_ball. Sem a
    # distribuicao, a tela apresenta um empate de 18% como diagnostico
    # conclusivo.
    votos_por_familia: dict[str, int]
    vizinhos_consultados: int
    familias_candidatas: list[str]
    participacao_maior_voto: float
    margem_votos: int
    evidencias: list[EvidenciaOut] = Field(default_factory=list)

    @classmethod
    def de_relatorio(cls, report) -> "DiagnosticoOut":
        return cls(
            status=status_diagnostico_pt(report.status),
            familia=report.family,
            rotulo=(
                display_label(report.family)
                if report.family is not None
                else "Diagnóstico inconclusivo"
            ),
            mensagem=report.message,
            total_ocorrencias=report.total_ocorrencias,
            frequencia_por_dia=report.freq_per_day,
            ocorrencias=JanelaOcorrencias(
                primeira=report.first_seen,
                ultima=report.last_seen,
                por_dia=report.per_day,
            ),
            fontes=list(report.sources),
            redator=report.renderer,
            degradado=report.degraded,
            erros_de_validacao=list(report.validation_errors),
            votos_por_familia=report.family_votes,
            vizinhos_consultados=report.neighbor_count,
            familias_candidatas=list(report.candidate_families),
            participacao_maior_voto=report.top_vote_share,
            margem_votos=report.vote_margin,
            evidencias=[
                EvidenciaOut.de_item(item)
                for item in getattr(report, "evidence", ())
            ],
        )


class ChatIn(BaseModel):
    pergunta: str
    modo: str | None = None


class ChatOut(BaseModel):
    status: str
    resposta: str
    familias: list[str]
    fontes: list[str]
    redator: str | None
    degradado: bool
    limitacoes: list[str]
    erros_de_validacao: list[str]
    evidencias: list[EvidenciaOut] = Field(default_factory=list)

    @classmethod
    def de_relatorio(cls, report) -> "ChatOut":
        return cls(
            status=status_chat_pt(report.status),
            resposta=report.message,
            familias=list(report.families),
            fontes=list(report.sources),
            redator=report.renderer,
            degradado=report.degraded,
            limitacoes=list(report.limitations),
            erros_de_validacao=list(report.validation_errors),
            evidencias=[
                EvidenciaOut.de_item(item)
                for item in getattr(report, "evidence", ())
            ],
        )

    # Dois exemplos no Swagger bastam para mostrar, sem provocar os dois casos
    # ao vivo, a distincao central do projeto: resposta fundamentada (status
    # "respondido", com fontes e redator) versus contencao por falta de
    # documento (status "sem_documento", sem fontes nem redator). Rotulos
    # reais — ver app/pipeline.py::answer_question e
    # app/chat/responses.py::undocumented_report.
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "respondido",
                    "resposta": (
                        "- Ajustar tensão da correia até atingir a deflexão "
                        "especificada [Doc4.pdf — seção 9.1; evidência correia:E1]."
                    ),
                    "familias": ["correia"],
                    "fontes": ["Doc4.pdf"],
                    "redator": "ollama",
                    "degradado": False,
                    "limitacoes": [
                        "A evidência não cobre o torque exato de reaperto."
                    ],
                    "erros_de_validacao": [],
                    "evidencias": [],
                },
                {
                    "status": "sem_documento",
                    "resposta": (
                        "Reconheci o problema como Falta de fase, mas ainda não "
                        "existe documento orientativo cadastrado para essa "
                        "manutenção."
                    ),
                    "familias": ["falta_fase"],
                    "fontes": [],
                    "redator": None,
                    "degradado": False,
                    "limitacoes": [],
                    "erros_de_validacao": [],
                    "evidencias": [],
                },
            ]
        }
    )


class FamiliaOut(BaseModel):
    """Vocabulario do dominio: o dashboard busca uma vez e rotula tudo.

    Existir como endpoint proprio evita repetir `rotulo` em cada objeto de
    cada resposta — os votos kNN, os eixos dos graficos, os chips do chat e o
    selectbox de upload todos resolvem o nome por este mapa.
    """
    familia: str
    rotulo: str
    tipo: str
    documentado: bool


class DocumentoOut(BaseModel):
    """Documento registrado.

    `source_path` do modelo Document NAO entra aqui: e caminho de arquivo no
    disco do servidor (inclusive dentro de UPLOADS_DIR) e nao tem uso legitimo
    no cliente.
    """
    familia: str
    rotulo: str
    titulo: str
    cadastrado_em: datetime


class DocumentoRegistradoOut(BaseModel):
    trechos_indexados: int


class JanelaHistorico(BaseModel):
    primeira: str
    ultima: str


class HistoricoFamiliaOut(BaseModel):
    familia: str
    tipo: str
    ocorrencias: int


class HistoricoDiaOut(BaseModel):
    dia: str
    familia: str
    ocorrencias: int


class HistoricoResumoOut(BaseModel):
    """Agregados do MESMO DataFrame que alimenta o kNN.

    Devolve apenas slugs; o rotulo em portugues vem do cache de GET /familias.
    Repetir o rotulo em cada uma das ~1.000 entradas de `por_dia` inflaria a
    resposta e criaria uma segunda fonte de vocabulario.
    """
    total_leituras: int
    janela: JanelaHistorico
    por_familia: list[HistoricoFamiliaOut]
    por_dia: list[HistoricoDiaOut]


class AmostraOut(BaseModel):
    """Uma leitura real do historico, pronta para POST /eventos.

    `features_substituidas` nomeia as colunas cujo valor no historico nao pode
    ser convertido para numero e foram enviadas como 0.0 — o mesmo contrato de
    scripts/simulator.py::build_payload, que hoje avisa apenas no stdout do
    container. Aqui o aviso chega a quem esta olhando a tela.
    """
    id_externo: int | None
    rotulo_original: str
    familia: str
    features: dict[str, float]
    features_substituidas: list[str]
