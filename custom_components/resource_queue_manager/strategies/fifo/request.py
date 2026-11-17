"""FIFO does not accept strategy-specific request parameters."""

from ..base import StrategyConfigField

REQUEST_FIELDS: tuple[StrategyConfigField, ...] = ()
