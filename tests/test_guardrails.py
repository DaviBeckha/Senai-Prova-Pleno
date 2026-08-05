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
