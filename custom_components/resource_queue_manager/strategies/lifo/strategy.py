"""LIFO policy; does not preempt active reservations."""

from collections import deque
from collections.abc import Mapping

from ..request import QueueRequest


class LifoStrategy:
    """Most recently queued waiting request is granted first."""

    key = "lifo"
    label = "LIFO — newest waiting request first"

    def enqueue(
        self,
        waiting: deque[str],
        request: QueueRequest,
        requests: Mapping[str, QueueRequest],
    ) -> None:
        waiting.appendleft(request.resource_id)
