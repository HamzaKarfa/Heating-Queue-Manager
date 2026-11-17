"""Explicit provider registry and schema validation for queue policies."""

from collections.abc import Mapping
from math import isfinite

from .base import QueueStrategy, StrategyConfigField, StrategyProvider
from .fifo.provider import FifoProvider
from .lifo.provider import LifoProvider
from .priority_fifo.provider import PriorityFifoProvider

DEFAULT_STRATEGY = "fifo"

# Only registered/bundled providers are loadable; never import arbitrary code
# based on a service payload or a saved config-entry value.
PROVIDERS: dict[str, StrategyProvider] = {
    "fifo": FifoProvider(),
    "lifo": LifoProvider(),
    "priority_fifo": PriorityFifoProvider(),
}
STRATEGIES = PROVIDERS  # Legacy config-flow membership alias.


def get_provider(key: str) -> StrategyProvider:
    try:
        return PROVIDERS[key]
    except (KeyError, TypeError) as err:
        raise ValueError(f"Unsupported queue strategy: {key!r}") from err


def _validate_fields(
    key: str,
    data: Mapping[str, object] | None,
    fields: tuple[StrategyConfigField, ...],
    purpose: str,
) -> dict[str, str | int | float | bool]:
    """Validate per-provider scalar fields, defaults and strict allowlists."""
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise ValueError(f"Strategy {purpose} must be a mapping")
    declared = {field.key: field for field in fields}
    if len(declared) != len(fields):
        raise ValueError(f"Duplicate {purpose} field for {key!r}")
    unknown = set(data) - set(declared)
    if unknown:
        raise ValueError(
            f"Unsupported {purpose} fields for {key!r}: "
            + ", ".join(sorted(str(field) for field in unknown))
        )

    result: dict[str, str | int | float | bool] = {}
    for field in fields:
        if field.key in data:
            value = data[field.key]
        elif field.default is not None:
            value = field.default
        elif field.required:
            raise ValueError(f"Missing required {purpose} field: {field.key}")
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
            if isinstance(value, float) and not isfinite(value):
                raise ValueError(f"{field.key} must be finite")
            if field.minimum is not None and value < field.minimum:
                raise ValueError(f"{field.key} is below its minimum")
            if field.maximum is not None and value > field.maximum:
                raise ValueError(f"{field.key} exceeds its maximum")
        elif field.kind == "select":
            if not isinstance(value, str) or value not in field.choices:
                raise ValueError(f"{field.key} must match a valid choice")
        else:
            raise ValueError(f"Unsupported field type: {field.kind!r}")
        result[field.key] = value
    return result


def validate_strategy_config(
    key: str, config: Mapping[str, object] | None = None
) -> dict[str, str | int | float | bool]:
    """Validate settings that belong to an entire queue instance."""
    return _validate_fields(key, config, get_provider(key).config_fields, "configuration")


def validate_request_data(
    key: str, data: Mapping[str, object] | None = None
) -> dict[str, str | int | float | bool]:
    """Validate metadata belonging to ONE resource request.

    No request may provide undeclared fields, and missing required values
    cannot become unvalidated persisted state.
    """
    return _validate_fields(
        key, data, getattr(get_provider(key), "request_fields", ()), "request"
    )


def get_strategy(
    key: str, config: Mapping[str, object] | None = None
) -> QueueStrategy:
    return get_provider(key).create(validate_strategy_config(key, config))


def strategy_options() -> list[dict[str, str]]:
    return [
        {"value": provider.key, "label": provider.label}
        for provider in PROVIDERS.values()
    ]
