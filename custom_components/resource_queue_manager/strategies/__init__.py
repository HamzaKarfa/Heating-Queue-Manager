"""Pluggable queue strategies and their service-provider registry."""

from .base import QueueStrategy, StrategyConfigField, StrategyProvider
from .request import QueueRequest
from .fifo import FifoProvider, FifoStrategy
from .lifo import LifoProvider, LifoStrategy
from .registry import (
    DEFAULT_STRATEGY,
    PROVIDERS,
    STRATEGIES,
    get_provider,
    get_strategy,
    validate_strategy_config,
    strategy_options,
)

__all__ = [
    "QueueStrategy",
    "QueueRequest",
    "StrategyConfigField",
    "StrategyProvider",
    "FifoProvider",
    "FifoStrategy",
    "LifoProvider",
    "LifoStrategy",
    "DEFAULT_STRATEGY",
    "PROVIDERS",
    "STRATEGIES",
    "get_provider",
    "get_strategy",
    "validate_strategy_config",
    "strategy_options",
]
