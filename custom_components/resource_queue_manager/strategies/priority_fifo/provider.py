"""Self-contained priority FIFO module provider."""

from collections.abc import Mapping

from .config import CONFIG_FIELDS
from .request import REQUEST_FIELDS
from .strategy import PriorityFifoStrategy


class PriorityFifoProvider:
    """Register metadata, configure policy and construct isolated instances."""

    key = "priority_fifo"
    label = PriorityFifoStrategy.label
    description = (
        "Serve higher-priority waiting requests first, "
        "keeping arrival order for equal priority."
    )
    config_fields = CONFIG_FIELDS
    request_fields = REQUEST_FIELDS

    def create(
        self, config: Mapping[str, object] | None = None
    ) -> PriorityFifoStrategy:
        values = dict(config or {})
        return PriorityFifoStrategy(
            priority_order=values.get("priority_order", "highest_first")
        )
