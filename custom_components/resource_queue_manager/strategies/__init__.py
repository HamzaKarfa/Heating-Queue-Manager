"""Pluggable scheduling policies for the generic reservation engine."""

from .base import QueueStrategy
from .fifo import FifoStrategy
from .lifo import LifoStrategy
from .registry import DEFAULT_STRATEGY, STRATEGIES, get_strategy

__all__ = [
    "QueueStrategy",
    "FifoStrategy",
    "LifoStrategy",
    "DEFAULT_STRATEGY",
    "STRATEGIES",
    "get_strategy",
]
