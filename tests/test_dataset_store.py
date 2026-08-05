import pandas as pd
from sqlalchemy import inspect

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
