"""LIFO plugin configuration declaration.

The initial LIFO implementation does not require additional per-entry fields.
"""

from ..base import StrategyConfigField

CONFIG_FIELDS: tuple[StrategyConfigField, ...] = ()
