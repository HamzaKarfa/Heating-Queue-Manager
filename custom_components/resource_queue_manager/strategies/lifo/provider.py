"""LIFO strategy module provider."""

from collections.abc import Mapping

from .config import CONFIG_FIELDS
from .strategy import LifoStrategy


class LifoProvider:
    """Describe, configure and instantiate the LIFO scheduling policy."""

    key = "lifo"
    label = LifoStrategy.label
    description = "Newest waiting request is granted first; active work is never preempted."
    config_fields = CONFIG_FIELDS

    def create(self, config: Mapping[str, object] | None = None) -> LifoStrategy:
        if config:
            raise ValueError("LIFO does not accept strategy-specific settings")
        return LifoStrategy()
