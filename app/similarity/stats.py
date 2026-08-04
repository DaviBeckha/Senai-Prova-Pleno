from dataclasses import dataclass

import pandas as pd


@dataclass
class OccurrenceStats:
    total: int
    first_seen: str
    last_seen: str
    per_day: dict[str, int]
    freq_per_day: float


def occurrence_stats(df: pd.DataFrame, family: str) -> OccurrenceStats:
    sub = df[df["family"] == family]
    if sub.empty:
        return OccurrenceStats(0, "", "", {}, 0.0)
    dates = sub["created_at"].dt.strftime("%Y-%m-%d")
    per_day = dates.value_counts().sort_index().to_dict()
    first, last = sub["created_at"].min(), sub["created_at"].max()
    window_days = max((last - first).days + 1, 1)
    return OccurrenceStats(
        total=int(len(sub)),
        first_seen=first.isoformat(),
        last_seen=last.isoformat(),
        per_day={k: int(v) for k, v in per_day.items()},
        freq_per_day=round(len(sub) / window_days, 2),
    )
