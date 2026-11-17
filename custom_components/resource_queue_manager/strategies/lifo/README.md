# LIFO strategy provider

**Key:** `lifo` · **Policy:** last in, first out for waiting requests.

A new request is placed at the front of the waiting deque. When capacity is
released, the most recent waiter receives the grant. **Active reservations are
never interrupted.**

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

This strategy may starve older requests under a sustained stream of new work.
Use it only when last-arrived-first is appropriate. The core still requires an
OFF confirmation before releasing an active reservation.

See [strategy plugin architecture](../README.md) for extension details.
