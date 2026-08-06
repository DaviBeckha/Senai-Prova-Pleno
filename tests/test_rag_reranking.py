from app.chat.analyzer import analyze_question
from app.core.maintenance_intent import ContentRole
from app.rag.chunking import Chunk
from app.rag.reranking import select_procedure_hits
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
        self.inspection = _chunk(
            "Inspecionar a correia, os parafusos e as polias.",
            ContentRole.INSPECTION,
            8,
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
            self.inspection,
            self.adjustment,
            self.replacement,
            self.validation,
        )

    def search(self, query, doc_family, k=4, min_score=0.0):
        ranked_by_vector_only = (
            SearchHit(self.replacement, 0.95),
            SearchHit(self.general, 0.92),
            SearchHit(self.inspection, 0.88),
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


def test_explicacao_recupera_conceito_sem_passos_de_intervencao():
    bundle = _retrieve("O que significa o ajuste da correia?")

    roles = [item.chunk.content_role for item in bundle.items]
    assert roles == [ContentRole.GENERAL]
    assert "Objetivo geral" in bundle.items[0].chunk.text


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


def test_inspecao_com_seguranca_recupera_seguranca_e_inspecao():
    bundle = _retrieve("Como inspecionar a correia com segurança?")

    roles = [item.chunk.content_role for item in bundle.items]
    assert ContentRole.SAFETY in roles
    assert ContentRole.INSPECTION in roles


def test_todos_os_fragmentos_do_bloco_de_seguranca_sao_compostos():
    index = LayeredFakeIndex()
    safety_a = _chunk(
        "Desligar o equipamento e aplicar bloqueio.",
        ContentRole.SAFETY,
        7,
    )
    safety_b = _chunk(
        "Confirmar ausência de energia e aguardar parada completa.",
        ContentRole.SAFETY,
        8,
    )
    safety_b.section = safety_a.section
    safety_b.section_path = safety_a.section_path
    index._all = (safety_a, safety_b, index.adjustment, index.validation)
    analysis = analyze_question(
        "Quais verificacoes de seguranca devem ser feitas antes de mexer na correia?"
    )

    bundle = retrieve_evidence(
        index,
        analysis.original,
        analysis.explicit_families,
        analysis,
        k=4,
        min_score=0.0,
        complete_max_chars=12_000,
    )

    safety_texts = [
        item.chunk.text
        for item in bundle.items
        if item.chunk.content_role is ContentRole.SAFETY
    ]
    assert len(safety_texts) == 2
    assert any("bloqueio" in text for text in safety_texts)
    assert any("parada completa" in text for text in safety_texts)


def test_multiplas_acoes_reservam_evidencia_para_cada_uma():
    index = LayeredFakeIndex()
    index._all = (
        *(
            _chunk(f"Inspecionar item {position}.", ContentRole.INSPECTION, position)
            for position in range(4)
        ),
        index.replacement,
    )
    analysis = analyze_question("Como inspecionar e trocar a correia?")

    bundle = retrieve_evidence(
        index,
        analysis.original,
        analysis.explicit_families,
        analysis,
        k=4,
        min_score=0.0,
        complete_max_chars=12_000,
    )

    roles = {item.chunk.content_role for item in bundle.items}
    assert roles == {ContentRole.INSPECTION, ContentRole.REPLACEMENT}


def test_bloco_obrigatorio_maior_que_orcamento_falha_fechado():
    analysis = analyze_question(
        "Qual o procedimento completo para trocar uma correia?"
    )

    bundle = retrieve_evidence(
        LayeredFakeIndex(),
        analysis.original,
        analysis.explicit_families,
        analysis,
        k=4,
        min_score=0.0,
        complete_max_chars=10,
    )

    assert bundle.has_evidence is False
    assert bundle.families[0].complete is False
    assert bundle.families[0].omitted_chunks > 0


def test_primeiro_procedimento_nao_ultrapassa_saldo_do_orcamento():
    index = LayeredFakeIndex()
    analysis = analyze_question(
        "Qual o procedimento completo para trocar uma correia?"
    )
    mandatory_chars = len(index.safety.text) + len(index.validation.text)
    budget = mandatory_chars + len(index.replacement.text) - 1

    bundle = retrieve_evidence(
        index,
        analysis.original,
        analysis.explicit_families,
        analysis,
        k=4,
        min_score=0.0,
        complete_max_chars=budget,
    )

    assert sum(len(item.chunk.text) for item in bundle.items) <= budget
    assert bundle.families[0].complete is False
    assert bundle.families[0].omitted_chunks == 1


def test_reserva_por_acao_pode_ultrapassar_k_sem_descartar_acao():
    analysis = analyze_question(
        "Como diagnosticar, inspecionar, ajustar, alinhar, lubrificar, trocar "
        "e validar a correia?"
    )
    hits = [
        SearchHit(_chunk(role.value, role, position), 0.9 - position * 0.01)
        for position, role in enumerate((
            ContentRole.DIAGNOSIS,
            ContentRole.INSPECTION,
            ContentRole.ADJUSTMENT,
            ContentRole.ALIGNMENT,
            ContentRole.LUBRICATION,
            ContentRole.REPLACEMENT,
            ContentRole.VALIDATION,
        ))
    ]

    selected = select_procedure_hits(hits, analysis, k=4, complete=False)

    assert {hit.chunk.content_role for hit in selected} == {
        hit.chunk.content_role for hit in hits
    }


def test_procedimento_completo_nao_devolve_bloco_geral_irrelevante():
    bundle = _retrieve("Qual o procedimento completo para trocar uma correia?")

    roles = {item.chunk.content_role for item in bundle.items}
    assert ContentRole.GENERAL not in roles
    assert roles == {
        ContentRole.SAFETY,
        ContentRole.REPLACEMENT,
        ContentRole.VALIDATION,
    }
