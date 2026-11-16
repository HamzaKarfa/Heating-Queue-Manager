"""Resource Queue Manager (FIFO): persisted FIFO reservations, no entity switching."""

import asyncio
from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_RESOURCE_ID,
    ATTR_ENTITY_ID,
    CONF_MAX_ACTIVE,
    CONF_MONITORED_ENTITIES,
    DEFAULT_MAX_ACTIVE,
    DOMAIN,
    EVENT_SLOT_GRANTED,
    SERVICE_CANCEL,
    SERVICE_RELEASE,
    SERVICE_REQUEST,
    SERVICE_RESUME,
    SIGNAL_QUEUE_UPDATED,
)
from .coordinator import ResourceQueueCoordinator, QueueStateError
from .fifo import QueueResult

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.SENSOR]
STORAGE_VERSION = 1

REQUEST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_RESOURCE_ID): cv.string,
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    }
)
RESOURCE_SCHEMA = vol.Schema({vol.Required(ATTR_RESOURCE_ID): cv.string})


@dataclass
class QueueRuntime:
    """Queue, persistence and lock owned by one config entry."""

    manager: ResourceQueueCoordinator
    store: Store
    lock: asyncio.Lock


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Expose actions once; every queue change is serialized and saved."""
    hass.data.setdefault(DOMAIN, {})

    def _get_runtime() -> tuple[str, QueueRuntime]:
        loaded = hass.data[DOMAIN]
        if len(loaded) != 1:
            raise HomeAssistantError(
                "Resource Queue Manager (FIFO) must have exactly one loaded config entry"
            )
        return next(iter(loaded.items()))

    def _publish(entry_id: str, runtime: QueueRuntime, result: QueueResult) -> None:
        """Publish only after the queue snapshot has been written to disk."""
        async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
        for resource_id in result.granted:
            hass.bus.async_fire(
                EVENT_SLOT_GRANTED,
                {
                    ATTR_RESOURCE_ID: resource_id,
                    ATTR_ENTITY_ID: runtime.manager.entity_for(resource_id),
                    "config_entry_id": entry_id,
                },
            )

    async def _persist(runtime: QueueRuntime) -> None:
        """Write through synchronously before announcing new grants."""
        try:
            await runtime.store.async_save(runtime.manager.export_state())
        except Exception as err:
            runtime.manager.pause()
            raise HomeAssistantError(
                "Unable to save FIFO state; queue has been paused"
            ) from err

    async def _mutate(call: ServiceCall, operation: str) -> None:
        entry_id, runtime = _get_runtime()
        async with runtime.lock:
            try:
                if operation == SERVICE_REQUEST:
                    result = runtime.manager.request(
                        call.data[ATTR_RESOURCE_ID],
                        call.data[ATTR_ENTITY_ID],
                    )
                elif operation == SERVICE_RELEASE:
                    result = runtime.manager.release(call.data[ATTR_RESOURCE_ID])
                elif operation == SERVICE_CANCEL:
                    result = runtime.manager.cancel(call.data[ATTR_RESOURCE_ID])
                else:
                    raise HomeAssistantError("Unsupported queue operation")
            except QueueStateError as err:
                # Also notify dashboards if a safety check paused the manager.
                async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
                raise HomeAssistantError(str(err)) from err

            try:
                await _persist(runtime)
            except HomeAssistantError:
                async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
                raise
            _publish(entry_id, runtime, result)

    async def async_request(call: ServiceCall) -> None:
        await _mutate(call, SERVICE_REQUEST)

    async def async_release(call: ServiceCall) -> None:
        await _mutate(call, SERVICE_RELEASE)

    async def async_cancel(call: ServiceCall) -> None:
        await _mutate(call, SERVICE_CANCEL)

    async def async_resume(call: ServiceCall) -> None:
        """Explicitly re-enable grants after entity state inspection."""
        entry_id, runtime = _get_runtime()
        async with runtime.lock:
            try:
                result = runtime.manager.resume()
            except QueueStateError as err:
                raise HomeAssistantError(str(err)) from err
            try:
                await _persist(runtime)
            except HomeAssistantError:
                async_dispatcher_send(hass, SIGNAL_QUEUE_UPDATED, entry_id)
                raise
            _publish(entry_id, runtime, result)

    hass.services.async_register(
        DOMAIN, SERVICE_REQUEST, async_request, schema=REQUEST_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RELEASE, async_release, schema=RESOURCE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL, async_cancel, schema=RESOURCE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME, async_resume, schema=vol.Schema({})
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Restore reservations and known entities; always boot paused."""
    def get_entity_state(entity_id: str) -> str | None:
        state = hass.states.get(entity_id)
        return state.state if state is not None else None

    store = Store(
        hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
    )
    try:
        saved = await store.async_load()
        if saved is None:
            manager = ResourceQueueCoordinator(
                max_active=entry.options.get(
                    CONF_MAX_ACTIVE,
                    entry.data.get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE),
                ),
                entity_state=get_entity_state,
                monitored_entities=entry.options.get(CONF_MONITORED_ENTITIES, []),
            )
        else:
            manager = ResourceQueueCoordinator.from_state(
                max_active=entry.options.get(
                    CONF_MAX_ACTIVE,
                    entry.data.get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE),
                ),
                entity_state=get_entity_state,
                saved=saved,
                monitored_entities=entry.options.get(CONF_MONITORED_ENTITIES, []),
                legacy_max_active=entry.data.get(
                    CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE
                ),
            )
    except Exception as err:
        # Never reset to an empty queue on a corrupt/unreadable snapshot.
        raise ConfigEntryNotReady(
            "Unable to restore FIFO state; preserving existing storage"
        ) from err

    manager.pause()
    runtime = QueueRuntime(manager, store, asyncio.Lock())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload sensors before disposing of the queue runtime."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
