"""FIFO policy; no Home Assistant dependency."""

from collections import deque


class FifoStrategy:
    """Oldest request is granted first."""

    key = "fifo"
    label = "FIFO — oldest request first"

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        waiting.append(resource_id)
