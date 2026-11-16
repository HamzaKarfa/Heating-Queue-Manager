"""Pure-Python FIFO coordinator with conservative restart recovery.

No Home Assistant imports and NO physical relay control. All operations are
synchronous; the HA adapter serializes state mutations and disk writes.
"""

from collections.abc import Callable, Iterable
from .fifo import HeatingQueue, QueueResult


class QueueStateError(ValueError):
    """A request or a recovery operation is unsafe."""


class HeatingQueueCoordinator:
    """Reserve slots only for explicitly supervised relays.

    A saved booking retains its binding. Historical relays are NOT supervised:
    monitoring is controlled by a separate configuration-entry option.
    """

    def __init__(
        self,
        max_active: int,
        relay_state: Callable[[str], str | None],
        monitored_relays: Iterable[str] = (),
    ) -> None:
        self.queue = HeatingQueue(max_active)
        self._relay_state = relay_state
        self._relays: dict[str, str] = {}
        monitored = list(monitored_relays)
        for relay in monitored:
            self._validate_relay_entity_id(relay)
        if len(set(monitored)) != len(monitored):
            raise QueueStateError("Duplicate supervised relay")
        self._monitored_relays = frozenset(monitored)
        self.paused = False

    @classmethod
    def from_state(
        cls,
        max_active: int,
        relay_state: Callable[[str], str | None],
        saved: object,
        monitored_relays: Iterable[str] = (),
    ) -> "HeatingQueueCoordinator":
        """Restore FIFO order and relay registry; always start paused."""
        if not isinstance(saved, dict):
            raise QueueStateError("Invalid stored coordinator state")

        queue = HeatingQueue.from_snapshot(
            max_active, saved.get("active"), saved.get("waiting")
        )
        bindings = saved.get("bindings")
        if not isinstance(bindings, dict):
            raise QueueStateError("Invalid saved relay assignments")
        current_ids = set(queue.snapshot().active + queue.snapshot().waiting)
        if set(bindings) != current_ids:
            raise QueueStateError("Saved queue and relay assignments disagree")

        # Accept version 0.2 storage containing historical known_relays,
        # but never treat that history as the current supervision registry.
        known = saved.get("known_relays")
        if known is not None:
            if not isinstance(known, dict) or any(
                known.get(heater) != relay for heater, relay in bindings.items()
            ):
                raise QueueStateError("Legacy relay registry disagrees with queue")

        instance = cls(max_active, relay_state, monitored_relays)
        for heater, relay in bindings.items():
            instance._validate_heater_id(heater)
            instance._validate_relay_entity_id(relay)
        if len(set(bindings.values())) != len(bindings):
            raise QueueStateError("Multiple queued heaters share a relay")

        # Refuse a changed configuration that would silently abandon a
        # reserved or waiting heater. The options flow also guards this.
        unmanaged = set(bindings.values()) - instance._monitored_relays
        if unmanaged:
            raise QueueStateError(
                "Saved queued relays are not supervised: "
                + ", ".join(sorted(unmanaged))
            )

        instance.queue = queue
        instance._relays = dict(bindings)
        instance.pause()
        return instance

    def export_state(self) -> dict:
        """JSON-safe snapshot for Home Assistant's persistent Store."""
        snapshot = self.queue.snapshot()
        return {
            "active": list(snapshot.active),
            "waiting": list(snapshot.waiting),
            "bindings": dict(self._relays),
        }

    def snapshot(self) -> QueueResult:
        """Return an immutable view of reservations."""
        return self.queue.snapshot()

    @property
    def max_active(self) -> int:
        return self.queue.max_active

    @property
    def monitored_relays(self) -> tuple[str, ...]:
        """Explicit relay supervision list from Home Assistant options."""
        return tuple(sorted(self._monitored_relays))

    def relay_for(self, heater_id: str) -> str | None:
        """Return the relay for a current reservation or waiting request."""
        return self._relays.get(heater_id)

    def pause(self) -> None:
        """Stop granting or releasing slots until a recovery check completes."""
        self.paused = True

    def recovery_issues(self) -> tuple[str, ...]:
        """Check configured relays, never historical test associations."""
        active_relays = {
            self._relays[heater_id] for heater_id in self.queue.snapshot().active
        }
        problems: list[str] = []
        for relay in sorted(self._monitored_relays):
            state = self._relay_state(relay)
            if state not in ("on", "off"):
                problems.append(f"{relay}: state {state!r} is unverified")
            elif state == "on" and relay not in active_relays:
                problems.append(f"{relay}: ON without a reservation")
        return tuple(problems)

    def resume(self) -> None:
        """Resume ONLY after all known relay observations are consistent.

        A previously saved active reservation is never automatically
        released, even if its relay appears OFF. The owner must call release.
        """
        problems = self.recovery_issues()
        if problems:
            raise QueueStateError("Recovery blocked: " + "; ".join(problems))
        self.paused = False

    def _require_ready(self) -> None:
        if self.paused:
            raise QueueStateError(
                "Queue is paused after startup; check relays and call resume"
            )

    def request(self, heater_id: str, relay_entity_id: str) -> QueueResult:
        """Ask for a slot, without switching any real device."""
        self._require_ready()
        self._validate_heater_id(heater_id)
        self._validate_relay_entity_id(relay_entity_id)
        if relay_entity_id not in self._monitored_relays:
            raise QueueStateError(
                f"Relay {relay_entity_id!r} is not supervised; configure it first"
            )
        old = self._relays.get(heater_id)
        if old is not None and old != relay_entity_id:
            raise QueueStateError(
                f"{heater_id!r} is already bound to {old!r}"
            )
        if any(
            other_id != heater_id and bound_relay == relay_entity_id
            for other_id, bound_relay in self._relays.items()
        ):
            raise QueueStateError(
                f"Relay {relay_entity_id!r} is bound to another heater"
            )

        # Check every explicitly supervised relay before granting.
        problems = self.recovery_issues()
        if problems:
            self.pause()
            raise QueueStateError(
                "Queue paused on unsafe relay state: " + "; ".join(problems)
            )

        state = self._relay_state(relay_entity_id)
        if state not in ("on", "off"):
            raise QueueStateError(
                f"Relay {relay_entity_id!r} is not available (state={state!r})"
            )
        if state == "on" and heater_id not in self.queue.snapshot().active:
            raise QueueStateError(
                f"Relay {relay_entity_id!r} is ON without a reservation"
            )

        result = self.queue.request(heater_id)
        self._relays[heater_id] = relay_entity_id
        return result

    def release(self, heater_id: str) -> QueueResult:
        """Release a slot only if the relay is observed OFF."""
        return self._discard(heater_id)

    def cancel(self, heater_id: str) -> QueueResult:
        """Cancel a pending request or release an OFF reservation."""
        return self._discard(heater_id)

    def _discard(self, heater_id: str) -> QueueResult:
        self._require_ready()
        self._validate_heater_id(heater_id)
        if heater_id in self.queue.snapshot().active:
            relay = self._relays[heater_id]
            state = self._relay_state(relay)
            if state != "off":
                raise QueueStateError(
                    f"Cannot release {heater_id!r}: relay {relay!r} "
                    f"must be OFF (state={state!r})"
                )
        problems = self.recovery_issues()
        if problems:
            self.pause()
            raise QueueStateError(
                "Queue paused on unsafe relay state: " + "; ".join(problems)
            )

        result = self.queue.release(heater_id)
        self._relays.pop(heater_id, None)
        return result

    @staticmethod
    def _validate_heater_id(heater_id: str) -> None:
        if not isinstance(heater_id, str) or not heater_id.strip():
            raise QueueStateError("heater_id must be a non-empty string")
        if heater_id != heater_id.strip():
            raise QueueStateError("heater_id must not have surrounding whitespace")

    @staticmethod
    def _validate_relay_entity_id(relay_entity_id: str) -> None:
        if (
            not isinstance(relay_entity_id, str)
            or relay_entity_id.count(".") != 1
            or relay_entity_id.split(".", 1)[0] not in ("light", "switch")
            or not relay_entity_id.split(".", 1)[1]
        ):
            raise QueueStateError(
                "relay_entity_id must be a light.* or switch.* entity"
            )
