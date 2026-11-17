"""Home Assistant adapter for strategy-defined configuration templates.

A provider describes settings using pure-Python StrategyConfigField objects.
Only this module imports Home Assistant and converts them into native selectors.
"""

import voluptuous as vol

from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .strategies import get_provider


def strategy_form_schema(
    strategy: str,
    previous: dict[str, object] | None = None,
) -> vol.Schema:
    """Build a strategy-specific form from the registered provider metadata."""
    previous = previous or {}
    schema: dict = {}

    for field in get_provider(strategy).config_fields:
        if field.kind == "text":
            selector = TextSelector(TextSelectorConfig())
        elif field.kind == "boolean":
            selector = BooleanSelector()
        elif field.kind == "number":
            selector = NumberSelector(
                NumberSelectorConfig(
                    min=field.minimum if field.minimum is not None else -1000000,
                    max=field.maximum if field.maximum is not None else 1000000,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            )
        elif field.kind == "select":
            selector = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=choice, label=choice)
                        for choice in field.choices
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            raise ValueError(f"Unsupported selector kind {field.kind!r}")

        default = previous.get(field.key, field.default)
        if field.required:
            marker = (
                vol.Required(field.key, default=default)
                if default is not None
                else vol.Required(field.key)
            )
        else:
            marker = (
                vol.Optional(field.key, default=default)
                if default is not None
                else vol.Optional(field.key)
            )
        schema[marker] = selector

    return vol.Schema(schema)
