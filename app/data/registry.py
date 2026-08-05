from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.data.models import Document

_SEED = {
    # Doc1.pdf e rasterizado (sem camada de texto extraivel); a ingestao RAG
    # real usa a transcricao docs_fontes/doc1_rolamentos.md (ver scripts/
    # bootstrap.py PDF_MAP) — source_path aqui alinhado ao caminho de
    # ingestao real. Titulo permanece "Doc1 - Rolamentos".
    "rolamento_inner": ("Doc1 - Rolamentos", "docs_fontes/doc1_rolamentos.md"),
    "rolamento_outer": ("Doc1 - Rolamentos", "docs_fontes/doc1_rolamentos.md"),
    "rolamento_ball": ("Doc1 - Rolamentos", "docs_fontes/doc1_rolamentos.md"),
    "rolamento_combination": ("Doc1 - Rolamentos", "docs_fontes/doc1_rolamentos.md"),
    "desalinhado": ("Doc2 - Desalinhamento", "Doc2.pdf"),
    "desbalanceado": ("Doc3 - Desbalanceamento", "Doc3.pdf"),
    "correia": ("Doc4 - Correias", "Doc4.pdf"),
    "polia": ("Doc5 - Polias", "Doc5.pdf"),
    "cocked_rotor": ("Doc6 - Cocked Rotor", "Doc6.pdf"),
}


class DocumentRegistry:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._factory = session_factory

    def seed_defaults(self) -> None:
        with self._factory() as session:
            for family, (title, path) in _SEED.items():
                exists = session.scalar(select(Document).where(Document.family == family))
                if not exists:
                    session.add(Document(family=family, title=title, source_path=path))
            session.commit()

    def has_document(self, family: str, title: str | None = None) -> bool:
        """Check if a document exists by family, or by family + normalized title.

        If title is provided, normalized (strip + lower) for comparison.
        If title is None, checks only by family (backward compat).
        """
        with self._factory() as session:
            if title is None:
                return session.scalar(select(Document).where(Document.family == family)) is not None
            normalized_title = title.strip().lower()
            return session.scalar(
                select(Document).where(
                    (Document.family == family)
                    & (func.lower(Document.title) == normalized_title)
                )
            ) is not None

    def register(self, family: str, title: str, source_path: str) -> None:
        normalized_title = title.strip()
        normalized_title_lower = normalized_title.lower()
        with self._factory() as session:
            try:
                existing = session.scalar(
                    select(Document).where(
                        (Document.family == family)
                        & (func.lower(Document.title) == normalized_title_lower)
                    )
                )
                if existing:
                    raise ValueError(
                        "já existe documento com este título para esta família"
                    )
                session.add(Document(family=family, title=normalized_title, source_path=source_path))
                session.commit()
            except ValueError:
                raise
            except Exception:
                raise

    def list_documents(self) -> list[Document]:
        with self._factory() as session:
            return list(session.scalars(select(Document)).all())
