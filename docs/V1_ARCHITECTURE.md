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

## Plugin architecture (service-provider model)

Each algorithm is a self-contained Python package. The host integration owns
physical-device safety, persistence, config-entry lifecycle and service routing;
the plugin supplies policy logic, registration metadata and configuration
descriptors. This intentionally resembles a Laravel service provider.

```text
custom_components/resource_queue_manager/
├── engine.py                  # Generic reservation engine
├── coordinator.py             # Safety, persistence data and entity bindings
├── config_flow.py             # Shared HA UI and entry options
├── strategy_forms.py         # Provider fields -> native HA selectors
├── sensor.py                  # Per-entry sensors
├── services.yaml              # Shared HA action declarations
└── strategies/
    ├── __init__.py
    ├── base.py                # QueueStrategy, StrategyProvider, config descriptors
    ├── registry.py            # Explicit provider registration and validation
    ├── request.py             # QueueRequest: ID plus validated metadata
    ├── fifo/
    │   ├── __init__.py
    │   ├── provider.py        # FifoProvider
    │   ├── config.py          # Strategy-specific configuration fields
    │   ├── request.py         # Per-request field declarations
    │   └── strategy.py        # FIFO algorithm
    └── lifo/
        ├── __init__.py
        ├── provider.py        # LifoProvider
        ├── config.py          # Strategy-specific configuration fields
        └── strategy.py        # LIFO algorithm
```

The dependency direction is **Home Assistant adapter → coordinator → engine → provider-created strategy**. The strategy packages themselves contain no Home Assistant imports. Every queue receives its **own instance** of the selected policy.

### Provider contract

`StrategyProvider` declares:

- `key`: stable identifier used in config entries and saved snapshots.
- `label` and `description`: user-facing metadata.
- `config_fields`: declarative entry-setting definitions owned by `config.py`.
- `request_fields`: optional per-request field definitions owned by `request.py`.
- `create(config)`: constructs a new policy instance using validated settings.

`QueueStrategy` now implements `enqueue(waiting, request, requests)`, where `request` is a `QueueRequest(resource_id, data)` and `requests` lets an algorithm inspect metadata of other queued resources. The engine consumes from the left of the waiting deque and always enforces capacity. FIFO/LIFO ignore request metadata; a custom algorithm can use it to reorder the queue without editing the engine.

`registry.py` explicitly registers provider instances. The Home Assistant strategy dropdown now reads its labels and values directly from the registry. This avoids adding hard-coded strategy names to `config_flow.py` every time another simple strategy is registered.

### Plugin-specific configuration and UI

The plugin's `config.py` declares `StrategyConfigField` descriptors; these can include required fields, defaults, numeric bounds and enum choices. Both current strategies declare no additional fields. The host's `strategy_forms.py` translates descriptors into **native Home Assistant selectors** for text, numbers, booleans and choices. It does not render custom HTML templates.

If a registered provider declares settings, setup and Options now present an additional **Strategy configuration** step. The host validates the submitted values with `validate_strategy_config()`, persists them under `strategy_config` in the entry and saved queue snapshot, and passes them into a new isolated policy instance on each setup/reload. Switching a strategy or its settings with active/waiting reservations is rejected.

For example, a future plugin could declare:

```python
CONFIG_FIELDS = (
    StrategyConfigField(
        key="default_priority",
        label="Default priority",
        kind="number",
        required=True,
        default=3,
        minimum=1,
        maximum=10,
    ),
)
```

Those fields would automatically appear in the host's additional strategy form. Each new plugin still needs appropriate English translation keys for its fields. Per-request fields are now declared separately through a plugin's `request.py` and `request_fields` provider attribute. The common Home Assistant `request` action exposes an **optional `strategy_data` object** whose keys are checked strictly against that selected provider's request schema. The engine receives a `QueueRequest(resource_id, data)` and persists non-empty data in a new `request_data` mapping alongside the existing ID-only `active`/`waiting` lists. Older snapshots missing `request_data` restore normally for FIFO/LIFO.

For a future priority plugin, a request could look like:

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "replace_with_config_entry_id"
  resource_id: bedroom
  entity_id: switch.heater_bedroom
  strategy_data:
    priority: 7
```

**This is a future-plugin example, not a currently supported FIFO/LIFO payload.** Both shipped policies intentionally reject unknown request metadata. No priority strategy is registered in this branch. A test-only strategy validates that priorities can reorder pending resources and survive a restart without changing the core engine. The host retains full control over state checks and does not actuate physical devices.

For richer per-request fields, adding Home Assistant labels to `services.yaml` remains a documentation/UI task; the stable extensibility interface is the validated `strategy_data` object. Provider-supplied code or services are **not automatically executed**.

### Adding an algorithm

1. Create a package in `strategies/<key>/`.
2. Add `strategy.py` with the pure scheduling logic and `config.py` with its optional settings.
3. Add `provider.py` implementing `StrategyProvider` and creating an independent strategy instance.
4. Register the provider in `strategies/registry.py`.
5. Add policy, persistence/restart and Home Assistant integration tests.
6. Declare per-request fields in `request.py` when needed; provide validation, serialization, ordering and upgrade tests before enabling the strategy.

Active reservations are never preempted. For current FIFO/LIFO policies the waiting deque stores requests in the order they will be granted. The v1 branch prohibits changing algorithms while active or waiting requests remain.

**Priority-based FIFO is not yet implemented.** Its per-request priority metadata, stable ties, storage migration and UI deserve a separate design pass. The present provider contract establishes module boundaries without claiming that all future strategies can be installed with zero host changes.

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
