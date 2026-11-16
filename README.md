<img width="154" height="154" alt="Logo RQ en flux bleu-cyan" src="https://github.com/user-attachments/assets/6e3b34af-3bfe-4f86-abae-321be968eeaf" />


# Resource Queue Manager (FIFO)

**Resource Queue Manager (FIFO)** is a Home Assistant custom integration that coordinates a configurable number of **simultaneous resource reservations** using a first-in, first-out (FIFO) queue.

The FIFO engine is generic. This version of the Home Assistant adapter supervises `light` and `switch` entities. Your **automations control the physical devices**; the integration never switches an entity on or off.

> **Experimental software scheduler, not a safety-rated electrical load-shedding system.** Independent loads, external automations and manual switches can bypass its reservations. Keep electrical and thermal safety protections in place.

## Features

- FIFO allocation with an adjustable concurrent reservation limit (1–50, initially 3).
- A **Configure** menu to select the exact `light` and `switch` entities supervised by the queue.
- A `resource_id` assigned to a monitored `entity_id` for each request.
- Persistent active reservations, FIFO order and entity bindings in Home Assistant's `.storage`.
- **Fail-closed recovery**: always reload in `paused` state; manual `resume` checks supervised entity states before granting reservations.
- Explicit `off` confirmation before releasing an active reservation.
- Four diagnostic sensors and a slot-granted event.

## Fresh installation

The integration folder is:

```text
custom_components/resource_queue_manager/
├── __init__.py
├── config_flow.py
├── const.py
├── coordinator.py
├── fifo.py
├── manifest.json
├── sensor.py
├── services.yaml
├── strings.json
├── translations/
└── brand/icon.png
```

Install through HACS as a custom integration repository, or copy the `resource_queue_manager` folder into Home Assistant's `config/custom_components`. Restart Home Assistant. Add **Resource Queue Manager (FIFO)** under **Settings → Devices & services**. Under **Configure**, select the supervised entities and maximum reservations. Both setup and Configure display the capacity as an editable **numeric input** (integer 1–50), rather than a slider; the form includes concise guidance for each setting. Verify the equipment and invoke:

```yaml
action: resource_queue_manager.resume
data: {}
```

Every startup/reload, including an options edit, leaves the queue `paused`; no new reservations are granted until manual `resume`. You cannot exclude an entity with an active or waiting request or reduce capacity below the current active count. Increasing the limit retains FIFO ordering and allocates additional slots after verification on `resume`.

## Actions and example

Request a reservation, without switching the device:

```yaml
action: resource_queue_manager.request
data:
  resource_id: chambre_1
  entity_id: light.relais_chauffage_chambre_1
```

Once the sensor's `active` attribute contains `chambre_1`, your heating automation can turn on the relay. After turning it OFF and confirming the Home Assistant state is `off`, release:

```yaml
action: resource_queue_manager.release
data:
  resource_id: chambre_1
```

Cancel a pending request or release an OFF resource:

```yaml
action: resource_queue_manager.cancel
data:
  resource_id: chambre_1
```

Every newly granted reservation fires `resource_queue_manager_slot_granted` with `resource_id`, `entity_id`, and `config_entry_id`. Use the sensor as the authoritative state if an automation may miss the event.

## Diagnostic sensors

| Default entity | Purpose |
| --- | --- |
| `sensor.resource_queue_active` | Current reservation count; `active` lists ordered resource IDs |
| `sensor.resource_queue_waiting` | Pending requests; `waiting` lists resource IDs |
| `sensor.resource_queue_available` | Available reservations; **0 when paused** |
| `sensor.resource_queue_status` | `paused` or `ready` |

Attributes include `monitored_entities`, `max_active`, and `recovery_issues`. Entity IDs may differ if Home Assistant detects existing name collisions.

## BREAKING CHANGE — replacing Heating Queue Manager

This project intentionally uses a **new integration domain** and does **not** migrate the old config entry or persisted queue data. If you remove the old integration and reinstall:

1. **Disable all automations calling `heating_queue_manager.*` first**, especially heater automations, and ensure relays are OFF before proceeding.
2. Delete the old integration under Home Assistant → Devices & services and remove the old custom component directory `custom_components/heating_queue_manager` (and its HACS entry if applicable).
3. Install the renamed `custom_components/resource_queue_manager`, restart Home Assistant, add and configure it with only the devices you intend to supervise. Check the actual relay states, then call `resource_queue_manager.resume`.
4. Update **all** old calls: `heating_queue_manager.request` → `resource_queue_manager.request`; `heating_queue_manager.release` → `resource_queue_manager.release`; similarly for `cancel` and `resume`.
5. Update fields `heater_id` → `resource_id` and `relay_entity_id` → `entity_id` in requests. Keep the `resource_id` value, such as `chambre_1`, unchanged if desired.
6. Update sensor references, e.g. `sensor.heating_queue_status` → `sensor.resource_queue_status`, and the `active`, `waiting`, and `available` sensors. The new event is `resource_queue_manager_slot_granted`.
7. Validate a complete grant/ON/OFF/release/idle-cancel cycle on **one low-risk test device** before enabling real heater automations.

**Your existing heating ON/OFF cycles remain in Home Assistant automation YAML.** This rename does not change 11/19-minute schedules, `repeat: until`, thermostats, or dedicated off/idle automations.

This version still requires a binary `light` or `switch` state; arbitrary sensors or other device domains cannot yet be reserved directly. The number of FIFO slots does **not** limit real-world loads outside the supervised list.

## Tests

```bash
python -m unittest discover -s tests -v
python -m pip install "pytest-homeassistant==2026.11.1"
python -m pytest -q tests/ha/test_integration.py
```

CI exercises both isolated Python code and Home Assistant 2026.11 config entries and services. Tests use simulated states, not physical loads.

## GitHub repository slug

The repository is presently hosted at [HamzaKarfa/Heating-Queue-Manager](https://github.com/HamzaKarfa/Heating-Queue-Manager). To rename its **GitHub URL** too, the repository owner must open **GitHub → Repository Settings → General → Repository name** and change it to `Resource-Queue-Manager`. The integration's manifest links still point to the current, valid GitHub URL until that action is completed.
