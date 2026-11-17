"""LIFO policy; does not preempt active reservations."""

from collections import deque


class LifoStrategy:
    """Most recently queued waiting request is granted first."""

    key = "lifo"
    label = "LIFO — newest waiting request first"

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        waiting.appendleft(resource_id)
