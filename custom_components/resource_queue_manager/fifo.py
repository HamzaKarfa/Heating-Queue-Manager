"""Backward-compatible import path for the legacy FIFO module.

The generic engine now lives in engine.py. This shim keeps older tests and
third-party pure-Python imports working without changing their behavior.
"""

if __package__:
    from .engine import QueueResult, ResourceQueue
else:
    from engine import QueueResult, ResourceQueue

__all__ = ["QueueResult", "ResourceQueue"]
