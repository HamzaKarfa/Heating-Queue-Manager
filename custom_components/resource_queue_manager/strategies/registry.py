"""Explicit service-provider registry for queue strategies.

A strategy module exposes a provider describing its user-facing metadata,
configuration contract and scheduling implementation. Registration is explicit
and deterministic; no arbitrary modules are imported from user input.
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

# Legacy membership checks in Home Assistant config flows.
STRATEGIES = PROVIDERS


def get_provider(key: str) -> StrategyProvider:
    """Resolve a registered plugin by its stable key."""
    try:
        return PROVIDERS[key]
    except (KeyError, TypeError) as err:
        raise ValueError(f"Unsupported queue strategy: {key!r}") from err


def get_strategy(
    key: str, config: Mapping[str, object] | None = None
) -> QueueStrategy:
    """Create a new strategy instance (never share mutable policy state)."""
    return get_provider(key).create(config)


def strategy_options() -> list[dict[str, str]]:
    """Expose policy choices using the same registry as the engine."""
    return [
        {"value": provider.key, "label": provider.label}
        for provider in PROVIDERS.values()
    ]
