"""Strategy-independent, pure-Python reservation engine.

Queue policy controls *only the next-grant order*. Active reservations,
capacity, de-duplication and request persistence belong to this engine.
Physical device switching remains strictly outside the engine.
"""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from .strategies import (
    DEFAULT_STRATEGY,
    QueueRequest,
    get_strategy,
    validate_request_data,
    validate_strategy_config,
)


@dataclass(frozen=True, slots=True)
class QueueResult:
    """Snapshot after a queue transition, preserving legacy ID-only outputs."""

    granted: tuple[str, ...]
    active: tuple[str, ...]
    waiting: tuple[str, ...]


class ResourceQueue:
    """Hard-capacity queue with an injected scheduling policy."""

    def __init__(
        self,
        max_active: int = 3,
        strategy: str = DEFAULT_STRATEGY,
        strategy_config: Mapping[str, object] | None = None,
    ) -> None:
        if (
            type(max_active) is not int
            or max_active < 1
        ):
            raise ValueError("max_active must be a positive integer")
        self.max_active = max_active
        self.strategy = strategy
        self.strategy_config = validate_strategy_config(strategy, strategy_config)
        self._strategy = get_strategy(strategy, self.strategy_config)
        self._active: dict[str, None] = {}
        self._waiting: deque[str] = deque()
        self._requests: dict[str, QueueRequest] = {}

    @classmethod
    def from_snapshot(
        cls,
        max_active: int,
        active: object,
        waiting: object,
        strategy: str = DEFAULT_STRATEGY,
        strategy_config: Mapping[str, object] | None = None,
        request_data: object | None = None,
    ) -> "ResourceQueue":
        """Restore grants and metadata exactly; never allocate while loading."""
        instance = cls(max_active, strategy, strategy_config)
        if not isinstance(active, list) or not isinstance(waiting, list):
            raise ValueError("stored active and waiting must be lists")
        combined = active + waiting
        if any(
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            for value in combined
        ):
            raise ValueError("stored resource IDs must be normalized strings")
        if len(combined) != len(set(combined)):
            raise ValueError("duplicate resource ID in saved queue")
        if len(active) > max_active:
            raise ValueError("saved reservations exceed current limit")
        if waiting and len(active) < max_active:
            raise ValueError("saved waiting queue has unallocated free slots")

        if request_data is None:
            request_data = {}
        if not isinstance(request_data, dict):
            raise ValueError("stored request metadata must be a mapping")
        if set(request_data) - set(combined):
            raise ValueError("saved request metadata contains unknown resources")

        restored: dict[str, QueueRequest] = {}
        for resource_id in combined:
            normalized = validate_request_data(
                strategy, request_data.get(resource_id, {})
            )
            restored[resource_id] = QueueRequest(resource_id, normalized)

        instance._active = dict.fromkeys(active)
        instance._waiting = deque(waiting)
        instance._requests = restored
        return instance

    def request(
        self,
        resource_id: str,
        request_data: Mapping[str, object] | None = None,
    ) -> QueueResult:
        """Request a slot with metadata validated by its provider."""
        self._validate_id(resource_id)
        metadata = validate_request_data(self.strategy, request_data)
        existing = self._requests.get(resource_id)
        if existing is not None:
            if dict(existing.data) != metadata:
                raise ValueError(
                    f"Resource {resource_id!r} already has different request metadata"
                )
            return self._allocate()

        request = QueueRequest(resource_id, metadata)
        # A strategy can consult all pending and active request metadata.
        self._strategy.enqueue(
            self._waiting, request, {**self._requests, resource_id: request}
        )
        if resource_id not in self._waiting:
            raise ValueError("Strategy failed to enqueue the resource")
        self._requests[resource_id] = request
        return self._allocate()

    def release(self, resource_id: str) -> QueueResult:
        """Release a reservation or withdraw a pending request."""
        self._validate_id(resource_id)
        self._active.pop(resource_id, None)
        try:
            self._waiting.remove(resource_id)
        except ValueError:
            pass
        self._requests.pop(resource_id, None)
        return self._allocate()

    def snapshot(self) -> QueueResult:
        return QueueResult((), tuple(self._active), tuple(self._waiting))

    def export_request_data(self) -> dict[str, dict[str, str | int | float | bool]]:
        """Persist only non-empty request metadata, keyed by resource ID."""
        return {
            resource_id: dict(request.data)
            for resource_id, request in self._requests.items()
            if request.data
        }

    def allocate_pending(self) -> QueueResult:
        """Only the coordinator calls this after safety/recovery checks."""
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
        if (
            not isinstance(resource_id, str)
            or not resource_id.strip()
            or resource_id != resource_id.strip()
        ):
            raise ValueError("resource_id must be a non-empty normalized string")
