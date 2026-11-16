"""User setup and selection of explicitly supervised light/switch entities."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
from homeassistant.helpers.storage import Store

from .const import (
    CONF_MAX_ACTIVE,
    CONF_MONITORED_RELAYS,
    DEFAULT_MAX_ACTIVE,
    DOMAIN,
)

STORAGE_VERSION = 1


class HeatingQueueManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one singleton Heating Queue Manager instance."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Create a config entry from the integrations UI."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Heating Queue Manager", data=user_input
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_MAX_ACTIVE, default=DEFAULT_MAX_ACTIVE):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=50))
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "HeatingQueueOptionsFlow":
        """Expose the Configure button in Home Assistant."""
        return HeatingQueueOptionsFlow()


class HeatingQueueOptionsFlow(OptionsFlowWithReload):
    """Explicit list of relays supervised by the FIFO scheduler."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ):
        """Validate changes against currently queued reservations."""
        entry = self.config_entry
        errors: dict[str, str] = {}
        existing = list(entry.options.get(CONF_MONITORED_RELAYS, []))

        if user_input is not None:
            selected = list(user_input.get(CONF_MONITORED_RELAYS, []))
            runtime = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if runtime is not None:
                bindings = runtime.manager.export_state()["bindings"]
            else:
                # A failed/unloaded entry can still contain reservations.
                # Never permit their exclusion without inspecting storage.
                try:
                    store = Store(
                        self.hass,
                        STORAGE_VERSION,
                        f"{DOMAIN}.{entry.entry_id}",
                    )
                    saved = await store.async_load()
                    bindings = (saved or {}).get("bindings", {})
                    if not isinstance(bindings, dict):
                        raise ValueError("Invalid stored relay bindings")
                except Exception:
                    errors["base"] = "storage_unavailable"
                    bindings = {}

            if not errors and not set(bindings.values()).issubset(selected):
                errors["base"] = "relays_in_use"

            if not errors:
                return self.async_create_entry(
                    data={CONF_MONITORED_RELAYS: selected}
                )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_MONITORED_RELAYS,
                    default=existing,
                ): EntitySelector(
                    EntitySelectorConfig(
                        domain=["light", "switch"], multiple=True
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
