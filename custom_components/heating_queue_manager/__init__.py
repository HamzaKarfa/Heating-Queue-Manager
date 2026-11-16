"""Heating Queue Manager: FIFO reservations, no relay actuation."""

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ATTR_HEATER_ID,
    ATTR_RELAY_ENTITY_ID,
    CONF_MAX_ACTIVE,
    DEFAULT_MAX_ACTIVE,
    DOMAIN,
    EVENT_SLOT_GRANTED,
    SERVICE_CANCEL,
    SERVICE_RELEASE,
    SERVICE_REQUEST,
    SIGNAL_QUEUE_UPDATED,
)
from .coordinator import HeatingQueueCoordinator, QueueStateError
from .fifo import QueueResult

PLATFORMS = [Platform.SENSOR]

REQUEST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_HEATER_ID): cv.string,
        vol.Required(ATTR_RELAY_ENTITY_ID): cv.entity_id,
    }
)
HEATER_SCHEMA = vol.Schema({vol.Required(ATTR_HEATER_ID): cv.string})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register service actions once for this domain, not for each entry."""
    hass.data.setdefault(DOMAIN, {})

    def _get_coordinator() -> tuple[str, HeatingQueueCoordinator]:
        loaded = hass.data[DOMAIN]
        if len(loaded) != 1:
            raise HomeAssistantError(
                "Heating Queue Manager must have exactly one loaded config entry"
            )
        return next(iter(loaded.items()))

    def _publish(
        entry_id: str,
        manager: HeatingQueueCoordinator,
        result: QueueResult,
    ) -> None:
        """Notify observers after the entire queue mutation is complete."""
        async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
        for heater_id in result.granted:
            hass.bus.async_fire(
                EVENT_SLOT_GRANTED,
                {
                    ATTR_HEATER_ID: heater_id,
                    ATTR_RELAY_ENTITY_ID: manager.relay_for(heater_id),
                    "config_entry_id": entry_id,
                },
            )

    async def async_request(call: ServiceCall) -> None:
        """Place a heater in the queue or reserve an available slot."""
        entry_id, manager = _get_coordinator()
        try:
            result = manager.request(
                call.data[ATTR_HEATER_ID], call.data[ATTR_RELAY_ENTITY_ID]
            )
        except QueueStateError as err:
            raise HomeAssistantError(str(err)) from err
        _publish(entry_id, manager, result)

    async def async_release(call: ServiceCall) -> None:
        """Release a reservation after its observed relay is OFF."""
        entry_id, manager = _get_coordinator()
        try:
            result = manager.release(call.data[ATTR_HEATER_ID])
        except QueueStateError as err:
            raise HomeAssistantError(str(err)) from err
        _publish(entry_id, manager, result)

    async def async_cancel(call: ServiceCall) -> None:
        """Withdraw a request (an active reservation still needs relay OFF)."""
        entry_id, manager = _get_coordinator()
        try:
            result = manager.cancel(call.data[ATTR_HEATER_ID])
        except QueueStateError as err:
            raise HomeAssistantError(str(err)) from err
        _publish(entry_id, manager, result)

    hass.services.async_register(
        DOMAIN, SERVICE_REQUEST, async_request, schema=REQUEST_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELEASE, async_release, schema=HEATER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL, async_cancel, schema=HEATER_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create an entry-scoped coordinator and set up dashboard sensors."""
    def get_relay_state(entity_id: str) -> str | None:
        state = hass.states.get(entity_id)
        return state.state if state is not None else None

    manager = HeatingQueueCoordinator(
        max_active=entry.data.get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE),
        relay_state=get_relay_state,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload sensors before disposing of the in-memory scheduler."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
