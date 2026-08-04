from dataclasses import dataclass
from typing import Any


@dataclass
class AppState:
    pipeline: Any
    registry: Any
    index: Any
    df: Any
    session_factory: Any = None
