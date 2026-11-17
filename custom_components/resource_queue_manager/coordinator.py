"""Pure-Python FIFO coordinator with conservative restart recovery.

No Home Assistant imports and NO physical entity control. All operations are
synchronous; the HA adapter serializes state mutations and disk writes.
"""

from collections.abc import Callable, Iterable, Mapping
from .engine import ResourceQueue, QueueResult
from .strategies import DEFAULT_STRATEGY, validate_strategy_config


class QueueStateError(ValueError):
    """A request or a recovery operation is unsafe."""


class ResourceQueueCoordinator:
    """Reserve slots only for explicitly supervised entities.

    A saved booking retains its binding. Historical entities are NOT supervised:
    monitoring is controlled by a separate configuration-entry option.
    """

    def __init__(
        self,
        max_active: int,
        entity_state: Callable[[str], str | None],
        monitored_entities: Iterable[str] = (),
        strategy: str = DEFAULT_STRATEGY,
        strategy_config: Mapping[str, object] | None = None,
    ) -> None:
        self.queue = ResourceQueue(max_active, strategy, strategy_config)
        self._entity_state = entity_state
        self._entities: dict[str, str] = {}
        monitored = list(monitored_entities)
        for entity in monitored:
            self._validate_entity_id(entity)
        if len(set(monitored)) != len(monitored):
            raise QueueStateError("Duplicate supervised entity")
        self._monitored_entities = frozenset(monitored)
        self.paused = False

    @classmethod
    def from_state(
        cls,
        max_active: int,
        entity_state: Callable[[str], str | None],
        saved: object,
        monitored_entities: Iterable[str] = (),
        legacy_max_active: int | None = None,
        strategy: str = DEFAULT_STRATEGY,
        strategy_config: Mapping[str, object] | None = None,
    ) -> "ResourceQueueCoordinator":
        """Restore FIFO order and entity registry; always start paused."""
        if not isinstance(saved, dict):
            raise QueueStateError("Invalid stored coordinator state")

        # The saved limit validates the ORIGINAL FIFO invariants. The new
        # configured limit can be larger without allocating extra slots yet.
        # Old 0.2 snapshots lacked max_active; use the initial entry limit.
        stored_limit = saved.get(
            "max_active",
            legacy_max_active if legacy_max_active is not None else max_active,
        )
        saved_strategy = saved.get("strategy", DEFAULT_STRATEGY)
        saved_config = saved.get("strategy_config", {})
        configured = validate_strategy_config(strategy, strategy_config)
        saved_active = saved.get("active")
        saved_waiting = saved.get("waiting")
        # Never silently reinterpret already queued requests under a new policy.
        if (saved_strategy != strategy or saved_config != configured) and (
            saved_active or saved_waiting
        ):
            raise QueueStateError(
                "Cannot change strategy or settings while reservations or requests are pending"
            )
        queue = ResourceQueue.from_snapshot(
            stored_limit, saved_active, saved_waiting,
            strategy=strategy, strategy_config=configured,
        )
        if len(queue.snapshot().active) > max_active:
            raise QueueStateError(
                "New maximum cannot be below the saved active reservations"
            )
        queue.max_active = max_active
        bindings = saved.get("bindings")
        if not isinstance(bindings, dict):
            raise QueueStateError("Invalid saved entity assignments")
        current_ids = set(queue.snapshot().active + queue.snapshot().waiting)
        if set(bindings) != current_ids:
            raise QueueStateError("Saved queue and entity assignments disagree")

        # Accept version 0.2 storage containing historical known_entities,
        # but never treat that history as the current supervision registry.
        known = saved.get("known_entities")
        if known is not None:
            if not isinstance(known, dict) or any(
                known.get(resource) != entity for resource, entity in bindings.items()
            ):
                raise QueueStateError("Legacy entity registry disagrees with queue")

        instance = cls(
            max_active, entity_state, monitored_entities,
            strategy=strategy, strategy_config=configured,
        )
        for resource, entity in bindings.items():
            instance._validate_resource_id(resource)
            instance._validate_entity_id(entity)
        if len(set(bindings.values())) != len(bindings):
            raise QueueStateError("Multiple queued resources share a entity")

        # Refuse a changed configuration that would silently abandon a
        # reserved or waiting resource. The options flow also guards this.
        unmanaged = set(bindings.values()) - instance._monitored_entities
        if unmanaged:
            raise QueueStateError(
                "Saved queued entities are not supervised: "
                + ", ".join(sorted(unmanaged))
            )

        instance.queue = queue
        instance._entities = dict(bindings)
        instance.pause()
        return instance

    def export_state(self) -> dict:
        """JSON-safe snapshot for Home Assistant's persistent Store."""
        snapshot = self.queue.snapshot()
        return {
            "active": list(snapshot.active),
            "waiting": list(snapshot.waiting),
            "max_active": self.max_active,
            "strategy": self.strategy,
            "strategy_config": dict(self.queue.strategy_config),
            "bindings": dict(self._entities),
        }

    def snapshot(self) -> QueueResult:
        """Return an immutable view of reservations."""
        return self.queue.snapshot()

    @property
    def strategy(self) -> str:
        return self.queue.strategy

    @property
    def max_active(self) -> int:
        return self.queue.max_active

    @property
    def monitored_entities(self) -> tuple[str, ...]:
        """Explicit entity supervision list from Home Assistant options."""
        return tuple(sorted(self._monitored_entities))

    def entity_for(self, resource_id: str) -> str | None:
        """Return the entity for a current reservation or waiting request."""
        return self._entities.get(resource_id)

    def pause(self) -> None:
        """Stop granting or releasing slots until a recovery check completes."""
        self.paused = True

    def recovery_issues(self) -> tuple[str, ...]:
        """Check configured entities, never historical test associations."""
        active_entities = {
            self._entities[resource_id] for resource_id in self.queue.snapshot().active
        }
        problems: list[str] = []
        for entity in sorted(self._monitored_entities):
            state = self._entity_state(entity)
            if state not in ("on", "off"):
                problems.append(f"{entity}: state {state!r} is unverified")
            elif state == "on" and entity not in active_entities:
                problems.append(f"{entity}: ON without a reservation")
        return tuple(problems)

    def resume(self) -> QueueResult:
        """Resume after checking supervised entities, filling increased slots.

        Existing active bookings remain allocated. If the limit was raised
        while waiting requests existed, the oldest requests receive the new
        slots. The HA adapter persists this result BEFORE firing their grants.
        """
        problems = self.recovery_issues()
        if problems:
            raise QueueStateError("Recovery blocked: " + "; ".join(problems))
        self.paused = False
        return self.queue.allocate_pending()

    def _require_ready(self) -> None:
        if self.paused:
            raise QueueStateError(
                "Queue is paused after startup; check entities and call resume"
            )

    def request(self, resource_id: str, entity_id: str) -> QueueResult:
        """Ask for a slot, without switching any real device."""
        self._require_ready()
        self._validate_resource_id(resource_id)
        self._validate_entity_id(entity_id)
        if entity_id not in self._monitored_entities:
            raise QueueStateError(
                f"Entity {entity_id!r} is not supervised; configure it first"
            )
        old = self._entities.get(resource_id)
        if old is not None and old != entity_id:
            raise QueueStateError(
                f"{resource_id!r} is already bound to {old!r}"
            )
        if any(
            other_id != resource_id and bound_relay == entity_id
            for other_id, bound_relay in self._entities.items()
        ):
            raise QueueStateError(
                f"Entity {entity_id!r} is bound to another resource"
            )

        # Check every explicitly supervised entity before granting.
        problems = self.recovery_issues()
        if problems:
            self.pause()
            raise QueueStateError(
                "Queue paused on unsafe entity state: " + "; ".join(problems)
            )

        state = self._entity_state(entity_id)
        if state not in ("on", "off"):
            raise QueueStateError(
                f"Entity {entity_id!r} is not available (state={state!r})"
            )
        if state == "on" and resource_id not in self.queue.snapshot().active:
            raise QueueStateError(
                f"Entity {entity_id!r} is ON without a reservation"
            )

        result = self.queue.request(resource_id)
        self._entities[resource_id] = entity_id
        return result

    def release(self, resource_id: str) -> QueueResult:
        """Release a slot only if the entity is observed OFF."""
        return self._discard(resource_id)

    def cancel(self, resource_id: str) -> QueueResult:
        """Cancel a pending request or release an OFF reservation."""
        return self._discard(resource_id)

    def _discard(self, resource_id: str) -> QueueResult:
        self._require_ready()
        self._validate_resource_id(resource_id)
        if resource_id in self.queue.snapshot().active:
            entity = self._entities[resource_id]
            state = self._entity_state(entity)
            if state != "off":
                raise QueueStateError(
                    f"Cannot release {resource_id!r}: entity {entity!r} "
                    f"must be OFF (state={state!r})"
                )
        problems = self.recovery_issues()
        if problems:
            self.pause()
            raise QueueStateError(
                "Queue paused on unsafe entity state: " + "; ".join(problems)
            )

        result = self.queue.release(resource_id)
        self._entities.pop(resource_id, None)
        return result

    @staticmethod
    def _validate_resource_id(resource_id: str) -> None:
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise QueueStateError("resource_id must be a non-empty string")
        if resource_id != resource_id.strip():
            raise QueueStateError("resource_id must not have surrounding whitespace")

    @staticmethod
    def _validate_entity_id(entity_id: str) -> None:
        if (
            not isinstance(entity_id, str)
            or entity_id.count(".") != 1
            or entity_id.split(".", 1)[0] not in ("light", "switch")
            or not entity_id.split(".", 1)[1]
        ):
            raise QueueStateError(
                "entity_id must be a light.* or switch.* entity"
            )
