import numpy as np
import pandas as pd
from sqlalchemy import func, select

from app.data.db import make_session_factory
from app.data.loader import FEATURE_COLUMNS
from app.data.models import Base


def _factory():
    factory = make_session_factory("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def test_sensor_reading_table_has_expected_columns():
    from app.data.models import SensorReading

    cols = {c.name: c for c in SensorReading.__table__.columns}
    assert SensorReading.__tablename__ == "sensor_readings"
    for feature in FEATURE_COLUMNS:
        assert feature in cols, f"feature ausente: {feature}"
        assert cols[feature].nullable, f"feature deve ser nullable: {feature}"
    assert cols["family"].index
    assert not cols["created_at"].nullable
    assert cols["external_id"].nullable


def _mini_xlsx(tmp_path, n_inner=3, n_normal=2):
    rows = []
    for i in range(n_inner):
        rows.append({"id": i + 1, "created_at": f"2026-06-0{i+1}T10:00:00+00:00",
                     "fault": "rolamento_inner_2", "rpm": 1000.0 + i})
    for i in range(n_normal):
        rows.append({"id": 100 + i, "created_at": f"2026-06-1{i}T10:00:00+00:00",
                     "fault": "normal_carga_1", "rpm": 900.0})
    for r in rows:
        for c in FEATURE_COLUMNS:
            r.setdefault(c, 0.5)
    rows[0]["z_kurtosis"] = np.nan  # NaN precisa virar NULL no banco
    path = tmp_path / "mini.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    return str(path)


def test_seed_if_empty_inserts_once(tmp_path):
    from app.data.dataset_store import seed_if_empty
    from app.data.models import SensorReading

    factory = _factory()
    path = _mini_xlsx(tmp_path)
    assert seed_if_empty(factory, path) == 5
    assert seed_if_empty(factory, path) == 0  # idempotente: segunda chamada nao duplica
    with factory() as session:
        total = session.scalar(select(func.count()).select_from(SensorReading))
        assert total == 5
        null_kurtosis = session.scalar(
            select(func.count()).select_from(SensorReading)
            .where(SensorReading.z_kurtosis.is_(None)))
        assert null_kurtosis == 1
        families = set(session.scalars(select(SensorReading.family)))
        assert families == {"rolamento_inner", "normal"}


def test_seed_if_empty_missing_xlsx_raises_clear_error(tmp_path):
    import pytest
    from app.data.dataset_store import seed_if_empty

    factory = _factory()
    with pytest.raises(FileNotFoundError, match="sensor_readings"):
        seed_if_empty(factory, str(tmp_path / "nao_existe.xlsx"))


def test_seed_if_empty_multiple_chunks_single_transaction(tmp_path, monkeypatch):
    from app.data import dataset_store
    from app.data.models import SensorReading

    monkeypatch.setattr(dataset_store, "_CHUNK", 2)
    factory = _factory()
    path = _mini_xlsx(tmp_path, n_inner=4, n_normal=3)  # 7 linhas -> 4 lotes de _CHUNK=2
    assert dataset_store.seed_if_empty(factory, path) == 7
    assert dataset_store.seed_if_empty(factory, path) == 0  # idempotente: segunda chamada nao duplica
    with factory() as session:
        total = session.scalar(select(func.count()).select_from(SensorReading))
        assert total == 7


def test_load_from_db_round_trip_matches_loader_contract(tmp_path):
    from app.data.dataset_store import load_from_db, seed_if_empty
    from app.data.loader import load_dataset

    factory = _factory()
    path = _mini_xlsx(tmp_path)
    seed_if_empty(factory, path)
    df_db = load_from_db(factory)
    df_xlsx = load_dataset(path)

    assert set(df_db.columns) >= {"id", "created_at", "fault", "family", "kind", *FEATURE_COLUMNS}
    assert "external_id" not in df_db.columns
    assert sorted(df_db["id"]) == sorted(df_xlsx["id"])  # id = id original do xlsx
    assert df_db["created_at"].dt.tz is not None  # tz-aware UTC
    assert df_db["family"].value_counts().to_dict() == df_xlsx["family"].value_counts().to_dict()
    assert df_db["z_kurtosis"].isna().sum() == 1  # NULL voltou como NaN


def test_load_from_db_empty_table_raises_clear_error():
    import pytest
    from app.data.dataset_store import load_from_db

    factory = _factory()
    with pytest.raises(RuntimeError, match="sensor_readings"):
        load_from_db(factory)


def test_occurrence_stats_equivalent_between_sources(tmp_path):
    from app.data.dataset_store import load_from_db, seed_if_empty
    from app.data.loader import load_dataset
    from app.similarity.stats import occurrence_stats

    factory = _factory()
    path = _mini_xlsx(tmp_path)
    seed_if_empty(factory, path)
    stats_db = occurrence_stats(load_from_db(factory), "rolamento_inner")
    stats_xlsx = occurrence_stats(load_dataset(path), "rolamento_inner")
    assert stats_db == stats_xlsx


def test_ensure_dataset_end_to_end(tmp_path):
    from app.data.dataset_store import ensure_dataset

    factory = _factory()
    df = ensure_dataset(factory, _mini_xlsx(tmp_path))
    assert len(df) == 5
    # segunda chamada: sem xlsx no caminho, direto do banco
    df2 = ensure_dataset(factory, str(tmp_path / "sumiu.xlsx"))
    assert len(df2) == 5
