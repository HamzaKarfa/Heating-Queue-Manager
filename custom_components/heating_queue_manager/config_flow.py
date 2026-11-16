"""UI configuration for Heating Queue Manager."""

import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE, DOMAIN


class HeatingQueueManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a singleton Heating Queue Manager instance."""

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
