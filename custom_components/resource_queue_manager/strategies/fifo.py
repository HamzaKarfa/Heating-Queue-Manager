"""First in, first out scheduling policy."""

from collections import deque


class FifoStrategy:
    """Grant requests in their arrival order."""

    key = "fifo"
    label = "FIFO — oldest request first"

    def enqueue(self, waiting: deque[str], resource_id: str) -> None:
        waiting.append(resource_id)
