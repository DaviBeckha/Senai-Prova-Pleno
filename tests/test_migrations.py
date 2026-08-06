"""Testes de integridade das migrations do Alembic.

Aplica `alembic upgrade head` de verdade contra um SQLite de ARQUIVO
temporario (nao ":memory:", que nao sobrevive a reconexao) e confere, via
`sqlalchemy.inspect`, que os artefatos de schema esperados (foreign key,
unique constraint) realmente existem apos a migracao — em vez de confiar
apenas no autogenerate/model.
"""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(url: str) -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def _tem_fk_diagnoses_e_uq_documents(url: str) -> tuple[bool, bool]:
    engine = create_engine(url, future=True)
    try:
        fks = inspect(engine).get_foreign_keys("diagnoses")
        uqs = inspect(engine).get_unique_constraints("documents")
    finally:
        engine.dispose()
    tem_fk = any(fk["referred_table"] == "events" for fk in fks)
    tem_uq = any(set(uq["column_names"]) == {"family", "title"} for uq in uqs)
    return tem_fk, tem_uq


def test_alembic_upgrade_head_cria_fk_diagnoses_event_id(tmp_path, monkeypatch):
    db_path = tmp_path / "migra_fk.db"
    url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(url), "head")

        engine = create_engine(url, future=True)
        try:
            fks = inspect(engine).get_foreign_keys("diagnoses")
        finally:
            engine.dispose()

        assert any(
            fk["referred_table"] == "events" and fk["constrained_columns"] == ["event_id"]
            for fk in fks
        )
    finally:
        get_settings.cache_clear()


def test_diagnosis_com_event_id_inexistente_falha_com_pragma_fk_on(tmp_path, monkeypatch):
    # No Postgres a FK vale sempre; aqui simulamos a aplicacao com o pragma
    # de FK do SQLite (desligado por padrao nesse dialeto).
    db_path = tmp_path / "migra_fk_pragma.db"
    url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(url), "head")

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                conn.execute(
                    "INSERT INTO diagnoses (event_id, created_at, status, family, message) "
                    "VALUES (9999, '2026-01-01T00:00:00', 'diagnostico', 'correia', 'msg')"
                )
                conn.commit()
                assert False, "esperava falha de foreign key"
            except sqlite3.IntegrityError:
                pass
        finally:
            conn.close()
    finally:
        get_settings.cache_clear()


def test_alembic_upgrade_incremental_a_partir_de_banco_com_migrations_antigas(tmp_path, monkeypatch):
    # Simula o banco do Davi: ja tem 0001+0002 aplicadas (dados legados) —
    # `alembic upgrade head` precisa continuar dai sem erro, e nao exigir um
    # banco totalmente novo.
    db_path = tmp_path / "migra_incremental.db"
    url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = _alembic_config(url)
        command.upgrade(cfg, "0002")
        command.upgrade(cfg, "head")

        engine = create_engine(url, future=True)
        try:
            tables = inspect(engine).get_table_names()
        finally:
            engine.dispose()
        assert {"events", "diagnoses", "documents", "sensor_readings"}.issubset(tables)
    finally:
        get_settings.cache_clear()


def test_migration_remove_diagnoses_orfaos_legados_antes_de_criar_fk(tmp_path, monkeypatch):
    # Dado um banco com 0001+0002 aplicadas e um diagnostico orfao (bug do
    # duplo commit antigo — Event nunca chegou a existir), a migration da FK
    # precisa limpar o orfao ANTES de criar a constraint, senao ela falharia
    # ao ser criada num banco com dados inconsistentes.
    db_path = tmp_path / "migra_orfao.db"
    url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = _alembic_config(url)
        command.upgrade(cfg, "0002")

        conn = sqlite3.connect(str(db_path))
        try:
            # Evento + diagnostico validos (devem sobreviver).
            conn.execute(
                "INSERT INTO events (id, external_id, created_at, payload, family, kind) "
                "VALUES (1, NULL, '2026-01-01T00:00:00', '{}', 'correia', 'falha')"
            )
            conn.execute(
                "INSERT INTO diagnoses (event_id, created_at, status, family, message) "
                "VALUES (1, '2026-01-01T00:00:00', 'diagnostico', 'correia', 'msg valido')"
            )
            # Diagnostico orfao: event_id sem Event correspondente.
            conn.execute(
                "INSERT INTO diagnoses (event_id, created_at, status, family, message) "
                "VALUES (9999, '2026-01-01T00:00:00', 'diagnostico', 'correia', 'msg orfao')"
            )
            conn.commit()
        finally:
            conn.close()

        command.upgrade(cfg, "head")

        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("SELECT event_id, message FROM diagnoses").fetchall()
        finally:
            conn.close()

        assert rows == [(1, "msg valido")]
    finally:
        get_settings.cache_clear()


def test_alembic_upgrade_head_cria_unique_constraint_documents_family_title(tmp_path, monkeypatch):
    db_path = tmp_path / "migra_uq.db"
    url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(url), "head")

        engine = create_engine(url, future=True)
        try:
            uqs = inspect(engine).get_unique_constraints("documents")
        finally:
            engine.dispose()

        assert any(
            set(uq["column_names"]) == {"family", "title"} for uq in uqs
        )
    finally:
        get_settings.cache_clear()


def test_documents_com_family_title_exatos_duplicados_falha_apos_migration(tmp_path, monkeypatch):
    db_path = tmp_path / "migra_uq_insert.db"
    url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(url), "head")

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO documents (family, title, source_path, created_at) "
                "VALUES ('correia', 'Doc Correia', 'x.pdf', '2026-01-01T00:00:00')"
            )
            conn.commit()
            try:
                conn.execute(
                    "INSERT INTO documents (family, title, source_path, created_at) "
                    "VALUES ('correia', 'Doc Correia', 'y.pdf', '2026-01-02T00:00:00')"
                )
                conn.commit()
                assert False, "esperava falha de unique constraint"
            except sqlite3.IntegrityError:
                pass
        finally:
            conn.close()
    finally:
        get_settings.cache_clear()


def test_migration_dedup_documents_legados_mantem_linha_mais_antiga(tmp_path, monkeypatch):
    # Antes da constraint existir, o banco pode ter duplicatas exatas
    # (family+title identicos) da race select-then-insert do register()
    # antigo. A migration precisa deduplicar ANTES de criar a constraint,
    # mantendo a linha mais antiga (menor id / primeira inserida).
    db_path = tmp_path / "migra_uq_dedup.db"
    url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = _alembic_config(url)
        command.upgrade(cfg, "0003")

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO documents (id, family, title, source_path, created_at) "
                "VALUES (1, 'correia', 'Doc Correia', 'antigo.pdf', '2026-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO documents (id, family, title, source_path, created_at) "
                "VALUES (2, 'correia', 'Doc Correia', 'duplicado.pdf', '2026-01-02T00:00:00')"
            )
            # Titulo com case diferente NAO e duplicata exata (constraint e
            # case-sensitive) -- deve sobreviver a dedup da migration.
            conn.execute(
                "INSERT INTO documents (id, family, title, source_path, created_at) "
                "VALUES (3, 'correia', 'doc correia', 'case-diferente.pdf', '2026-01-03T00:00:00')"
            )
            conn.commit()
        finally:
            conn.close()

        command.upgrade(cfg, "head")

        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT id, title, source_path FROM documents ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        assert rows == [
            (1, "Doc Correia", "antigo.pdf"),
            (3, "doc correia", "case-diferente.pdf"),
        ]
    finally:
        get_settings.cache_clear()


def test_alembic_downgrade_remove_e_upgrade_restaura_fk_e_unique_constraint(tmp_path, monkeypatch):
    # drop_constraint em batch mode no SQLite (recreate da tabela) e o ponto
    # mais fragil das duas migrations novas -- so validado manualmente ate
    # aqui. Confere o ciclo completo: upgrade cria os dois artefatos,
    # downgrade para 0002 remove ambos, upgrade de volta para head restaura
    # os dois.
    db_path = tmp_path / "migra_downgrade.db"
    url = _sqlite_url(db_path)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        cfg = _alembic_config(url)

        command.upgrade(cfg, "head")
        assert _tem_fk_diagnoses_e_uq_documents(url) == (True, True)

        command.downgrade(cfg, "0002")
        assert _tem_fk_diagnoses_e_uq_documents(url) == (False, False)

        command.upgrade(cfg, "head")
        assert _tem_fk_diagnoses_e_uq_documents(url) == (True, True)
    finally:
        get_settings.cache_clear()
