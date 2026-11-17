"""FIFO plugin provider, similar to a Laravel service provider."""

from collections.abc import Mapping

from .config import CONFIG_FIELDS
from .request import REQUEST_FIELDS
from .strategy import FifoStrategy


class FifoProvider:
    """Describe, configure and instantiate the FIFO scheduling policy."""

    key = "fifo"
    label = FifoStrategy.label
    description = "First requested, first granted."
    config_fields = CONFIG_FIELDS
    request_fields = REQUEST_FIELDS

    def create(self, config: Mapping[str, object] | None = None) -> FifoStrategy:
        if config:
            raise ValueError("FIFO does not accept strategy-specific settings")
        return FifoStrategy()
