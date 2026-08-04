from sqlalchemy import select
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

    def has_document(self, family: str) -> bool:
        with self._factory() as session:
            return session.scalar(select(Document).where(Document.family == family)) is not None

    def register(self, family: str, title: str, source_path: str) -> None:
        with self._factory() as session:
            session.add(Document(family=family, title=title, source_path=source_path))
            session.commit()

    def list_documents(self) -> list[Document]:
        with self._factory() as session:
            return list(session.scalars(select(Document)).all())
