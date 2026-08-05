import numpy as np

try:
    import faiss
except ImportError:  # ambiente de teste sem faiss
    faiss = None

from app.rag.chunking import Chunk
from app.rag.search import SearchHit


class VectorIndex:
    def __init__(self, embedder) -> None:
        self._embedder = embedder
        self._indexes: dict[str, "faiss.IndexFlatIP"] = {}
        self._chunks: dict[str, list[Chunk]] = {}

    def add(self, chunks: list[Chunk]) -> None:
        by_family: dict[str, list[Chunk]] = {}
        for c in chunks:
            by_family.setdefault(c.doc_family, []).append(c)
        for family, items in by_family.items():
            vecs = np.array(
                self._embedder.embed([c.text for c in items], "passage"), dtype="float32")
            if family not in self._indexes:
                self._indexes[family] = _new_index(vecs.shape[1])
                self._chunks[family] = []
            self._indexes[family].add(vecs)
            self._chunks[family].extend(items)

    def search(
        self,
        query: str,
        doc_family: str,
        k: int = 4,
        min_score: float = 0.55,
    ) -> list[SearchHit]:
        """Trechos mais proximos da consulta, com o score que os justifica.

        Os embeddings sao normalizados (EmbeddingService.embed), entao o
        produto interno do IndexFlatIP e o cosseno — e `min_score` e um corte
        de similaridade comparavel entre consultas.
        """
        if doc_family not in self._indexes:
            return []
        vec = np.array(self._embedder.embed([query], "query"), dtype="float32")
        k = min(k, len(self._chunks[doc_family]))
        scores, indexes = self._indexes[doc_family].search(vec, k)
        hits = [
            SearchHit(self._chunks[doc_family][index], float(score))
            for score, index in zip(scores[0], indexes[0], strict=True)
            if index >= 0 and float(score) >= min_score
        ]
        return sorted(hits, key=lambda hit: hit.score, reverse=True)

    def chunks_for_family(self, doc_family: str) -> tuple[Chunk, ...]:
        """Todos os trechos da familia em ordem documental (nao por score)."""
        return tuple(self._chunks.get(doc_family, ()))


def _new_index(dim: int):
    if faiss is None:
        return _PyFallbackIndex(dim)
    return faiss.IndexFlatIP(dim)


class _PyFallbackIndex:
    """Busca por produto interno em numpy puro; usado quando faiss nao esta instalado."""

    def __init__(self, dim: int) -> None:
        self._vecs = np.empty((0, dim), dtype="float32")

    def add(self, vecs: np.ndarray) -> None:
        self._vecs = np.vstack([self._vecs, vecs])

    def search(self, vec: np.ndarray, k: int):
        if not len(self._vecs) or k <= 0:
            return (
                np.empty((1, 0), dtype="float32"),
                np.empty((1, 0), dtype="int64"),
            )
        scores = self._vecs @ vec[0]
        order = np.argsort(-scores)[:k]
        return scores[order][None, :], order[None, :]
