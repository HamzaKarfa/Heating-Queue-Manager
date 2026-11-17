# Migrating Resource Queue Manager v0.4 → v1.0.0

> **Release candidate guidance.** These steps describe the v1 development branch
> and should first be rehearsed in a separate Home Assistant test instance.
> The v1.0.0 GitHub Release has not yet been published.

This is an **in-place upgrade** for existing `resource_queue_manager` installations.
It is **not** a migration from the legacy `heating_queue_manager` domain.

## What stays compatible

- Domain: `resource_queue_manager`.
- Services/actions: `request`, `release`, `cancel`, `resume`.
- Service fields: `resource_id` and `entity_id`.
- Slot-granted event: `resource_queue_manager_slot_granted`.
- Existing config entry ID and `.storage/resource_queue_manager.<config_entry_id>`.
- Saved active and waiting IDs and resource/entity bindings.
- Existing FIFO ordering and capacity, unless **you** change them.
- Unique IDs of existing queue sensors.

Legacy snapshots without `strategy`, `strategy_config` or `request_data`
are interpreted as FIFO with empty strategy-specific settings and metadata.

## Changes that require attention

| Area | v0.4 | v1 |
| --- | --- | --- |
| Queue instances | One | Several independent named entries |
| Strategy | FIFO | FIFO, LIFO, Priority FIFO |
| Action routing | Implicit singleton | Required `config_entry_id` once **two or more entries are configured** |
| Queue settings | Capacity/entities | Plus strategy and optional plugin configuration |
| Request settings | IDs only | Optional provider-validated `strategy_data`; priority required for Priority FIFO |
| Sensor names | Existing Resource Queue sensors | Legacy IDs retained; new entries use their names |
| Startup/reload | Paused | **Each** entry paused until explicitly resumed |

A second queue being temporarily unloaded does not make implicit service routing safe:
the config-entry ID is required based on the **number of configured entries**,
not just the number currently loaded.

## Before upgrading

1. **Back up Home Assistant** including `.storage`, the custom component, and automations.
2. Record the current four diagnostic sensor entity IDs, the **active** list, the **waiting** list, supervised entities and the original entry ID.
3. Disable automations controlling actual heating or other high-power equipment, ensure equipment is in a safe physical state, and do not rely on software reservations for electrical safety.
4. If possible, rehearse the migration with a low-risk test lamp on a separate installation. Do not replace individual files in a live running integration.
5. Confirm Home Assistant is **2026.11.0 or newer**.

## Upgrade procedure

1. Install the **complete** v1 component directory (development branch for testing, or the eventual v1 Marketplace release). Do not mix versions.
2. Restart Home Assistant. The original queue must load in `paused` state; saved active/waiting reservations should still be visible.
3. Verify its strategy is **FIFO** and that monitored entity bindings and sensor IDs remain intact.
4. Inspect all physical entities and the `recovery_issues` attribute. Never treat a restored reservation as permission to switch an unknown device ON.
5. Explicitly resume the **original entry** using `resource_queue_manager.resume`.
6. Verify an OFF-confirmed release and the next FIFO grant using a noncritical test device.

**Do not add a second entry until existing automations have been updated.**
Once two configured entries exist, legacy actions without `config_entry_id`
fail rather than guess which queue to change.

### Update existing automation actions

Include the original entry ID on every call:

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "ORIGINAL_ENTRY_ID"
  resource_id: bedroom
  entity_id: light.bedroom_test_relay
```

```yaml
action: resource_queue_manager.release
data:
  config_entry_id: "ORIGINAL_ENTRY_ID"
  resource_id: bedroom
```

Do the same for `cancel` and `resume`. The editor under
**Developer tools → Actions** offers a configuration-entry selector.

If an automation listens for `resource_queue_manager_slot_granted`,
also filter the event's `config_entry_id` when multiple queues are configured.
Sensors belong to specific entries; update templates that inadvertently
read a different queue's sensor.

### Add a new queue

1. Go to **Settings → Devices & services → Add integration → Resource Queue Manager**.
2. Give it a unique name; select strategy, capacity and supervised Home Assistant entities (native domains and helpers are accepted). For electrical actuators, keep explicit ON/OFF supervision and hardware protections.
3. Do not assign an entity already supervised by another queue.
4. Configure the Priority FIFO `priority_order` if relevant.
5. Find the new queue's sensor IDs; check `paused` and `recovery_issues`; resume this **new** entry only after inspection.
6. Supply its entry ID on every related action.

Priority FIFO requests must use `strategy_data.priority` (number 1–10).
Equal priority levels remain FIFO. A new request cannot change the priority of
an existing reservation. No current strategy preempts an active reservation.

## Changing strategies and capacity

A queue must have **no active or waiting work** before switching its algorithm
or provider-specific settings. Cancel waiting requests and finish/release active
reservations **only after the entities report OFF**. You cannot remove an entity
still bound to a reservation or reduce capacity below the active count.

Changing options triggers a reload and sets that queue to `paused`. Inspect
equipment and call `resume` again. Do not delete storage files to force a
strategy change: doing so discards safety-relevant reservation records.

## Rollback plan

If a test reveals an issue, stop new work, make physical equipment safe and
disable affected automations. Restore the **matching pre-upgrade backup of the
component, config entries and `.storage`** before restarting v0.4.

**Important:** v1 writes additional fields and can manage multiple entries.
A downgrade without restoring its matching backup is **not a supported or
tested migration**; it could misinterpret or lose queued reservations.

## From the older Heating Queue Manager

`heating_queue_manager` and `resource_queue_manager` are different
integration domains. There is no automatic conversion. Disable old automations,
make devices safe, remove the old component, install Resource Queue Manager,
configure the new entry, and update service/field/event/sensor references:

- `heating_queue_manager.*` → `resource_queue_manager.*`
- `heater_id` → `resource_id`
- `relay_entity_id` → `entity_id`

Start with a low-risk test device and manually resume only after inspection.

## Go / no-go checklist

- [ ] Original v0.4 reservations/bindings survived in-place upgrade.
- [ ] Existing FIFO automations work with one configured entry.
- [ ] Original service calls were updated with `config_entry_id` before adding a second.
- [ ] Two queues remain isolated through requests, grants, restart and release.
- [ ] Sensors and event filtering refer to the intended queue.
- [ ] Strategy change with pending work is refused.
- [ ] Manual `resume` is required after restart and options reload.
- [ ] Return-to-v0.4 backup restoration has been rehearsed.
- [ ] Actual loads retain independent hardware protection.
