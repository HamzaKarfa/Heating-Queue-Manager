"""Pure-Python FIFO reservation engine. Never controls entities directly."""

from collections import deque
from dataclasses import dataclass

if __package__:
    from .strategies import DEFAULT_STRATEGY, get_strategy
else:  # Standalone pure-Python tests import fifo.py directly.
    from strategies import DEFAULT_STRATEGY, get_strategy


@dataclass(frozen=True, slots=True)
class QueueResult:
    """Snapshot after a transition and newly allocated reservations."""

    granted: tuple[str, ...]
    active: tuple[str, ...]
    waiting: tuple[str, ...]


class ResourceQueue:
    """First-in, first-out scheduler with a hard reservation count limit.

    The caller owns all physical switching and must confirm a entity is OFF
    before releasing its reservation. Requests and releases should be
    serialized by the integration's coordinator.
    """

    def __init__(self, max_active: int = 3, strategy: str = DEFAULT_STRATEGY) -> None:
        if not isinstance(max_active, int) or isinstance(max_active, bool) or max_active < 1:
            raise ValueError("max_active must be a positive integer")
        self.max_active = max_active
        self.strategy = strategy
        self._strategy = get_strategy(strategy)
        self._active: dict[str, None] = {}
        self._waiting: deque[str] = deque()

    @classmethod
    def from_snapshot(
        cls,
        max_active: int,
        active: object,
        waiting: object,
        strategy: str = DEFAULT_STRATEGY,
    ) -> "ResourceQueue":
        """Restore an exact ordering without granting any new reservations.

        Invalid or inconsistent persisted data is rejected, never silently
        converted into an empty queue.
        """
        instance = cls(max_active, strategy)
        if not isinstance(active, list) or not isinstance(waiting, list):
            raise ValueError("stored active and waiting must be lists")

        all_resources = active + waiting
        if any(not isinstance(value, str) or not value.strip() or value != value.strip() for value in all_resources):
            raise ValueError("stored resource IDs must be non-empty normalized strings")
        if len(all_resources) != len(set(all_resources)):
            raise ValueError("duplicate resource ID in saved queue")
        if len(active) > max_active:
            raise ValueError("saved reservations exceed current limit")
        if waiting and len(active) < max_active:
            raise ValueError("saved waiting queue has unallocated free slots")

        instance._active = dict.fromkeys(active)
        instance._waiting = deque(waiting)
        return instance

    def request(self, resource_id: str) -> QueueResult:
        """Enqueue a request; immediately grant if capacity is available."""
        self._validate_id(resource_id)
        if resource_id not in self._active and resource_id not in self._waiting:
            self._strategy.enqueue(self._waiting, resource_id)
        return self._allocate()

    def release(self, resource_id: str) -> QueueResult:
        """Release reservation or withdraw a pending request."""
        self._validate_id(resource_id)
        self._active.pop(resource_id, None)
        try:
            self._waiting.remove(resource_id)
        except ValueError:
            pass
        return self._allocate()

    def snapshot(self) -> QueueResult:
        """Inspect state without changing the queue."""
        return QueueResult((), tuple(self._active), tuple(self._waiting))

    def allocate_pending(self) -> QueueResult:
        """Promote waiting requests after a verified capacity increase.

        Only the coordinator should call this, after recovery checks.
        """
        return self._allocate()

    def _allocate(self) -> QueueResult:
        newly_granted: list[str] = []
        while self._waiting and len(self._active) < self.max_active:
            candidate = self._waiting.popleft()
            if candidate in self._active:
                continue
            self._active[candidate] = None
            newly_granted.append(candidate)
        return QueueResult(
            tuple(newly_granted), tuple(self._active), tuple(self._waiting)
        )

    @staticmethod
    def _validate_id(resource_id: str) -> None:
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ValueError("resource_id must be a non-empty string")
