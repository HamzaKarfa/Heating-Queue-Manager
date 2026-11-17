"""Per-queue configuration for priority FIFO."""

from ..base import StrategyConfigField

CONFIG_FIELDS: tuple[StrategyConfigField, ...] = (
    StrategyConfigField(
        key="priority_order",
        label="Priority order",
        description="Choose whether larger or smaller priority numbers run first.",
        kind="select",
        required=True,
        default="highest_first",
        choices=("highest_first", "lowest_first"),
    ),
)
