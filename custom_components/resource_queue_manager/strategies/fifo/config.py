"""FIFO plugin configuration declaration.

FIFO does not need additional settings beyond shared capacity and monitored
entities. Future plugins can declare specific fields in this module.
"""

from ..base import StrategyConfigField

CONFIG_FIELDS: tuple[StrategyConfigField, ...] = ()
