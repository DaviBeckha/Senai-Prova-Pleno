from app.data.db import make_session_factory
from app.data.models import Base
from app.data.registry import DocumentRegistry


def _registry():
    factory = make_session_factory("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(factory.kw["bind"])
    return DocumentRegistry(factory)


def test_seed_and_lookup():
    reg = _registry()
    reg.seed_defaults()
    assert reg.has_document("rolamento_inner")
    assert reg.has_document("cocked_rotor")
    assert not reg.has_document("ventoinha")
    assert not reg.has_document("eccentric_rotor")


def test_register_new_document_unlocks_family():
    reg = _registry()
    reg.seed_defaults()
    reg.register("ventoinha", "Procedimento Ventoinha", "docs_novos/ventoinha.pdf")
    assert reg.has_document("ventoinha")


def test_register_duplicate_family_and_title_raises_valueerror():
    reg = _registry()
    reg.register("ventoinha", "Proc X", "docs_novos/proc_x.pdf")
    try:
        reg.register("ventoinha", "Proc X", "docs_novos/proc_x_v2.pdf")
        assert False, "esperava ValueError"
    except ValueError as exc:
        assert "já existe documento com este título para esta família" in str(exc)


def test_register_same_family_different_title_is_allowed():
    reg = _registry()
    reg.register("ventoinha", "Proc X", "docs_novos/proc_x.pdf")
    reg.register("ventoinha", "Proc Y", "docs_novos/proc_y.pdf")
    assert reg.has_document("ventoinha")
