"""FIFO policy; no Home Assistant dependency."""

from collections import deque
from collections.abc import Mapping

from ..request import QueueRequest


class FifoStrategy:
    """Oldest request is granted first."""

    key = "fifo"
    label = "FIFO — oldest request first"

    def enqueue(
        self,
        waiting: deque[str],
        request: QueueRequest,
        requests: Mapping[str, QueueRequest],
    ) -> None:
        waiting.append(request.resource_id)
