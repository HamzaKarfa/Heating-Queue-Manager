"""Pure-Python coordinator between FIFO reservations and relay observations.

This module intentionally does not import Home Assistant and NEVER switches a relay.
Its public methods are synchronous: the Home Assistant adapter calls them on the
event loop without awaiting between checking and reserving a slot.
"""

from collections.abc import Callable

from .fifo import HeatingQueue, QueueResult


class QueueStateError(ValueError):
    """A request cannot safely change the queue."""


class HeatingQueueCoordinator:
    """Manage one FIFO queue and an immutable relay binding per request."""

    def __init__(
        self,
        max_active: int,
        relay_state: Callable[[str], str | None],
    ) -> None:
        self.queue = HeatingQueue(max_active)
        self._relay_state = relay_state
        self._relays: dict[str, str] = {}

    def snapshot(self) -> QueueResult:
        """Return a read-only view of the queue."""
        return self.queue.snapshot()

    @property
    def max_active(self) -> int:
        return self.queue.max_active

    def relay_for(self, heater_id: str) -> str | None:
        """Return the registered relay entity for a heater."""
        return self._relays.get(heater_id)

    def request(self, heater_id: str, relay_entity_id: str) -> QueueResult:
        """Request a slot, without powering any physical device.

        Refuse a new request if the relay is already on, unknown, or unavailable.
        Duplicate requests are idempotent; changing a binding is forbidden.
        """
        self._validate_heater_id(heater_id)
        self._validate_relay_entity_id(relay_entity_id)
        old = self._relays.get(heater_id)
        if old is not None and old != relay_entity_id:
            raise QueueStateError(
                f"{heater_id!r} is already bound to {old!r}"
            )

        state = self._relay_state(relay_entity_id)
        if state not in ("on", "off"):
            raise QueueStateError(
                f"Relay {relay_entity_id!r} is not available (state={state!r})"
            )

        if state == "on" and heater_id not in self.queue.snapshot().active:
            raise QueueStateError(
                f"Relay {relay_entity_id!r} is already ON without a reservation"
            )

        # No await between validation, registration and reservation.
        result = self.queue.request(heater_id)
        self._relays[heater_id] = relay_entity_id
        return result

    def release(self, heater_id: str) -> QueueResult:
        """Release a heater only when its observed relay state is OFF.

        This reads Home Assistant's state, NOT a safety-rated physical contact.
        Unknown and unavailable are treated as unsafe; keep the reservation.
        """
        return self._discard(heater_id)

    def cancel(self, heater_id: str) -> QueueResult:
        """Withdraw pending requests; reserved requests require relay OFF too."""
        return self._discard(heater_id)

    def _discard(self, heater_id: str) -> QueueResult:
        self._validate_heater_id(heater_id)
        if heater_id in self.queue.snapshot().active:
            relay = self._relays[heater_id]
            state = self._relay_state(relay)
            if state != "off":
                raise QueueStateError(
                    f"Cannot release {heater_id!r}: relay {relay!r} "
                    f"must be OFF (state={state!r})"
                )

        # Once released, the oldest pending request is promoted atomically.
        result = self.queue.release(heater_id)
        self._relays.pop(heater_id, None)
        return result

    @staticmethod
    def _validate_heater_id(heater_id: str) -> None:
        if not isinstance(heater_id, str) or not heater_id.strip():
            raise QueueStateError("heater_id must be a non-empty string")
        if heater_id.strip() != heater_id:
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
