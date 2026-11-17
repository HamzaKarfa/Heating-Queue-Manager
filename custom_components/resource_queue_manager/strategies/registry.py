"""Safe, explicit provider registry for configurable queue policies.

Only strategies registered by the integration are available to users. Plugins
provide pure-Python descriptors and new policy instances; they cannot bypass
the Home Assistant coordinator's safety and persistence boundaries.
"""

from collections.abc import Mapping

from .base import QueueStrategy, StrategyProvider
from .fifo.provider import FifoProvider
from .lifo.provider import LifoProvider

DEFAULT_STRATEGY = "fifo"

PROVIDERS: dict[str, StrategyProvider] = {
    "fifo": FifoProvider(),
    "lifo": LifoProvider(),
}

# Preserve existing membership tests until the form adapter uses get_provider.
STRATEGIES = PROVIDERS


def get_provider(key: str) -> StrategyProvider:
    """Return the provider registered under an immutable key."""
    try:
        return PROVIDERS[key]
    except (KeyError, TypeError) as err:
        raise ValueError(f"Unsupported queue strategy: {key!r}") from err


def validate_strategy_config(
    key: str, config: Mapping[str, object] | None = None
) -> dict[str, str | int | float | bool]:
    """Validate a JSON-safe, provider-specific options dictionary.

    Reject unknown keys and invalid types rather than silently dropping them.
    This prevents a provider version change from reinterpreting saved settings.
    """
    provider = get_provider(key)
    if config is None:
        config = {}
    if not isinstance(config, Mapping):
        raise ValueError("Strategy configuration must be a mapping")

    fields = {field.key: field for field in provider.config_fields}
    if len(fields) != len(provider.config_fields):
        raise ValueError(f"Duplicate configuration fields for strategy {key!r}")
    if len(set(config) - set(fields)):
        raise ValueError(
            f"Unsupported settings for strategy {key!r}: "
            + ", ".join(sorted(str(field) for field in set(config) - set(fields)))
        )

    result: dict[str, str | int | float | bool] = {}
    for field in provider.config_fields:
        if field.key in config:
            value = config[field.key]
        elif field.default is not None:
            value = field.default
        elif field.required:
            raise ValueError(f"Missing required setting: {field.key}")
        else:
            continue

        if field.kind == "text":
            if not isinstance(value, str):
                raise ValueError(f"{field.key} must be text")
        elif field.kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{field.key} must be a boolean")
        elif field.kind == "number":
            if type(value) not in (int, float):
                raise ValueError(f"{field.key} must be a number")
            if field.minimum is not None and value < field.minimum:
                raise ValueError(f"{field.key} is below its minimum")
            if field.maximum is not None and value > field.maximum:
                raise ValueError(f"{field.key} exceeds its maximum")
        elif field.kind == "select":
            if not isinstance(value, str) or value not in field.choices:
                raise ValueError(f"{field.key} must match a valid choice")
        else:
            raise ValueError(f"Unsupported setting type: {field.kind!r}")
        result[field.key] = value
    return result


def get_strategy(
    key: str, config: Mapping[str, object] | None = None
) -> QueueStrategy:
    """Build one isolated policy instance using validated per-entry settings."""
    normalized = validate_strategy_config(key, config)
    return get_provider(key).create(normalized)


def strategy_options() -> list[dict[str, str]]:
    """Expose policy choices from the same registry used by the engine."""
    return [
        {"value": provider.key, "label": provider.label}
        for provider in PROVIDERS.values()
    ]
