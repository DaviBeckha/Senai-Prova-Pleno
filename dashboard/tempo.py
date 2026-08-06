"""Medição testável do tempo de operações longas do dashboard."""

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ResultadoTemporizado(Generic[T]):
    valor: T
    elapsed_seconds: float


def medir(
    operacao: Callable[[], T],
    *,
    clock: Callable[[], float] = perf_counter,
) -> ResultadoTemporizado[T]:
    """Executa uma operação síncrona e mede seu tempo ponta a ponta."""
    inicio = clock()
    valor = operacao()
    return ResultadoTemporizado(valor, clock() - inicio)
