"""Framework-agnostic contracts for strategy plugins.

Strategy providers declare configuration using simple Python data objects.
The Home Assistant adapter decides how to render them; plugin code never
imports or directly controls Home Assistant entities.
"""

from collections import deque
from collections.abc import Mapping

from .request import QueueRequest
from dataclasses import dataclass
from typing import Literal, Protocol


class QueueStrategy(Protocol):
    """Choose pending order; capacity and safety remain with the host engine."""

    key: str
    label: str

    def enqueue(
        self,
        waiting: deque[str],
        request: QueueRequest,
        requests: Mapping[str, QueueRequest],
    ) -> None:
        """Insert a request; lookup exposes metadata of existing waiters."""


@dataclass(frozen=True, slots=True)
class StrategyConfigField:
    """Declarative, JSON-compatible strategy option for a native HA selector."""

    key: str
    label: str
    kind: Literal["text", "number", "boolean", "select"]
    required: bool = False
    default: str | int | float | bool | None = None
    description: str = ""
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None


class StrategyProvider(Protocol):
    """One registered plugin, analogous to a Laravel service provider."""

    key: str
    label: str
    description: str
    config_fields: tuple[StrategyConfigField, ...]
    request_fields: tuple[StrategyConfigField, ...]

    def create(
        self, config: Mapping[str, object] | None = None
    ) -> QueueStrategy:
        """Create an isolated policy instance with validated settings."""
