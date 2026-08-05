import pandas as pd
from app.data.loader import FEATURE_COLUMNS, load_dataset


def _fixture(tmp_path):
    rows = [
        {"id": 1, "created_at": "2026-06-01T10:00:00+00:00", "fault": "rolamento_inner_2", "rpm": 1000.0},
        {"id": 2, "created_at": "2026-06-02T10:00:00+00:00", "fault": "normla_carga_3_3", "rpm": 1200.0},
    ]
    for r in rows:
        for c in FEATURE_COLUMNS:
            r.setdefault(c, 0.5)
    path = tmp_path / "mini.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    return str(path)


def test_load_dataset(tmp_path):
    df = load_dataset(_fixture(tmp_path))
    assert list(df["family"]) == ["rolamento_inner", "normal"]
    assert list(df["kind"]) == ["falha", "estado"]
    assert df["created_at"].dt.tz is not None
    assert len(FEATURE_COLUMNS) == 23
