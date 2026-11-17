"""Config flow for independent Resource Queue Manager instances."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from homeassistant.helpers.storage import Store

from .const import (
    CONF_MAX_ACTIVE,
    CONF_MONITORED_ENTITIES,
    CONF_NAME,
    CONF_STRATEGY,
    CONF_STRATEGY_CONFIG,
    DEFAULT_MAX_ACTIVE,
    DOMAIN,
)
from .strategies import (
    DEFAULT_STRATEGY,
    STRATEGIES,
    get_provider,
    strategy_options,
    validate_strategy_config,
)
from .strategy_forms import strategy_form_schema

STORAGE_VERSION = 1

MAX_ACTIVE_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=50, step=1, mode=NumberSelectorMode.BOX)
)
def strategy_selector(language: str = "en") -> SelectSelector:
    """Refresh provider choices in the user's Home Assistant language."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(**item)
                for item in strategy_options(language)
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
ENTITIES_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=["light", "switch"], multiple=True)
)


def _overlapping_entities(hass, selected: list[str], exclude: str | None = None) -> set[str]:
    """Refuse one physical entity being controlled by two independent queues."""
    selected_set = set(selected)
    overlapping: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == exclude:
            continue
        other = entry.options.get(
            CONF_MONITORED_ENTITIES,
            entry.data.get(CONF_MONITORED_ENTITIES, []),
        )
        overlapping.update(selected_set.intersection(other))
    return overlapping


class ResourceQueueManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create distinct queue entries; older singleton entries remain intact."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors["base"] = "invalid_name"
            elif any(e.title == name for e in self.hass.config_entries.async_entries(DOMAIN)):
                errors["base"] = "name_in_use"
            elif user_input[CONF_STRATEGY] not in STRATEGIES:
                errors["base"] = "invalid_strategy"
            elif _overlapping_entities(
                self.hass, user_input.get(CONF_MONITORED_ENTITIES, [])
            ):
                errors["base"] = "entities_in_use_elsewhere"
            else:
                # No shared unique_id: each flow creates an independent entry.
                self._pending_data = {
                    CONF_NAME: name,
                    CONF_MAX_ACTIVE: int(user_input[CONF_MAX_ACTIVE]),
                    CONF_STRATEGY: user_input[CONF_STRATEGY],
                    CONF_MONITORED_ENTITIES: list(
                        user_input.get(CONF_MONITORED_ENTITIES, [])
                    ),
                }
                if get_provider(user_input[CONF_STRATEGY]).config_fields:
                    return await self.async_step_strategy()
                self._pending_data[CONF_STRATEGY_CONFIG] = {}
                return self.async_create_entry(title=name, data=self._pending_data)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=(user_input or {}).get(CONF_NAME, "My queue")): str,
                vol.Required(
                    CONF_MAX_ACTIVE,
                    default=(user_input or {}).get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE),
                ): MAX_ACTIVE_SELECTOR,
                vol.Required(
                    CONF_STRATEGY,
                    default=(user_input or {}).get(CONF_STRATEGY, DEFAULT_STRATEGY),
                ): strategy_selector(self.hass.config.language),
                vol.Optional(
                    CONF_MONITORED_ENTITIES,
                    default=(user_input or {}).get(CONF_MONITORED_ENTITIES, []),
                ): ENTITIES_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_strategy(self, user_input: dict | None = None):
        """Configure fields provided by the selected algorithm module."""
        strategy = self._pending_data[CONF_STRATEGY]
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                normalized = validate_strategy_config(strategy, user_input)
            except ValueError:
                errors["base"] = "invalid_strategy_options"
            else:
                # A queue may have been created while this flow was open.
                if any(
                    e.title == self._pending_data[CONF_NAME]
                    for e in self.hass.config_entries.async_entries(DOMAIN)
                ):
                    errors["base"] = "name_in_use"
                elif _overlapping_entities(
                    self.hass, self._pending_data[CONF_MONITORED_ENTITIES]
                ):
                    errors["base"] = "entities_in_use_elsewhere"
                else:
                    data = dict(self._pending_data)
                    data[CONF_STRATEGY_CONFIG] = normalized
                    return self.async_create_entry(title=data[CONF_NAME], data=data)
        return self.async_show_form(
            step_id="strategy",
            data_schema=strategy_form_schema(
                strategy, user_input, self.hass.config.language
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "ResourceQueueOptionsFlow":
        return ResourceQueueOptionsFlow()


class ResourceQueueOptionsFlow(OptionsFlowWithReload):
    """Configure capacity, strategy and supervised entities per entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        entry = self.config_entry
        errors: dict[str, str] = {}
        selected = list(
            entry.options.get(
                CONF_MONITORED_ENTITIES,
                entry.data.get(CONF_MONITORED_ENTITIES, []),
            )
        )
        current_limit = entry.options.get(
            CONF_MAX_ACTIVE, entry.data.get(CONF_MAX_ACTIVE, DEFAULT_MAX_ACTIVE)
        )
        current_strategy = entry.options.get(
            CONF_STRATEGY, entry.data.get(CONF_STRATEGY, DEFAULT_STRATEGY)
        )
        current_config = entry.options.get(
            CONF_STRATEGY_CONFIG, entry.data.get(CONF_STRATEGY_CONFIG, {})
        )
        new_limit = current_limit
        new_strategy = current_strategy

        if user_input is not None:
            selected = list(user_input.get(CONF_MONITORED_ENTITIES, []))
            new_limit = int(user_input[CONF_MAX_ACTIVE])
            new_strategy = user_input[CONF_STRATEGY]
            if new_strategy not in STRATEGIES:
                errors["base"] = "invalid_strategy"
            elif _overlapping_entities(self.hass, selected, entry.entry_id):
                errors["base"] = "entities_in_use_elsewhere"

            # When a plugin form is required, defer settings validation until
            # its final submit. No live queue is paused during the extra step.
            ready = getattr(self, "_strategy_config_ready", False)
            has_fields = not errors and bool(get_provider(new_strategy).config_fields)
            pending_plugin_form = bool(has_fields and not ready)
            candidate_config = (
                self._validated_strategy_config
                if ready
                else current_config if current_strategy == new_strategy else {}
            )

            runtime = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if not errors and runtime is not None:
                async with runtime.lock:
                    saved = runtime.manager.export_state()
                    if not set(saved["bindings"].values()).issubset(selected):
                        errors["base"] = "entities_in_use"
                    elif new_limit < len(saved["active"]):
                        errors["base"] = "max_active_below_reserved"
                    elif (
                        new_strategy != runtime.manager.strategy
                        or (
                            not pending_plugin_form
                            and candidate_config != runtime.manager.queue.strategy_config
                        )
                    ) and (saved["active"] or saved["waiting"]):
                        errors["base"] = "strategy_in_use"
                    # Defer pausing until a plugin-specific form has finished.
                    if not errors and (
                        not get_provider(new_strategy).config_fields
                        or getattr(self, "_strategy_config_ready", False)
                    ):
                        runtime.manager.pause()
            elif not errors:
                try:
                    store = Store(
                        self.hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
                    )
                    saved = await store.async_load()
                    saved = {} if saved is None else saved
                    if not isinstance(saved, dict):
                        raise ValueError("Invalid stored queue")
                    bindings = saved.get("bindings", {})
                    active = saved.get("active", [])
                    waiting = saved.get("waiting", [])
                    if (
                        not isinstance(bindings, dict)
                        or not isinstance(active, list)
                        or not isinstance(waiting, list)
                    ):
                        raise ValueError("Invalid stored queue")
                    if not set(bindings.values()).issubset(selected):
                        errors["base"] = "entities_in_use"
                    elif new_limit < len(active):
                        errors["base"] = "max_active_below_reserved"
                    elif (
                        new_strategy != saved.get("strategy", current_strategy)
                        or (
                            not pending_plugin_form
                            and candidate_config != saved.get(
                                "strategy_config", current_config
                            )
                        )
                    ) and (active or waiting):
                        errors["base"] = "strategy_in_use"
                except Exception:
                    errors["base"] = "storage_unavailable"

            if not errors:
                pending = {
                    CONF_MONITORED_ENTITIES: selected,
                    CONF_MAX_ACTIVE: new_limit,
                    CONF_STRATEGY: new_strategy,
                }
                if get_provider(new_strategy).config_fields:
                    if not getattr(self, "_strategy_config_ready", False):
                        self._pending_options = pending
                        return await self.async_step_strategy()
                    pending[CONF_STRATEGY_CONFIG] = self._validated_strategy_config
                    self._strategy_config_ready = False
                else:
                    pending[CONF_STRATEGY_CONFIG] = {}
                return self.async_create_entry(data=pending)

        schema = vol.Schema(
            {
                vol.Required(CONF_MAX_ACTIVE, default=new_limit): MAX_ACTIVE_SELECTOR,
                vol.Required(CONF_STRATEGY, default=new_strategy): strategy_selector(self.hass.config.language),
                vol.Optional(
                    CONF_MONITORED_ENTITIES, default=selected
                ): ENTITIES_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )

    async def async_step_strategy(self, user_input: dict | None = None):
        """Configure the selected provider before committing options."""
        pending = self._pending_options
        strategy = pending[CONF_STRATEGY]
        errors: dict[str, str] = {}
        current_strategy = self.config_entry.options.get(
            CONF_STRATEGY,
            self.config_entry.data.get(CONF_STRATEGY, DEFAULT_STRATEGY),
        )
        previous = (
            self.config_entry.options.get(
                CONF_STRATEGY_CONFIG,
                self.config_entry.data.get(CONF_STRATEGY_CONFIG, {}),
            )
            if current_strategy == strategy
            else {}
        )
        if user_input is not None:
            try:
                normalized = validate_strategy_config(strategy, user_input)
            except ValueError:
                errors["base"] = "invalid_strategy_options"
            else:
                self._validated_strategy_config = normalized
                self._strategy_config_ready = True
                # Revalidate under the runtime lock before persisting changes.
                result = await self.async_step_init(dict(pending))
                if result["type"] == "form" and result.get("step_id") == "init":
                    self._strategy_config_ready = False
                return result

        return self.async_show_form(
            step_id="strategy",
            data_schema=strategy_form_schema(
                strategy, user_input or previous, self.hass.config.language
            ),
            errors=errors,
        )
