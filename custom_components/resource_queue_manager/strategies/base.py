"""Public contract for pure-Python queue scheduling strategies."""

from collections import deque
from typing import Protocol


class QueueStrategy(Protocol):
    """Choose the next-grant order without controlling Home Assistant entities."""

    key: str
    label: str

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        """Insert a pending resource in next-grant order."""
