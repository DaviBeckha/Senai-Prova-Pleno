import datetime
import pandas as pd
from app.data.loader import FEATURE_COLUMNS
from app.similarity.engine import SimilarityEngine

def _df():
    rows = []
    for i in range(30):  # cluster A: valores baixos → rolamento_inner
        r = {c: 0.1 for c in FEATURE_COLUMNS}
        r.update(id=i, family="rolamento_inner", kind="falha")
        rows.append(r)
    for i in range(30, 60):  # cluster B: valores altos → normal
        r = {c: 5.0 for c in FEATURE_COLUMNS}
        r.update(id=i, family="normal", kind="estado")
        rows.append(r)
    return pd.DataFrame(rows)

def test_query_dominant_and_deterministic():
    eng = SimilarityEngine()
    eng.fit(_df())
    event = {c: 0.12 for c in FEATURE_COLUMNS}
    r1 = eng.query(event, k=10)
    r2 = eng.query(event, k=10)
    assert r1.dominant_family == "rolamento_inner"
    assert r1.dominant_kind == "falha"
    assert r1.neighbor_ids == r2.neighbor_ids
    assert r1.family_votes["rolamento_inner"] == 10


def test_fit_with_heterogeneous_types():
    """Test fit() handles mixed types: float/str/datetime in same column."""
    rows = []
    for i in range(15):
        r = {c: 0.1 for c in FEATURE_COLUMNS}
        r.update(id=i, family="rolamento_inner", kind="falha")
        rows.append(r)
    for i in range(15, 30):
        r = {c: 5.0 for c in FEATURE_COLUMNS}
        r.update(id=i, family="normal", kind="estado")
        rows.append(r)
    df = pd.DataFrame(rows)

    # Convert first feature column to object dtype to support mixed types
    df[FEATURE_COLUMNS[0]] = df[FEATURE_COLUMNS[0]].astype(object)

    # Inject heterogeneous types: strings, datetime, floats in same column
    df.loc[0, FEATURE_COLUMNS[0]] = "0.1"  # string
    df.loc[1, FEATURE_COLUMNS[0]] = datetime.datetime(2293, 1, 1)  # datetime
    df.loc[2, FEATURE_COLUMNS[0]] = 0.15  # float

    # Should fit without error despite mixed types
    eng = SimilarityEngine()
    eng.fit(df)
    assert eng._nn is not None


def test_query_with_datetime_value():
    """Test query() handles datetime values in event dict and determinism with heterogeneous types."""
    eng = SimilarityEngine()
    eng.fit(_df())

    # Create event with a datetime value (simulates raw data extraction)
    event = {c: 0.12 for c in FEATURE_COLUMNS}
    event[FEATURE_COLUMNS[0]] = datetime.datetime(2293, 1, 1)

    # Should not raise TypeError; should return valid result
    r1 = eng.query(event, k=10)
    r2 = eng.query(event, k=10)

    assert isinstance(r1.neighbor_ids, list)
    assert len(r1.neighbor_ids) > 0
    assert r1.dominant_family in ["rolamento_inner", "normal"]

    # Verify determinism: same event with datetime should produce identical results
    assert r1.neighbor_ids == r2.neighbor_ids
    assert r1.dominant_family == r2.dominant_family
