"""LIFO strategy plugin: policy, configuration and provider."""

from .provider import LifoProvider
from .strategy import LifoStrategy

__all__ = ["LifoProvider", "LifoStrategy"]
