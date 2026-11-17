"""Required per-request priority value for priority FIFO."""

from ..base import StrategyConfigField

REQUEST_FIELDS: tuple[StrategyConfigField, ...] = (
    StrategyConfigField(
        key="priority",
        label="Request priority",
        description="Numeric priority level from 1 to 10.",
        kind="number",
        required=True,
        minimum=1,
        maximum=10,
    ),
)
