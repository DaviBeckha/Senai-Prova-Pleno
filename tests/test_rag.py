from pathlib import Path

from app.rag.chunking import chunk_file, chunk_pdf, chunk_text
from app.rag.index import VectorIndex
from app.rag.chunking import Chunk

class FakeEmbedder:
    dim = 4
    def embed(self, texts, type_):
        # vetor deterministico: conta de palavras-chave, normalizado a mao
        out = []
        for t in texts:
            v = [float(t.count("graxa")), float(t.count("correia")),
                 float(t.count("polia")), 1.0]
            norm = sum(x * x for x in v) ** 0.5
            out.append([x / norm for x in v])
        return out

def test_chunk_text_splits_by_section():
    text = "1. Objetivo\nTexto A\n2. Sintomas\nTexto B com graxa"
    chunks = chunk_text(text, doc_family="correia", source="Doc4")
    assert len(chunks) == 2
    assert chunks[1].section.startswith("2.")

def test_index_search_filters_by_family():
    idx = VectorIndex(FakeEmbedder())
    idx.add([
        Chunk("correia", "Doc4", "9.1", "ajustar tensao da correia"),
        Chunk("polia", "Doc5", "8", "verificar excentricidade da polia"),
    ])
    hits = idx.search("correia frouxa", doc_family="correia", k=2)
    assert len(hits) == 1
    # Contrato atual: SearchHit expoe doc_family via hit.chunk.doc_family,
    # nao como atributo direto do hit (app/rag/search.py: SearchHit tem
    # apenas chunk/score).
    assert hits[0].chunk.doc_family == "correia"

def test_chunk_text_fallback_pula_texto_so_whitespace():
    # PDF escaneado: PdfReader.extract_text() sem camada de texto extraivel
    # devolve "" por pagina; "\n".join(paginas) produz um texto so com
    # quebras de linha — sem secoes numeradas, cai no fallback por tamanho
    # fixo (max_chars). Esse fallback nao pode gerar chunk de puro whitespace
    # (evidencia-lixo que antes fazia a familia parecer "documentada" sem
    # conteudo real).
    text = "\n\n   \n\t\n"
    chunks = chunk_text(text, doc_family="rolamento_outer", source="Doc1")
    assert chunks == []


def test_chunk_text_fallback_mantem_conteudo_real_sem_secoes():
    # Contra-teste: texto real sem numeracao de secao continua indo pelo
    # fallback e gerando chunks normalmente — a mudanca so descarta
    # segmentos 100% whitespace, nao pode afetar conteudo com texto de fato.
    text = "Texto solto sem numeracao de secao, com conteudo relevante sobre correias."
    chunks = chunk_text(text, doc_family="correia", source="Doc4")
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_chunk_file_dispatches_markdown_by_extension(tmp_path):
    md_path = tmp_path / "doc1_rolamentos.md"
    md_path.write_text(
        "1. Objetivo\nTexto A sobre rolamentos\n2. Sintomas\nTexto B com graxa",
        encoding="utf-8",
    )
    chunks = chunk_file(str(md_path), doc_family="rolamento_inner")
    assert len(chunks) == 2
    assert chunks[0].section.startswith("1.")
    assert chunks[1].section.startswith("2.")
    assert all(c.doc_family == "rolamento_inner" for c in chunks)


def test_passos_numerados_permanecem_com_o_subtitulo_pai():
    text = """9. Verificação da Tensão
9.1 Correia Frouxa
Correção
1. Afrouxar os parafusos do motor.
2. Ajustar a posição do motor.
3. Aplicar a tensão recomendada.
4. Reapertar os parafusos.
5. Validar novamente.
10. Verificação do Alinhamento
Conteúdo seguinte.
"""

    chunks = chunk_text(text, doc_family="correia", source="Doc4.pdf")

    loose = next(chunk for chunk in chunks if chunk.section.startswith("9.1"))
    assert "1. Afrouxar" in loose.text
    assert "5. Validar" in loose.text
    assert not any(chunk.section.startswith("1. Afrouxar") for chunk in chunks)


def test_medidas_de_seguranca_formam_um_bloco_coerente():
    text = """7. Segurança
Antes de iniciar:
1. Desligar o equipamento.
2. Aplicar bloqueio e etiquetagem.
3. Confirmar ausência de energia.
4. Aguardar parada completa.
8. Inspeção Visual
Verificar correia.
"""

    chunks = chunk_text(text, doc_family="correia", source="Doc4.pdf")

    safety = next(chunk for chunk in chunks if chunk.content_role == "safety")
    assert "Desligar" in safety.text
    assert "parada completa" in safety.text
    assert safety.section_path == ("7. Segurança",)


def test_doc4_real_nao_indexa_passos_de_ajuste_como_secoes_isoladas():
    doc4 = Path(__file__).resolve().parents[1] / "Doc4.pdf"

    chunks = chunk_pdf(str(doc4), doc_family="correia")

    loose = next(chunk for chunk in chunks if chunk.section.startswith("9.1"))
    safety = next(chunk for chunk in chunks if chunk.section.startswith("7."))
    replacement = next(chunk for chunk in chunks if chunk.section.startswith("14."))
    assert "Aplicar a tensão recomendada" in loose.text
    assert "Confirmar ausência de energia" in safety.text
    assert "Remover a correia antiga" in replacement.text
    assert not any(chunk.section.startswith("2. Remover") for chunk in chunks)


def test_bloco_longo_preserva_contexto_pai_em_todas_as_partes():
    text = (
        "9.1 Correia Frouxa\n"
        "Primeiro parágrafo com instruções de ajuste e reaperto.\n\n"
        "Segundo parágrafo com aplicação da tensão recomendada.\n\n"
        "Terceiro parágrafo com validação da estabilidade final."
    )

    chunks = chunk_text(
        text,
        doc_family="correia",
        source="Doc4.pdf",
        max_chars=100,
    )

    assert len(chunks) > 1
    assert all(chunk.section_path == ("9.1 Correia Frouxa",) for chunk in chunks)
    assert all("9.1 Correia Frouxa" in chunk.text for chunk in chunks)
    assert "validação da estabilidade final" in " ".join(
        chunk.text for chunk in chunks
    )
