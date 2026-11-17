# Strategy plugins

Each strategy is a self-contained module registered explicitly in
[`registry.py`](registry.py). Registration uses a `StrategyProvider`
contract, inspired by a Laravel service provider.

Each plugin folder contains:

- `provider.py`: stable key, label, optional localized labels,
  config/request field declarations, and factory for a fresh strategy.
- `strategy.py`: scheduling policy implementing
  `enqueue(waiting, request, requests)`.
- `config.py`: optional per-queue configuration fields, rendered as native
  Home Assistant selectors by `strategy_forms.py`.
- `request.py`: optional per-request metadata fields, validated before
  persistence and scheduling.

The generic `engine.py` owns active reservations, capacity, idempotency and
state recovery. The `coordinator.py` owns entity supervision and safe release.
**Strategy plugins never switch real devices or override safety checks.**

Installed strategies:

| Directory | Policy | Request fields | Queue settings |
| --- | --- | --- | --- |
| [fifo](fifo/README.md) | Oldest waiting first | None | None |
| [lifo](lifo/README.md) | Newest waiting first | None | None |
| [priority_fifo](priority_fifo/README.md) | Priority then FIFO ties | `priority` (1–10) | `priority_order` |

Read the [full developer guide](../../../docs/DEVELOPMENT.md) and
[v1 architecture](../../../docs/V1_ARCHITECTURE.md) before adding modules.

The registry is **explicit**: modules placed on disk are not executed
automatically, so untrusted strategy code cannot be loaded from user input.
