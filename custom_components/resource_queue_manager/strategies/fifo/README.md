# FIFO strategy provider

**Key:** `fifo` · **Policy:** first in, first out.

The oldest pending request is promoted when a verified OFF release frees a
reservation. The generic engine guarantees the capacity limit. Already-active
reservations are never preempted.

**Provider files:** [provider.py](provider.py), [strategy.py](strategy.py),
[config.py](config.py), [request.py](request.py).

**Config fields:** none. **Request metadata fields:** none.

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: demo
  entity_id: light.demo_lamp
```

This is the default strategy and the migration target for legacy v0.4 queues.
See the [top-level README](../../../../README.md) for safe setup and the
[upgrade guide](../../../../docs/MIGRATION_v0.4_to_v1.md).
