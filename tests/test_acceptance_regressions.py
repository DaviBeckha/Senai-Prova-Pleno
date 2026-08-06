"""Regressões dos casos CHAT-001–017 e DIAG-001–005 executados com Ollama."""

import json

import pandas as pd
import pytest

from app.chat.analyzer import analyze_question
from app.chat.types import ChatIntent
from app.core.maintenance_intent import ContentRole
from app.core.text import normalize_text
from app.data.loader import FEATURE_COLUMNS
from app.llm.router import Router
from app.llm.template_fallback import TemplateRenderer
from app.pipeline import PrescriptivePipeline
from app.rag.chunking import Chunk
from app.rag.search import SearchHit
from app.similarity.engine import SimilarityEngine, SimilarityResult


def _chunk(
    family: str,
    role: ContentRole,
    text: str,
    order: int,
) -> Chunk:
    return Chunk(
        family,
        f"{family}.md",
        role.value,
        text,
        (role.value,),
        role,
        order,
    )


CHUNKS = {
    "correia": (
        _chunk(
            "correia",
            ContentRole.SAFETY,
            (
                "Desligar o equipamento, aplicar bloqueio, confirmar ausência "
                "de energia e aguardar a parada completa."
            ),
            1,
        ),
        _chunk(
            "correia",
            ContentRole.ADJUSTMENT,
            "Ajustar a tensão da correia frouxa e reapertar os parafusos.",
            2,
        ),
        _chunk(
            "correia",
            ContentRole.REPLACEMENT,
            "Remover a correia antiga e instalar a correia nova.",
            3,
        ),
        _chunk(
            "correia",
            ContentRole.VALIDATION,
            "Validar a tensão e a estabilidade após o ajuste.",
            4,
        ),
    ),
    "polia": (
        _chunk(
            "polia",
            ContentRole.SAFETY,
            "Desligar e bloquear o equipamento antes de intervir na polia.",
            1,
        ),
        _chunk(
            "polia",
            ContentRole.ADJUSTMENT,
            "Ajustar a posição da polia no conjunto.",
            2,
        ),
        _chunk(
            "polia",
            ContentRole.VALIDATION,
            "Validar o alinhamento da polia após o ajuste.",
            3,
        ),
    ),
    "cocked_rotor": (
        _chunk(
            "cocked_rotor",
            ContentRole.ADJUSTMENT,
            "Corrigir a posição do rotor inclinado.",
            1,
        ),
    ),
    "rolamento_combination": (
        _chunk(
            "rolamento_combination",
            ContentRole.ADJUSTMENT,
            "Corrigir a falha combinada no rolamento.",
            1,
        ),
    ),
}


class _LayeredIndex:
    def search(self, query, doc_family, k=4, min_score=0.0):
        return [
            SearchHit(chunk, 0.9 - position * 0.01)
            for position, chunk in enumerate(CHUNKS.get(doc_family, ())[:k])
        ]

    def chunks_for_family(self, doc_family):
        return CHUNKS.get(doc_family, ())


class _Registry:
    def has_document(self, family):
        return family in CHUNKS


class _OnlyLimitationsRenderer:
    name = "only-limitations"

    def render(self, ctx):
        return json.dumps({
            "steps": [],
            "unanswered": ["Não há uma ação completa nas evidências."],
        })


class _WeakActionRenderer:
    name = "weak-action"

    def render(self, ctx):
        return json.dumps({
            "steps": [{
                "action": "Verificar os parafusos.",
                "family": "correia",
                "evidence_id": "correia:E2",
                "quote": "Verificar os parafusos antes de ajustar a tensão.",
            }],
            "unanswered": [],
        })


class _RaisingRouter:
    def render(self, ctx):
        raise AssertionError("o redator não deveria ser chamado")


class _RaisingIndex:
    def search(self, query, doc_family, k=4, min_score=0.0):
        raise AssertionError("o índice não deveria ser consultado")


class _StaticEngine:
    def __init__(self, result):
        self._result = result

    def query(self, event):
        return self._result


def _dataframe(*families: str) -> pd.DataFrame:
    rows = []
    for index, family in enumerate(families):
        row = {column: 0.1 for column in FEATURE_COLUMNS}
        row.update(
            id=index,
            family=family,
            kind="estado" if family == "normal" else "falha",
            created_at=pd.Timestamp("2026-06-01T00:00:00Z"),
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _chat_pipeline(primary=None) -> PrescriptivePipeline:
    df = _dataframe(*CHUNKS)
    engine = SimilarityEngine()
    engine.fit(df)
    primary = primary or TemplateRenderer()
    return PrescriptivePipeline(
        engine,
        df,
        _Registry(),
        _LayeredIndex(),
        Router(primary, TemplateRenderer()),
    )


CHAT_CASES = (
    ("CHAT-001", "Como ajustar a tensao de uma correia frouxa?", ("correia",), ("adjust",), False),
    ("CHAT-002", "Qual e o procedimento completo para trocar uma correia?", ("correia",), ("replace",), False),
    ("CHAT-003", "Como verificar e corrigir o alinhamento de uma polia?", ("polia",), ("inspect", "align"), False),
    ("CHAT-004", "Como corrigir o desalinhamento entre eixos?", ("desalinhado",), ("repair",), False),
    ("CHAT-005", "Qual e o procedimento para corrigir o desbalanceamento do rotor?", ("desbalanceado",), ("repair",), False),
    ("CHAT-006", "Como corrigir um rotor inclinado?", ("cocked_rotor",), ("repair",), False),
    ("CHAT-007", "Como inspecionar e trocar o rolamento da pista interna?", ("rolamento_inner",), ("inspect", "replace"), False),
    ("CHAT-008", "Como corrigir falha na pista externa do rolamento?", ("rolamento_outer",), ("repair",), False),
    ("CHAT-009", "Como tratar defeito nas esferas do rolamento?", ("rolamento_ball",), ("repair",), False),
    ("CHAT-010", "Qual e o procedimento para falha combinada de rolamento?", ("rolamento_combination",), ("repair",), False),
    ("CHAT-011", "Como ajustar correia e polia no mesmo conjunto?", ("correia", "polia"), ("adjust",), False),
    ("CHAT-012", "Quais verificacoes de seguranca devem ser feitas antes de mexer na correia?", ("correia",), (), True),
    ("CHAT-013", "Como tratar defeito na esfera do rolamento?", ("rolamento_ball",), ("repair",), False),
    ("CHAT-014", "Qual e o procedimento para falha combinada no rolamento?", ("rolamento_combination",), ("repair",), False),
    ("CHAT-015", "Posso ajustar a correia com a maquina ligada?", ("correia",), ("adjust",), False),
    ("CHAT-016", "Quantas ocorrencias de correia existem no historico?", ("correia",), (), False),
    ("CHAT-017", "Como faco para corrigir uma correia frouxa?", ("correia",), ("repair",), False),
)


@pytest.mark.parametrize(
    ("case_id", "question", "families", "actions", "safety_only"),
    CHAT_CASES,
    ids=[case[0] for case in CHAT_CASES],
)
def test_matriz_manual_de_chat_e_interpretada(
    case_id,
    question,
    families,
    actions,
    safety_only,
):
    analysis = analyze_question(question)

    assert analysis.explicit_families == families, case_id
    assert analysis.requested_actions == actions, case_id
    assert analysis.safety_only is safety_only, case_id
    expected_intent = (
        ChatIntent.HISTORY
        if case_id == "CHAT-016"
        else ChatIntent.PROCEDURE
    )
    assert analysis.intent is expected_intent


@pytest.mark.parametrize(
    ("question", "expected_family"),
    (
        ("Como tratar defeito nas esferas do rolamento?", "rolamento_ball"),
        (
            "Qual e o procedimento para falha combinada de rolamento?",
            "rolamento_combination",
        ),
    ),
)
def test_variantes_naturais_de_alias_entram_no_escopo(question, expected_family):
    assert analyze_question(question).explicit_families == (expected_family,)


def test_acao_fraca_nao_passa_so_por_citar_chunk_de_ajuste():
    chunks = (
        _chunk(
            "correia",
            ContentRole.SAFETY,
            "Desligar e bloquear o equipamento.",
            1,
        ),
        _chunk(
            "correia",
            ContentRole.ADJUSTMENT,
            "Verificar os parafusos antes de ajustar a tensão.",
            2,
        ),
        _chunk(
            "correia",
            ContentRole.VALIDATION,
            "Validar a tensão após o ajuste.",
            3,
        ),
    )

    class WeakIndex:
        def search(self, query, doc_family, k=4, min_score=0.0):
            return [SearchHit(chunk, 0.9) for chunk in chunks]

        def chunks_for_family(self, doc_family):
            return chunks

    df = _dataframe("correia")
    engine = SimilarityEngine()
    engine.fit(df)
    pipeline = PrescriptivePipeline(
        engine,
        df,
        _Registry(),
        WeakIndex(),
        Router(_WeakActionRenderer(), TemplateRenderer()),
    )

    report = pipeline.answer_question("Como corrigir uma correia frouxa?")

    assert report.status == "insufficient_evidence"
    assert any("repair" in error for error in report.validation_errors)


def test_chat_017_prioriza_ajuste_e_exclui_substituicao():
    report = _chat_pipeline().answer_question(
        "Como faco para corrigir uma correia frouxa?"
    )
    answer = normalize_text(report.message)

    assert report.status == "answered"
    assert "ajustar a tensao" in answer
    assert "remover a correia antiga" not in answer


def test_chat_012_recupera_bloco_completo_de_seguranca():
    report = _chat_pipeline().answer_question(
        "Quais verificacoes de seguranca devem ser feitas antes de mexer na correia?"
    )
    answer = normalize_text(report.message)

    assert report.status == "answered"
    for expected in ("desligar", "bloqueio", "ausencia de energia", "parada completa"):
        assert expected in answer


def test_chat_011_cobre_correia_e_polia():
    report = _chat_pipeline().answer_question(
        "Como ajustar correia e polia no mesmo conjunto?"
    )
    answer = normalize_text(report.message)

    assert report.status == "answered"
    assert set(report.families) == {"correia", "polia"}
    assert "tensao da correia" in answer
    assert "posicao da polia" in answer


@pytest.mark.parametrize(
    "question",
    (
        "Como corrigir um rotor inclinado?",
        "Qual e o procedimento para falha combinada no rolamento?",
    ),
)
def test_resposta_apenas_com_limitacoes_e_insufficient_evidence(question):
    report = _chat_pipeline(_OnlyLimitationsRenderer()).answer_question(question)

    assert report.status == "insufficient_evidence"
    assert report.degraded is True
    assert any("nenhuma ação" in error for error in report.validation_errors)


def test_controles_deterministicos_nao_chamam_redator():
    df = _dataframe("correia", "correia")
    engine = SimilarityEngine()
    engine.fit(df)
    pipeline = PrescriptivePipeline(
        engine,
        df,
        _Registry(),
        _RaisingIndex(),
        _RaisingRouter(),
    )

    unsafe = pipeline.answer_question("Posso ajustar a correia com a maquina ligada?")
    history = pipeline.answer_question(
        "Quantas ocorrencias de correia existem no historico?"
    )

    assert unsafe.status == "answered"
    assert unsafe.sources == ()
    assert "Não realize a intervenção" in unsafe.message
    assert "desligue completamente" in unsafe.message
    assert history.status == "answered"
    assert "2 ocorrências" in history.message


_TIE_RESULT = SimilarityResult(
    dominant_family="correia",
    dominant_kind="falha",
    neighbor_ids=list(range(50)),
    family_votes={
        "correia": 9,
        "rolamento_outer": 9,
        "rolamento_ball": 9,
        "rolamento_inner": 7,
        "rolamento_combination": 7,
        "normal": 2,
        "cocked_rotor": 5,
        "eccentric_rotor": 2,
    },
    candidate_families=("correia", "rolamento_ball", "rolamento_outer"),
    top_vote_share=9 / 50,
    vote_margin=0,
    is_ambiguous=True,
)

DIAG_CASES = (
    ("DIAG-001", _TIE_RESULT, "correia", "diagnostico_inconclusivo"),
    ("DIAG-002", _TIE_RESULT, "correia", "diagnostico_inconclusivo"),
    ("DIAG-003", _TIE_RESULT, "correia", "diagnostico_inconclusivo"),
    (
        "DIAG-004",
        SimilarityResult(
            "ventoinha",
            "falha",
            list(range(50)),
            {"ventoinha": 13, "rolamento_combination": 10, "polia": 7},
            candidate_families=("ventoinha",),
            top_vote_share=13 / 50,
            vote_margin=3,
        ),
        "ventoinha",
        "sem_documento",
    ),
    (
        "DIAG-005",
        SimilarityResult(
            "normal",
            "estado",
            list(range(50)),
            {"normal": 28, "motor_desligado": 16, "baseline": 6},
            candidate_families=("normal",),
            top_vote_share=28 / 50,
            vote_margin=12,
        ),
        "normal",
        "estado",
    ),
)


@pytest.mark.parametrize(
    ("case_id", "result", "family", "expected_status"),
    DIAG_CASES,
    ids=[case[0] for case in DIAG_CASES],
)
def test_matriz_manual_de_diagnostico_e_deterministica(
    case_id,
    result,
    family,
    expected_status,
):
    pipeline = PrescriptivePipeline(
        _StaticEngine(result),
        _dataframe(family),
        _Registry(),
        _RaisingIndex(),
        _RaisingRouter(),
    )

    report = pipeline.diagnose({column: 0.1 for column in FEATURE_COLUMNS})

    assert report.status == expected_status, case_id
    assert report.renderer is None


def test_diag_001_empate_retem_diagnostico_sem_rag_ou_modelo():
    votes = {
        "correia": 9,
        "rolamento_outer": 9,
        "rolamento_ball": 9,
        "rolamento_inner": 7,
        "rolamento_combination": 7,
        "normal": 2,
        "cocked_rotor": 5,
        "eccentric_rotor": 2,
    }
    result = SimilarityResult(
        dominant_family="correia",
        dominant_kind="falha",
        neighbor_ids=list(range(50)),
        family_votes=votes,
        candidate_families=("correia", "rolamento_ball", "rolamento_outer"),
        top_vote_share=9 / 50,
        vote_margin=0,
        is_ambiguous=True,
    )
    pipeline = PrescriptivePipeline(
        _StaticEngine(result),
        _dataframe("correia"),
        _Registry(),
        _RaisingIndex(),
        _RaisingRouter(),
    )

    report = pipeline.diagnose({column: 0.1 for column in FEATURE_COLUMNS})

    assert report.status == "diagnostico_inconclusivo"
    assert report.family is None
    assert report.candidate_families == [
        "correia",
        "rolamento_ball",
        "rolamento_outer",
    ]


def test_diag_005_estado_normal_permanece_deterministico():
    result = SimilarityResult(
        dominant_family="normal",
        dominant_kind="estado",
        neighbor_ids=list(range(50)),
        family_votes={"normal": 28, "motor_desligado": 16, "baseline": 6},
        candidate_families=("normal",),
        top_vote_share=28 / 50,
        vote_margin=12,
    )
    pipeline = PrescriptivePipeline(
        _StaticEngine(result),
        _dataframe("normal"),
        _Registry(),
        _RaisingIndex(),
        _RaisingRouter(),
    )

    report = pipeline.diagnose({column: 0.1 for column in FEATURE_COLUMNS})

    assert report.status == "estado"
    assert report.family == "normal"
    assert report.renderer is None
