"""Isolamento e relevancia por familia no indice vetorial.

As 4 familias `rolamento_*` (outer/inner/ball/combination) sao ingeridas do
MESMO arquivo `docs_fontes/doc1_rolamentos.md` (ver app/rag/family_sections.py).
Sem o filtro de secao por familia, `rolamento_inner` indexaria tambem o
diagnostico de outras falhas de rolamento (pista externa, elementos rolantes,
gaiola) e o modelo poderia citar a frequencia caracteristica errada com
aparencia de fundamentacao.

Embedder: fake determinista (mesmo padrao de tests/test_rag.py), NAO o e5
real. Medido localmente: import + load() do EmbeddingService com
intfloat/multilingual-e5-base (modelo ja em cache local) levou ~47s so no
load(), muito acima do limite de 10s para esta suite. As features do fake
contam os bigramas "pista interna" e "pista externa" (case-insensitive), que
aparecem no doc1 em mais de uma secao — inclusive na secao 11
("Frequencias Caracteristicas dos Rolamentos"), comum as duas familias, que
menciona ambos os bigramas uma vez cada. O que garante a secao 12/13 no topo
NAO e exclusividade de vocabulario, e sim a MARGEM de score: medido via
_INDEX.search, a consulta "defeito na pista interna" sob rolamento_inner
produz 13.=1.0, 4.2.=0.9487, 11.=0.8165, e o restante (secoes comuns sem o
bigrama) em 0.7071 — o mesmo padrao se repete, com os papeis trocados, para
"defeito na pista externa" sob rolamento_outer (12.=1.0, 4.1.=0.9487,
11.=0.8165). A secao-alvo sempre vence porque e a UNICA cujo vetor e copia
escalar exata do vetor da consulta (mesma proporcao entre as 4 features);
qualquer outra secao com o bigrama mas texto adicional (4.1/4.2) ou com os
dois bigramas ao mesmo tempo (11.) tem cosseno estritamente menor.
"""

from pathlib import Path

from app.rag.index import VectorIndex
from app.rag.ingest import ingest_pdf

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOC1_PATH = str(_REPO_ROOT / "docs_fontes" / "doc1_rolamentos.md")
_DOC4_PATH = str(_REPO_ROOT / "Doc4.pdf")


class FakeEmbedder:
    """Embedder deterministico por contagem de palavras-chave.

    dim=4: contagem de "pista interna", contagem de "pista externa", contagem
    de "correia" e um termo constante (evita vetor nulo e mantem o padrao de
    tests/test_rag.py). Tudo em minusculas para nao depender de capitalizacao.
    """

    dim = 4

    def embed(self, texts: list[str], type_: str) -> list[list[float]]:
        out = []
        for t in texts:
            low = t.lower()
            v = [
                float(low.count("pista interna")),
                float(low.count("pista externa")),
                float(low.count("correia")),
                1.0,
            ]
            norm = sum(x * x for x in v) ** 0.5
            out.append([x / norm for x in v])
        return out


def _build_index() -> VectorIndex:
    idx = VectorIndex(FakeEmbedder())
    ingest_pdf(_DOC1_PATH, "rolamento_inner", idx)
    ingest_pdf(_DOC1_PATH, "rolamento_outer", idx)
    ingest_pdf(_DOC4_PATH, "correia", idx)
    return idx


# Indice compartilhado entre os testes deste modulo: ingestao (leitura de
# arquivo + chunking + embedding fake) e determinista e independente entre
# os testes, so custa tempo repeti-la sem necessidade.
_INDEX = _build_index()


def test_busca_pista_interna_traz_secao_13_da_familia_rolamento_inner():
    hits = _INDEX.search("defeito na pista interna", doc_family="rolamento_inner", k=4)
    secoes = [hit.chunk.section for hit in hits]
    assert any(secao.startswith("13.") for secao in secoes), secoes


def test_busca_pista_externa_traz_secao_12_da_familia_rolamento_outer():
    hits = _INDEX.search("defeito na pista externa", doc_family="rolamento_outer", k=4)
    secoes = [hit.chunk.section for hit in hits]
    assert any(secao.startswith("12.") for secao in secoes), secoes


def test_familia_correia_jamais_retorna_chunk_do_doc1_rolamentos():
    hits = _INDEX.search("ajustar tensao da correia frouxa", doc_family="correia", k=10)
    assert hits, "busca sob familia correia nao retornou nenhum chunk"
    fontes = {hit.chunk.source for hit in hits}
    assert "doc1_rolamentos.md" not in fontes
    assert all(hit.chunk.doc_family == "correia" for hit in hits)


def test_familia_rolamento_inner_nao_indexa_diagnostico_de_outros_subtipos():
    # Isolamento estrutural (nao depende do embedder nem de scores): a secao
    # 12 (pista externa), 14 (elementos rolantes) e 15 (gaiola) nao podem
    # estar presentes nos chunks da familia rolamento_inner — ver
    # app/rag/family_sections.py, _BEARING_PREFIXES["rolamento_inner"].
    chunks = _INDEX.chunks_for_family("rolamento_inner")
    secoes = [c.section for c in chunks]
    assert not any(secao.startswith(("12.", "14.", "15.")) for secao in secoes), secoes
    assert any(secao.startswith("13.") for secao in secoes), secoes


def test_familia_rolamento_outer_nao_indexa_diagnostico_de_outros_subtipos():
    chunks = _INDEX.chunks_for_family("rolamento_outer")
    secoes = [c.section for c in chunks]
    assert not any(secao.startswith(("13.", "14.", "15.")) for secao in secoes), secoes
    assert any(secao.startswith("12.") for secao in secoes), secoes
