"""Pluggable reservation order policies.

A strategy only determines where new waiting requests are placed. The queue
engine remains responsible for capacity, persistence and reservation safety.
Waiting entries are always stored in *grant order* for deterministic recovery.
"""

from collections import deque
from typing import Protocol


class QueueStrategy(Protocol):
    """Interface implemented by reservation scheduling policies."""

    key: str

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        """Insert a pending request in the order it should be granted."""


class FifoStrategy:
    """Oldest waiting request is granted first."""

    key = "fifo"

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        waiting.append(resource_id)


class LifoStrategy:
    """Most recently queued request is granted first (no preemption)."""

    key = "lifo"

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        waiting.appendleft(resource_id)


STRATEGIES: dict[str, QueueStrategy] = {
    "fifo": FifoStrategy(),
    "lifo": LifoStrategy(),
}
DEFAULT_STRATEGY = "fifo"


def get_strategy(key: str) -> QueueStrategy:
    """Get a registered strategy, rejecting unsupported policy identifiers."""
    try:
        return STRATEGIES[key]
    except (KeyError, TypeError) as err:
        raise ValueError(f"Unsupported queue strategy: {key!r}") from err
