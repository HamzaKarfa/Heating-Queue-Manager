"""Framework-agnostic contracts for strategy plugins."""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol


class QueueStrategy(Protocol):
    """Scheduling policy; Home Assistant and persistence stay in the host."""

    key: str
    label: str

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        """Insert a pending resource in its next-grant position."""


@dataclass(frozen=True, slots=True)
class StrategyConfigField:
    """Declarative strategy-specific settings for a future HA options form.

    Form implementations should map these descriptors to Home Assistant
    selectors rather than importing Home Assistant from the core engine.
    """

    key: str
    label: str
    kind: Literal["text", "number", "boolean", "select"]
    required: bool = False
    default: str | int | float | bool | None = None
    description: str = ""


class StrategyProvider(Protocol):
    """Plugin entry point, analogous to a framework service provider."""

    key: str
    label: str
    description: str
    config_fields: tuple[StrategyConfigField, ...]

    def create(
        self, config: Mapping[str, object] | None = None
    ) -> QueueStrategy:
        """Build a policy instance for one independent resource queue."""
