"""Explicit registry of installed queue strategies.

Add a new policy by importing its implementation and registering an instance.
Keeping registration explicit avoids executing arbitrary strategy modules.
The Home Assistant selector uses the same registry; no UI changes are needed
for ordinary policies that use the existing enqueue contract.
"""

from .base import QueueStrategy
from .fifo import FifoStrategy
from .lifo import LifoStrategy

DEFAULT_STRATEGY = "fifo"

STRATEGIES: dict[str, QueueStrategy] = {
    "fifo": FifoStrategy(),
    "lifo": LifoStrategy(),
}


def get_strategy(key: str) -> QueueStrategy:
    """Load a registered strategy or fail instead of changing queue semantics."""
    try:
        return STRATEGIES[key]
    except (KeyError, TypeError) as err:
        raise ValueError(f"Unsupported queue strategy: {key!r}") from err
