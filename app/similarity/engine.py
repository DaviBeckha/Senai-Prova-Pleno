from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

from app.data.loader import FEATURE_COLUMNS


@dataclass
class SimilarityResult:
    dominant_family: str
    dominant_kind: str
    neighbor_ids: list[int]
    family_votes: dict[str, int]
    candidate_families: tuple[str, ...] = ()
    top_vote_share: float = 0.0
    vote_margin: int = 0
    is_ambiguous: bool = False


class SimilarityEngine:
    def __init__(self) -> None:
        self._scaler = StandardScaler()
        self._imputer = SimpleImputer(strategy="mean")
        self._nn: NearestNeighbors | None = None
        self._meta: pd.DataFrame | None = None

    def fit(self, df: pd.DataFrame) -> None:
        # Convert feature columns to float, handling mixed types
        feature_data = df[FEATURE_COLUMNS].copy()
        for col in FEATURE_COLUMNS:
            feature_data[col] = pd.to_numeric(feature_data[col], errors='coerce')
        # Impute missing values
        x = self._imputer.fit_transform(feature_data.to_numpy())
        x = self._scaler.fit_transform(x)
        self._nn = NearestNeighbors(metric="euclidean").fit(x)
        self._meta = df[["id", "family", "kind"]].reset_index(drop=True)

    def query(self, event: dict, k: int = 50) -> SimilarityResult:
        if self._nn is None or self._meta is None or self._imputer is None:
            raise RuntimeError("SimilarityEngine.fit deve ser chamado antes de query")
        # Coerce event values to numeric, handling mixed types (datetime, str, int, float)
        vec_raw = []
        for c in FEATURE_COLUMNS:
            val = event[c]
            try:
                # Try direct float conversion first
                vec_raw.append(float(val))
            except (TypeError, ValueError):
                # Fall back to pd.to_numeric for mixed types (datetime, str, etc.)
                try:
                    numeric_val = pd.to_numeric(val, errors='coerce')
                    vec_raw.append(float(numeric_val) if not pd.isna(numeric_val) else np.nan)
                except (TypeError, ValueError):
                    # If all else fails, use NaN (will be imputed)
                    vec_raw.append(np.nan)

        vec = np.array([vec_raw])
        # Impute and scale using fitted transformers (transform, never fit_transform)
        vec = self._imputer.transform(vec)
        vec = self._scaler.transform(vec)
        _, idx = self._nn.kneighbors(vec, n_neighbors=min(k, len(self._meta)))
        rows = self._meta.iloc[idx[0]]
        votes = Counter(rows["family"])
        ranked_votes = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        dominant_family, top_votes = ranked_votes[0]
        second_votes = ranked_votes[1][1] if len(ranked_votes) > 1 else 0
        candidate_families = tuple(
            family
            for family, count in ranked_votes
            if count == top_votes
        )
        dominant_kind = rows[rows["family"] == dominant_family]["kind"].iloc[0]
        return SimilarityResult(
            dominant_family=dominant_family,
            dominant_kind=dominant_kind,
            neighbor_ids=[int(i) for i in rows["id"]],
            family_votes=dict(votes),
            candidate_families=candidate_families,
            top_vote_share=top_votes / len(rows),
            vote_margin=top_votes - second_votes,
            is_ambiguous=len(candidate_families) > 1,
        )
