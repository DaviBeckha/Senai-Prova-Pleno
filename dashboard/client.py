"""Cliente HTTP pequeno e testável usado pela interface Streamlit."""

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any


@dataclass(frozen=True)
class TimedJsonResponse:
    payload: dict[str, Any]
    elapsed_seconds: float


def request_json(
    post: Callable[..., Any],
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    clock: Callable[[], float] = perf_counter,
) -> TimedJsonResponse:
    """Executa POST JSON, valida o HTTP e mede o tempo ponta a ponta."""
    started_at = clock()
    response = post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    elapsed = clock() - started_at
    return TimedJsonResponse(response.json(), elapsed)
