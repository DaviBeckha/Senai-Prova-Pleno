class EmbeddingUnavailableError(RuntimeError):
    """Raised when the embedding model could not be loaded or has not been loaded yet."""


class EmbeddingService:
    """Wraps a sentence-transformers E5-family model behind a load()/embed() interface.

    The heavy dependency (sentence_transformers, which pulls in torch) is imported
    lazily inside load(), so this module can be imported — and instantiated — even
    in environments where sentence-transformers is not installed. Only calling
    load() (or embed() before load()) requires the dependency to be present.
    """

    def __init__(self, model_name: str, model_id: str, dim: int) -> None:
        self.model_name = model_name
        self.model_id = model_id
        self.dim = dim
        self._model = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingUnavailableError(
                f"sentence-transformers nao esta instalado; nao foi possivel carregar o modelo "
                f"'{self.model_name}' ({self.model_id})"
            ) from exc

        try:
            self._model = SentenceTransformer(self.model_id)
        except Exception as exc:
            raise EmbeddingUnavailableError(
                f"falha ao carregar o modelo de embeddings '{self.model_name}' ({self.model_id}): {exc}"
            ) from exc

    def embed(self, texts: list[str], type_: str) -> list[list[float]]:
        if type_ not in ("query", "passage"):
            raise ValueError(f"type_ deve ser 'query' ou 'passage', recebido: {type_!r}")
        if not self.ready:
            raise EmbeddingUnavailableError(
                f"EmbeddingService '{self.model_name}' nao foi carregado; chame load() antes de embed()"
            )

        prefixed = [f"{type_}: {t}" for t in texts]
        vectors = self._model.encode(prefixed, normalize_embeddings=True)
        return vectors.tolist()
