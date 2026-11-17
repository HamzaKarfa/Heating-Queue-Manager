# Version 1 architecture — multiple queue managers

This document describes the **work-in-progress v1 refactor**. The published v0.4 release remains unchanged until tests, migration, and review are complete.

## Goals and boundaries

One Home Assistant integration can manage multiple independent configuration entries. Each entry owns:

- A user-defined name (Home Assistant entry title).
- A selected scheduling policy, initially `fifo` or `lifo`.
- A maximum concurrent reservation count (1–50).
- Its own supervised `light`/`switch` entities and four diagnostic sensors.
- An independent `.storage/resource_queue_manager.<config_entry_id>` snapshot, runtime lock, pause/recovery state and queue ordering.

**No entity may be supervised by two entries.** Queues do not share a global capacity. The integration does **not** switch physical devices.

## Modules

```text
custom_components/resource_queue_manager/
├── strategies.py   # QueueStrategy protocol, built-in policies, registry
├── engine.py       # ResourceQueue/QueueResult, generic reservation engine
├── fifo.py         # Legacy import compatibility shim
├── coordinator.py  # One queue's bindings, safety checks, storage serialization
├── config_flow.py  # Independent entry creation and per-entry options
├── __init__.py     # Home Assistant entry lifecycle, services, persistence
├── sensor.py       # Four read-only sensors per entry
└── services.yaml   # Explicit config-entry selector for actions
```

The direction of dependencies is: **HA adapter → coordinator → generic engine → strategy**. Strategy implementations must be pure Python and must not import Home Assistant.

### Strategy contract

Each strategy implements `QueueStrategy.enqueue(waiting, resource_id)`. The engine always consumes the left-most pending request. The persisted `waiting` array is therefore already ordered by the selected policy's *next grant*. For example:

- FIFO appends to the right, so the oldest request is granted first.
- LIFO prepends to the left, so the most recently queued request is granted first.

Already-active reservations are **never preempted**. A new policy can be added in a separate module, then registered in `STRATEGIES` in `strategies.py`, without changing the queue engine or Home Assistant action routing.

Priority-based FIFO will require a richer request model (priority metadata, stable FIFO ties, policy-specific snapshot migration and configuration). It is **not** implemented in this first v1 branch.

### Adding a new strategy

1. Implement a pure-Python class with a unique `key` and an `enqueue` method.
2. Register an instance in `STRATEGIES`.
3. Expose its name in the config-flow selector and translations.
4. Add pure engine/coordinator tests, persistence/restart tests, and HA integration tests.
5. Define what happens if a user switches strategy with active or waiting work. This first refactor prohibits switching until the queue is empty.

## Actions and backward compatibility

Actions: `resource_queue_manager.request`, `release`, `cancel`, `resume`. Each supports optional `config_entry_id`.

- Exactly one **configured** queue: existing v0.4 automations without `config_entry_id` keep working.
- Two or more configured queues: `config_entry_id` must be specified on **every** action, even if one entry is temporarily unloaded.
- A wrong or unloaded `config_entry_id` fails explicitly. No fallback is attempted.

Example:

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "replace_with_config_entry_id"
  resource_id: "living_room"
  entity_id: light.living_room_heater_relay
```

The grant event retains `config_entry_id` for consumers to distinguish queues. The sensor attributes expose the policy and owning entry ID.

## Migration and fail-closed behavior

- Existing v0.4 config entries and stored snapshots remain associated with their existing entry IDs.
- Old snapshots with no `strategy` field are interpreted as FIFO.
- On each start/reload every queue is restored in `paused` and requires its **own** explicit `resume` after supervised entity states have been checked.
- Active reservations cannot be silently lost; switching strategy with active/waiting work is rejected.
- Capacity cannot be lowered below active reservations; supervised entities in use cannot be removed.
- A monitored entity reporting `unknown`/`unavailable`, or ON without an active reservation, blocks recovery.
- Neither a scheduling policy nor a logical slot count constitutes an electrical safety or power-limiting system.

## Release gate

Before bumping `manifest.json` to `1.0.0` and publishing:

- [ ] Pure-Python engine and coordinator tests pass (FIFO, LIFO, recovery, invalid policy).
- [ ] Home Assistant 2026.11 integration tests pass with two independent config entries.
- [ ] HACS/Marketplace validation and hassfest pass.
- [ ] Manual setup, rename, options, entry removal and service-selector checks.
- [ ] Verify upgrades from a populated v0.4 queue do not lose saved reservations.
- [ ] Validate actual entity IDs and YAML examples in Home Assistant.
- [ ] Review English translations and documentation.
