"""Domain-aware supervision of Home Assistant entities for logical queues.

ON/OFF devices retain fail-closed electrical-style reservation semantics.
Other entity domains are availability-checked logical resources: their values
are not interpreted as physical device state or an electrical safety signal.
This module intentionally does not import Home Assistant.
"""

import re

ON_OFF_DOMAINS = frozenset({"light", "switch", "input_boolean", "fan"})
UNKNOWN_STATES = frozenset({"unknown", "unavailable"})
ENTITY_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*\.[a-z0-9_]+")


def validate_entity_id(entity_id: str) -> None:
    """Validate a normalized Home Assistant entity ID, without domain limits."""
    if not isinstance(entity_id, str) or not ENTITY_ID_PATTERN.fullmatch(entity_id):
        raise ValueError("entity_id must be a valid Home Assistant entity ID")


def supervision_mode(entity_id: str) -> str:
    """Classify independent of the current value (which may itself be 'on')."""
    return "on_off" if entity_id.split(".", 1)[0] in ON_OFF_DOMAINS else "availability"


def state_is_known(state: str | None) -> bool:
    """Reject missing, unknown, and unavailable states for all entity types."""
    return isinstance(state, str) and state not in UNKNOWN_STATES


def recovery_issue(entity_id: str, state: str | None, active: bool) -> str | None:
    """Return a fail-closed reason when a supervised resource is inconsistent."""
    if not state_is_known(state):
        return f"{entity_id}: state {state!r} is unverified"
    if supervision_mode(entity_id) == "on_off":
        if state not in ("on", "off"):
            return f"{entity_id}: ON/OFF state {state!r} is unverified"
        if state == "on" and not active:
            return f"{entity_id}: ON without a reservation"
    return None


def release_issue(entity_id: str, state: str | None) -> str | None:
    """Release only on OFF for actuators; generic entities need known state."""
    if supervision_mode(entity_id) == "on_off":
        if state != "off":
            return (
                f"entity {entity_id!r} must be OFF "
                f"(state={state!r})"
            )
    elif not state_is_known(state):
        return (
            f"entity {entity_id!r} must be available "
            f"(state={state!r})"
        )
    return None
