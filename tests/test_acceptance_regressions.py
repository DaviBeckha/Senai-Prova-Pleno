"""Regressões dos casos CHAT-001–017 e DIAG-001–005 executados com Ollama."""

import json

import pandas as pd
import pytest

from app.chat.analyzer import analyze_question
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

    assert unsafe.status == "refused_unsafe"
    assert history.status == "answered"
    assert "2 ocorrências" in history.message


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
