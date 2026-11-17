"""Non-preemptive priority FIFO policy.

A larger numeric priority is served first by default. Ties preserve FIFO
arrival order. New requests never interrupt existing active reservations.
"""

from collections import deque
from collections.abc import Mapping

from ..request import QueueRequest


class PriorityFifoStrategy:
    """Sort waiting requests by priority and arrival order."""

    key = "priority_fifo"
    label = "FIFO with priority"

    def __init__(self, priority_order: str = "highest_first") -> None:
        if priority_order not in ("highest_first", "lowest_first"):
            raise ValueError("Invalid priority order")
        self.priority_order = priority_order

    def enqueue(
        self,
        waiting: deque[str],
        request: QueueRequest,
        requests: Mapping[str, QueueRequest],
    ) -> None:
        """Insert ahead of strictly lower-ranked requests; keep FIFO ties."""
        new_priority = request.data["priority"]
        for index, queued_id in enumerate(waiting):
            queued_priority = requests[queued_id].data["priority"]
            outranks = (
                new_priority > queued_priority
                if self.priority_order == "highest_first"
                else new_priority < queued_priority
            )
            if outranks:
                waiting.insert(index, request.resource_id)
                break
        else:
            waiting.append(request.resource_id)
