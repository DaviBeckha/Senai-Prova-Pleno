from app.guardrails.policy import decide
from app.similarity.engine import SimilarityResult


def _res(family, kind):
    return SimilarityResult(family, kind, [1], {family: 10})


def test_estado_nunca_diagnostica():
    d = decide(_res("normal", "estado"), has_document=lambda f: True)
    assert d.outcome == "estado"


def test_falha_documentada():
    d = decide(_res("correia", "falha"), has_document=lambda f: f == "correia")
    assert d.outcome == "documentado"


def test_falha_sem_documento():
    d = decide(_res("ventoinha", "falha"), has_document=lambda f: False)
    assert d.outcome == "nao_documentado"


def test_desconhecido_e_tratado_como_sem_documento():
    d = decide(_res("desconhecido", "desconhecido"), has_document=lambda f: True)
    assert d.outcome == "nao_documentado"


def test_empate_do_knn_retorna_inconclusivo_antes_do_documento():
    result = SimilarityResult(
        "correia",
        "falha",
        [1, 2],
        {"correia": 1, "rolamento_ball": 1},
        candidate_families=("correia", "rolamento_ball"),
        top_vote_share=0.5,
        vote_margin=0,
        is_ambiguous=True,
    )

    decision = decide(result, has_document=lambda family: True)

    assert decision.outcome == "inconclusivo"
    assert decision.family is None
    assert decision.candidate_families == ("correia", "rolamento_ball")
