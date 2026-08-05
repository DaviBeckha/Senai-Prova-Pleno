from app.rag.chunking import chunk_text
from app.rag.chunking import chunk_file
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
