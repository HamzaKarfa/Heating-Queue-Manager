"""FIFO strategy plugin: policy, configuration and provider."""

from .provider import FifoProvider
from .strategy import FifoStrategy

__all__ = ["FifoProvider", "FifoStrategy"]
