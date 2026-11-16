"""Heating Queue Manager integration bootstrap (no relay control yet)."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE, DOMAIN
from .fifo import HeatingQueue


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the component domain."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Instantiate an isolated scheduler for this config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = HeatingQueue(
        max_active=entry.data.get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a scheduler. No relay calls are made."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
