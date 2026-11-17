"""Immutable, framework-independent request view passed to scheduling policies."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueueRequest:
    """A logical reservation request with validated per-policy metadata."""

    resource_id: str
    data: Mapping[str, str | int | float | bool]
