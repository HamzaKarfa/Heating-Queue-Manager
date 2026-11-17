[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Marketplace](https://img.shields.io/badge/HACS-Marketplace-41BDF5)](https://hacs.xyz/)
[![Marketplace validation](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/validate.yml/badge.svg)](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/validate.yml)
[![Home Assistant tests](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/home-assistant-tests.yml/badge.svg)](https://github.com/HamzaKarfa/Resource-Queue-Manager/actions/workflows/home-assistant-tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

![Resource Queue Manager logo](assets/icon.png)

# Resource Queue Manager

**Resource Queue Manager** is a Home Assistant custom integration for coordinating **logical reservations** across multiple independently configured queues. Each queue owns its capacity, supervised entities, persistent state and scheduling strategy.

> **Release preparation — v1.0.0 development branch.** This README documents the code in `feat/v1-multi-queue-strategies`. Version 1.0.0 is **not yet published**. The Marketplace/default branch remains the stable v0.4 release until the PR is reviewed, merged and a GitHub Release is deliberately created. Do not use a heater or other safety-critical load as your first test.

> **Important:** Resource Queue Manager never switches devices ON or OFF. Your automations do that after obtaining a grant. It is **not a certified electrical load-shedding, thermal safety or overcurrent protection device**. Manual commands, external automation and unsupervised equipment can bypass it.

## What's new in v1

- **Multiple named queues** in one integration: e.g. Heating (capacity 3), Ventilation (2), Irrigation (1).
- **Independent strategies**, selected per queue during setup:
  - **FIFO** — oldest waiting request first (default and v0.4-compatible).
  - **LIFO** — newest waiting request first.
  - **Priority FIFO** — priority ranking with FIFO order for equal priorities.
- **Provider-based architecture**: each strategy ships its own `provider.py`, `config.py`, `request.py` and `strategy.py`. The core engine is not coupled to an algorithm.
- **Strategy-specific settings and request data** validated by the chosen provider.
- **Independent persistence and recovery**: every queue starts `paused` after reload and requires its own explicit `resume`.
- **Unambiguous service routing** with `config_entry_id` when multiple entries exist.
- Four read-only diagnostic sensors **per queue**, with strategy and entry ID in their attributes.

See [v1 architecture](docs/V1_ARCHITECTURE.md), [migration guide](docs/MIGRATION_v0.4_to_v1.md), [developer setup](docs/DEVELOPMENT.md) and [v1 release notes](docs/releases/v1.0.0.md).

## Scheduling example

Suppose a queue has **one** slot. Four requests arrive in this order: A, B, C, D. A is granted immediately and continues running; B/C/D are waiting.

| Strategy | Waiting order after A is granted | Next grant after A is released |
| --- | --- | --- |
| FIFO | B → C → D | B |
| LIFO | D → C → B | D |
| Priority FIFO | Sorted by priority, then arrival order | Highest-ranked waiter |

For Priority FIFO, let B have priority 4, C have priority 8 and D have priority 4. With the default `highest_first` option, the waiting order is **C → B → D**. With `lowest_first`, it is **B → D → C**. Equal-priority requests remain FIFO.

**All strategies are non-preemptive:** an already-active reservation is never revoked just because a more important request arrives. Priority FIFO can starve low-priority requests under sustained high-priority traffic; there is no aging or automatic priority escalation in v1.

## Installation

**Requirements:** Home Assistant **2026.11.0 or newer** and a working `light.*` or `switch.*` entity for each supervised device.

### Stable installation from Marketplace

Go to **Settings → Marketplace**, search for *Resource Queue Manager*, install and restart Home Assistant. If the repository is not visible, use the Marketplace's **Add from link** feature with `https://github.com/HamzaKarfa/Resource-Queue-Manager`.

**Until v1 is published, Marketplace installs the stable v0.4 release**, not the features in this README. Use the development steps below if you want to test the PR.

### Testing the v1 branch before release

Use a **separate Home Assistant test instance**, or make a full backup first and disable real-device automations. This branch is not an installable Marketplace release.

1. Browse [the v1 branch](https://github.com/HamzaKarfa/Resource-Queue-Manager/tree/feat/v1-multi-queue-strategies/custom_components/resource_queue_manager).
2. Copy the **whole** `custom_components/resource_queue_manager` directory from this branch into the test instance's `config/custom_components/resource_queue_manager`; do not mix files from v0.4 and v1.
3. Restart Home Assistant, then go to **Settings → Devices & services → Add integration → Resource Queue Manager**.
4. Add an entry and configure a **test lamp** or other low-risk entity. Repeat to test a second queue.
5. Confirm the queue's `status` sensor reads `paused`; inspect supervised entity states and explicitly call `resume` for that entry.
6. Exercise a request, an active grant, a waiting request, an OFF-verified release, a cancellation and a restart before using more complex automations.

Avoid overwriting a working HACS-managed installation with a feature branch on a production system. Restore the stable version from a backup if you decide not to continue testing.

### First configuration: one queue

When adding **Resource Queue Manager**, enter a unique queue name (e.g. *Heating*), the number of simultaneous reservations (1–50), a strategy and the `light`/`switch` entities supervised by that queue. You can add more entries afterward using **Add integration** again.

An entity may be supervised by **only one queue**, and each queue has its own capacity. There is **no shared electrical power limit** across queues.

Choosing **Priority FIFO** displays an additional provider-specific setup step:

| Setting | Values | Meaning |
| --- | --- | --- |
| `priority_order` | `highest_first` (default), `lowest_first` | Whether priority 10 or 1 wins first |

Each Priority FIFO request must contain `strategy_data.priority`, a numeric value from **1 to 10**. FIFO and LIFO do not accept `priority` or any other provider-specific request fields.

### Recovery: explicitly resume each queue

All queues are restored in `paused` state after Home Assistant startup, integration reload or options changes. Inspect supervised entities before resuming. Every supervised entity must report `on` or `off`; an entity reporting ON without an active reservation blocks recovery.

In **Developer tools → Actions**, select `resource_queue_manager.resume` and specify the queue:

```yaml
action: resource_queue_manager.resume
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
```

The `config_entry_id` is the Home Assistant **configuration entry ID**, not the queue name, entity ID or resource ID. The action editor offers a queue selector. The queue's status sensor must read `ready` before making requests.

With **exactly one configured queue**, old v0.4 calls with no `config_entry_id` still work. As soon as two or more queues are configured, **every** `request`, `release`, `cancel` and `resume` action must select its entry, even if the other entry is currently unloaded.

## Actions, events and safe reservation lifecycle

| Action | Required data | Optional data | Purpose |
| --- | --- | --- | --- |
| `resource_queue_manager.request` | `resource_id`, `entity_id` | `config_entry_id`, `strategy_data` | Acquire capacity or join a waiting queue |
| `resource_queue_manager.release` | `resource_id` | `config_entry_id` | Release only after the active device reports OFF |
| `resource_queue_manager.cancel` | `resource_id` | `config_entry_id` | Withdraw a waiting request or release an OFF reservation |
| `resource_queue_manager.resume` | — | `config_entry_id` | Validate supervised states and resume after reload |

Note that `config_entry_id` is effectively **required for all four actions when multiple queues exist**.

**Lifecycle:** Request → reservation becomes active or waits → automation confirms grant → automation switches device ON → automation switches device OFF → Home Assistant reports `off` → automation releases reservation → next waiting request is granted.

The integration fires `resource_queue_manager_slot_granted` with `resource_id`, `entity_id` and `config_entry_id` after persisting newly granted slots. Events are not replayed for existing grants. Use the relevant queue sensor's `active` attribute to verify a grant even if an event was missed.

### FIFO or LIFO request

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: demo_lamp
  entity_id: light.demo_lamp
```

### Priority FIFO request

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "YOUR_PRIORITY_QUEUE_ENTRY_ID"
  resource_id: bedroom
  entity_id: switch.bedroom_test_relay
  strategy_data:
    priority: 8
```

Priority must be supplied on **every new** Priority FIFO request. The same `resource_id` cannot change its entity binding or request priority while active/waiting; cancel or safely release it first. Unknown provider fields and out-of-range values are rejected.

### Release or cancel

After your automation switches a device OFF, **wait until Home Assistant reports `off`** before releasing:

```yaml
action: resource_queue_manager.release
data:
  config_entry_id: "YOUR_CONFIG_ENTRY_ID"
  resource_id: bedroom
```

Use `resource_queue_manager.cancel` with the same entry ID and resource ID to withdraw a waiting request. Cancellation of an active reservation also requires its entity to report OFF.

### Low-risk test automation

Create an `input_button.queue_demo` helper; supervise a real **test light** `light.demo_lamp` in your new queue. Find its actual **active sensor entity ID** under Devices & services → Entities (for example `sensor.heating_test_active`) and replace the placeholders below. Do not use this example on an unattended heater.

```yaml
alias: "Resource Queue v1 - test lamp"
mode: single
triggers:
  - trigger: state
    entity_id: input_button.queue_demo
actions:
  - action: resource_queue_manager.request
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"
      resource_id: demo_lamp
      entity_id: light.demo_lamp
      # For Priority FIFO only, add:
      # strategy_data:
      #   priority: 5
  - wait_template: >
      {{ 'demo_lamp' in (state_attr('sensor.YOUR_QUEUE_active', 'active') or []) }}
    timeout: "00:02:00"
    continue_on_timeout: true
  - if:
      - condition: template
        value_template: "{{ not wait.completed }}"
    then:
      - action: resource_queue_manager.cancel
        data:
          config_entry_id: "YOUR_CONFIG_ENTRY_ID"
          resource_id: demo_lamp
      - stop: "Timed out waiting for reservation"
  - action: light.turn_on
    target:
      entity_id: light.demo_lamp
  - delay: "00:00:15"
  - action: light.turn_off
    target:
      entity_id: light.demo_lamp
  - wait_template: "{{ is_state('light.demo_lamp', 'off') }}"
    timeout: "00:00:30"
    continue_on_timeout: false
  - action: resource_queue_manager.release
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"
      resource_id: demo_lamp
```

A stopped automation, lost connection or HA restart can leave a reservation active. This example is **not fault tolerant**; reconcile the actual device states and saved reservations before issuing `resume` or re-running a resource.

## Diagnostics and troubleshooting

Each entry owns four sensors. Newly added queues use their entry title in their sensor names. The **legacy v0.4 entry preserves** its existing Resource Queue sensor names and unique IDs. Check the actual entity IDs in Home Assistant; do not assume a name is fixed.

| Sensor (typical suffix) | State | Attributes |
| --- | --- | --- |
| `*_active` | Active reservation count | `active` (resource IDs) |
| `*_waiting` | Waiting request count | `waiting` (next-grant order) |
| `*_available` | Grantable slots; 0 if paused | `max_active` |
| `*_status` | `paused` or `ready` | `recovery_issues`, `monitored_entities` |

All sensors also expose `strategy`, `config_entry_id`, active/waiting IDs and safety state. Priority values are persisted internally as request metadata; the basic sensor lists remain **ID-only**.

| Symptom | Check |
| --- | --- |
| Action says `specify config_entry_id` | Two or more queues are configured; select the owning entry in **all** actions. |
| Queue is paused after restart or options change | Expected. Inspect supervised entities, then call `resume` on that queue. |
| `resume` refuses to run | Inspect the queue's `recovery_issues` attribute; fix missing/unavailable or unreserved ON entities. |
| `request` rejects `priority` | Priority goes inside `strategy_data` and is only supported by **Priority FIFO**. |
| Priority request fails for missing metadata | Provide `strategy_data: {priority: 1}` through `{priority: 10}` (inclusive). |
| Two queues cannot monitor the same relay | This is intentional. Assign each physical entity to one queue only. |
| Queue is not granting | Confirm its `status` is `ready`, its capacity and the OFF state of reserved devices. |
| A lower-priority request never runs | Priority FIFO is non-preemptive and does not have aging; frequent high-priority arrivals may cause starvation. |
| Changing strategy or configuration is refused | Empty the active and waiting lists safely before switching policies or provider-specific settings. |
| Release/cancel fails | An active reservation's entity must **report** `off`, not merely receive a turn-off action. |
| A grant event was missed | Read that specific queue's `active` sensor attribute. |

**Safety reminder:** reservation capacity does not measure electrical current or force devices OFF. Keep independent protection devices, thermal limits, and normal circuit protection.

## Upgrading from v0.4

The existing `resource_queue_manager` domain, config-entry ID, storage key, legacy FIFO ordering and old action names are retained. **There is no automatic strategy migration**: old entries default to FIFO. The v1 snapshot adds optional `strategy`, `strategy_config` and `request_data` fields. Old snapshots without these fields continue to load as FIFO.

Before adding a second entry, update existing automations to pass the legacy queue's **actual `config_entry_id`** on all four actions. Back up Home Assistant and disable real-equipment automations while testing. After the upgrade, verify the saved active/waiting lists and supervised entity states, then explicitly `resume` the original queue.

Read the [detailed v0.4 → v1 migration procedure](docs/MIGRATION_v0.4_to_v1.md). Migration from the **older `heating_queue_manager` integration** is separate: it used a different domain and is not automatic.

## Development, compatibility and release

```bash
python -m unittest discover -s tests -v
python -m pip install "pytest-homeassistant==2026.11.1"
python -m pytest -q tests/ha/test_integration.py
```

CI also validates HACS/Marketplace metadata and Home Assistant hassfest. Tests simulate Home Assistant states, **not physical devices**. See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for environment setup and plugin development.

This branch stages manifest version **1.0.0** for review. The version in `manifest.json` is the component version; the GitHub Release tag will be `v1.0.0` when explicitly published after merging. **No merge, tag or public release is performed by pushing these preparation commits.**

The repository is distributed under the [MIT License](LICENSE).
