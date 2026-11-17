"""Last in, first out scheduling policy (non-preemptive)."""

from collections import deque


class LifoStrategy:
    """Newest waiting request first; never interrupt active reservations."""

    key = "lifo"
    label = "LIFO — newest waiting request first"

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        waiting.appendleft(resource_id)
