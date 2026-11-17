# Changelog

All notable changes to Resource Queue Manager are documented here.
Versions follow Semantic Versioning; the Home Assistant manifest version and
GitHub Release tag are intended to match (`1.0.0` ↔ `v1.0.0`).

## [1.0.0]

**Multi-instance and strategy-provider architecture.** Version 1 introduces
multiple independent queues, additional strategies, and domain-aware entity
supervision while preserving existing v0.4 FIFO entry and storage compatibility.

### Added

- Multiple independent, named Home Assistant configuration entries with
  separate capacities, supervised entities, saved state and diagnostic sensors.
- Pluggable `StrategyProvider` modules, with pure-Python strategies, configuration
  and request descriptors, and provider-driven Home Assistant forms.
- FIFO, non-preemptive LIFO, and Priority FIFO (configurable priority direction;
  stable FIFO ties for equal priority).
- `config_entry_id` targeting for every queue action and corresponding grant
  event identity.
- Provider-validated `strategy_data` in the `request` action, persisted in
  a new `request_data` field.
- French UI translation coverage and provider-owned translated labels.
- Domain-neutral entity selector for native `number`/`text` and helpers including
  `input_number`, `input_text` and `input_boolean`. ON/OFF devices remain guarded
  by observed OFF before release; other entities require a known state.
- Expanded English/French documentation, migration/rollback instructions and
  development guides.
- Tests covering strategy ordering, multiple entries, priority persistence,
  provider forms, v0.4 snapshot upgrades, logical entity supervision and release metadata.
- Manually gated `v1.0.0` GitHub release workflow.

### Changed

- Generic scheduling engine moved to `engine.py`; the obsolete `fifo.py` shim
  and standalone-import fallback have been removed. Tests import the real package.
- Existing singleton installations remain FIFO, but **once two or more entries
  are configured, all actions require `config_entry_id`**.
- HACS/manifest display name is now **Resource Queue Manager** without the
  FIFO-only suffix.
- Every entry remains paused after startup and options reload until an explicit
  validated `resume` for that entry.

### Important

- No physical entity switching; logical reservations are not electrical
  protections or a guaranteed power limiter.
- No active-reservation preemption, priority aging, global capacity, or automatic
  strategy migration.
- Rollback to v0.4 requires the matching Home Assistant backup.

See [v1.0.0 release notes](docs/releases/v1.0.0.md) and
[v0.4 → v1 migration guide](docs/MIGRATION_v0.4_to_v1.md).

## [0.4.0] — Initial public release

- Single persistent FIFO queue of logical reservations.
- Configurable capacity and explicitly supervised `light`/`switch` entities.
- Safe OFF-confirmed release, fail-closed manual restart recovery,
  four diagnostic sensors and slot-granted event.
- Domain change from legacy Heating Queue Manager.

See [v0.4.0 release notes](docs/releases/v0.4.0.md).
