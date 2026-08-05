import pandas as pd
from app.similarity.stats import occurrence_stats

def test_occurrence_stats():
    df = pd.DataFrame({
        "family": ["correia", "correia", "correia", "normal"],
        "created_at": pd.to_datetime([
            "2026-06-01T10:00:00Z", "2026-06-01T12:00:00Z",
            "2026-06-03T10:00:00Z", "2026-06-02T10:00:00Z"]),
    })
    s = occurrence_stats(df, "correia")
    assert s.total == 3
    assert s.per_day == {"2026-06-01": 2, "2026-06-03": 1}
    assert s.first_seen.startswith("2026-06-01")
    assert s.last_seen.startswith("2026-06-03")
    assert s.freq_per_day == 1.0  # 3 ocorrencias / 3 dias de janela
