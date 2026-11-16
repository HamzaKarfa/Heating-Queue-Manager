"""Read-only sensors exposing FIFO reservations and recovery readiness."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_QUEUE_UPDATED
from .coordinator import HeatingQueueCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose counts and a status sensor for recovery."""
    manager: HeatingQueueCoordinator = hass.data[DOMAIN][entry.entry_id].manager
    async_add_entities(
        [
            HeatingQueueSensor(hass, entry.entry_id, manager, metric)
            for metric in ("active", "waiting", "available", "status")
        ]
    )


class HeatingQueueSensor(SensorEntity):
    """A FIFO counter or a readiness indicator with queue attributes."""

    _attr_should_poll = False
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        manager: HeatingQueueCoordinator,
        metric: str,
    ) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._manager = manager
        self._metric = metric
        self._attr_unique_id = f"{entry_id}_{metric}"
        self._attr_name = f"Heating Queue {metric.capitalize()}"

    @property
    def native_value(self) -> int | str:
        """Return a count or the safety state (paused/ready)."""
        snapshot = self._manager.snapshot()
        if self._metric == "active":
            return len(snapshot.active)
        if self._metric == "waiting":
            return len(snapshot.waiting)
        if self._metric == "status":
            return "paused" if self._manager.paused else "ready"
        # Available means *grantable* slots, not just free reservations.
        if self._manager.paused:
            return 0
        return self._manager.max_active - len(snapshot.active)

    @property
    def extra_state_attributes(self) -> dict:
        """Include current and pending FIFO order for dashboards."""
        snapshot = self._manager.snapshot()
        return {
            "active": list(snapshot.active),
            "waiting": list(snapshot.waiting),
            "max_active": self._manager.max_active,
            "paused": self._manager.paused,
            "monitored_relays": list(self._manager.monitored_relays),
            "recovery_issues": list(self._manager.recovery_issues()),
        }

    async def async_added_to_hass(self) -> None:
        """Track changes through dispatcher, without polling."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_QUEUE_UPDATED, self._handle_queue_change
            )
        )

    @callback
    def _handle_queue_change(self, entry_id: str) -> None:
        if entry_id == self._entry_id:
            self.async_write_ha_state()
