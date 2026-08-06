from app.chat.analyzer import analyze_question
from app.core.maintenance_intent import ContentRole
from app.rag.chunking import Chunk
from app.rag.retrieval import retrieve_evidence
from app.rag.search import SearchHit


def _chunk(
    text: str,
    role: ContentRole,
    order: int,
) -> Chunk:
    return Chunk(
        "correia",
        "Doc4.pdf",
        role.value,
        text,
        section_path=(role.value,),
        content_role=role,
        document_order=order,
    )


class LayeredFakeIndex:
    def __init__(self) -> None:
        self.replacement = _chunk(
            "Substituir a correia: remover a antiga e instalar uma nova.",
            ContentRole.REPLACEMENT,
            14,
        )
        self.adjustment = _chunk(
            "Ajustar a tensão recomendada, reapertar e validar novamente.",
            ContentRole.ADJUSTMENT,
            9,
        )
        self.safety = _chunk(
            "Desligar, bloquear, confirmar ausência de energia e aguardar parada completa.",
            ContentRole.SAFETY,
            7,
        )
        self.validation = _chunk(
            "Medir vibração e verificar a estabilidade final.",
            ContentRole.VALIDATION,
            15,
        )
        self.general = _chunk(
            "Objetivo geral do sistema de transmissão por correias.",
            ContentRole.GENERAL,
            1,
        )
        self._all = (
            self.general,
            self.safety,
            self.adjustment,
            self.replacement,
            self.validation,
        )

    def search(self, query, doc_family, k=4, min_score=0.0):
        ranked_by_vector_only = (
            SearchHit(self.replacement, 0.95),
            SearchHit(self.general, 0.92),
            SearchHit(self.adjustment, 0.84),
            SearchHit(self.validation, 0.80),
            SearchHit(self.safety, 0.75),
        )
        return list(ranked_by_vector_only[:k])

    def chunks_for_family(self, doc_family):
        return self._all


def _retrieve(question: str, *, k: int = 4):
    analysis = analyze_question(question)
    return retrieve_evidence(
        LayeredFakeIndex(),
        question,
        analysis.explicit_families,
        analysis,
        k=k,
        min_score=0.0,
        complete_max_chars=12_000,
    )


def test_correcao_sem_dano_prioriza_ajuste_e_exclui_substituicao():
    bundle = _retrieve("Como corrigir uma correia frouxa?")

    roles = [item.chunk.content_role for item in bundle.items]
    assert ContentRole.ADJUSTMENT in roles
    assert ContentRole.REPLACEMENT not in roles


def test_intervencao_inclui_seguranca_procedimento_e_validacao():
    bundle = _retrieve("Como ajustar a tensão da correia?")

    roles = [item.chunk.content_role for item in bundle.items]
    assert roles == [
        ContentRole.SAFETY,
        ContentRole.ADJUSTMENT,
        ContentRole.VALIDATION,
    ]


def test_troca_explicita_preserva_bloco_de_substituicao():
    bundle = _retrieve("Como trocar uma correia com trincas?")

    roles = [item.chunk.content_role for item in bundle.items]
    assert ContentRole.REPLACEMENT in roles


def test_pergunta_de_seguranca_forca_bloco_completo_de_seguranca():
    bundle = _retrieve(
        "Quais verificacoes de seguranca devem ser feitas antes de mexer na correia?"
    )

    safety = next(
        item for item in bundle.items
        if item.chunk.content_role == ContentRole.SAFETY
    )
    assert "ausência de energia" in safety.chunk.text
    assert "parada completa" in safety.chunk.text


def test_procedimento_completo_nao_devolve_bloco_geral_irrelevante():
    bundle = _retrieve("Qual o procedimento completo para trocar uma correia?")

    roles = {item.chunk.content_role for item in bundle.items}
    assert ContentRole.GENERAL not in roles
    assert roles == {
        ContentRole.SAFETY,
        ContentRole.REPLACEMENT,
        ContentRole.VALIDATION,
    }
