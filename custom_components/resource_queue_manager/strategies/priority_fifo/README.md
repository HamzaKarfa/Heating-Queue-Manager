# Priority FIFO strategy provider

**Key:** `priority_fifo` · **Policy:** sort waiting requests by priority,
then FIFO for equal priorities. Active reservations are not preempted.

This plugin demonstrates the complete provider contract:

- [provider.py](provider.py) — metadata, configuration/request contracts,
  factory and optional French label metadata.
- [config.py](config.py) — per-queue `priority_order`:
  `highest_first` (default; 10 before 1) or `lowest_first` (1 before 10).
- [request.py](request.py) — required numeric `priority` from 1 to 10.
- [strategy.py](strategy.py) — stable ordering algorithm using the generic
  queue request model.

Home Assistant adds a **Strategy configuration** screen when this provider is
selected. Its request service uses the common `strategy_data` object:

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_PRIORITY_QUEUE_ENTRY_ID"
  resource_id: bedroom
  entity_id: switch.bedroom_test_relay
  strategy_data:
    priority: 8
```

A duplicate request cannot mutate an existing booking's priority: first safely
cancel/release it, then submit a new request. The request data is saved alongside
the active/waiting order and restored on HA restart. A queue always restores
in `paused` until explicit `resume` after supervised-state checks.

**Limitation:** no priority aging or fairness algorithm yet. Frequent
high-priority arrivals can cause long waits for low-priority requests.

See [strategy plugin architecture](../README.md) and the
[release guide](../../../../docs/releases/v1.0.0.md).
