import numpy as np

try:
    import faiss
except ImportError:  # ambiente de teste sem faiss
    faiss = None

from app.rag.chunking import Chunk


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

    def search(self, query: str, doc_family: str, k: int = 4) -> list[Chunk]:
        if doc_family not in self._indexes:
            return []
        vec = np.array(self._embedder.embed([query], "query"), dtype="float32")
        k = min(k, len(self._chunks[doc_family]))
        _, idx = self._indexes[doc_family].search(vec, k)
        return [self._chunks[doc_family][i] for i in idx[0] if i >= 0]


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
        scores = self._vecs @ vec[0]
        order = np.argsort(-scores)[:k]
        return scores[order][None, :], order[None, :]
