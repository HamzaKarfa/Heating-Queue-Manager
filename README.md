# Heating Queue Manager

A custom Home Assistant integration to schedule on/off heating requests using a **FIFO (first-in, first-out)** queue with a configurable number of simultaneous reservations.

> **Experimental — do not connect to physical heater automations yet.** The integration reserves *logical* slots only; it never switches relays. It is not a safety-rated load-shedding device.

## Design principles

- Respect existing thermostats (ESPHome, Generic Thermostat, etc.) and their independent ON/OFF cycles.
- Reserve up to N simultaneous slots; remaining requests stay in FIFO order.
- Release a reserved slot only when Home Assistant **reports** its relay OFF.
- Persist FIFO order, active reservations and known relay mappings across Home Assistant restarts.
- **Always start paused after restart**, even if a snapshot was restored successfully. Resume explicitly only after inspecting the physical installation.

## Repository layout

```text
custom_components/heating_queue_manager/
  __init__.py          # HA adapter, Store, serialized actions
  fifo.py              # Pure-Python FIFO
  coordinator.py       # Heater/relay bindings and recovery checks
  sensor.py            # Read-only queue/status sensors
  config_flow.py       # Setup form
  const.py             # Domain, service and event names
  manifest.json
  services.yaml
  strings.json
  translations/en.json
  translations/fr.json
tests/
  test_fifo.py
  test_coordinator.py
  test_recovery.py
.github/workflows/tests.yml
hacs.json
```

## Installation and configuration

Copy the `custom_components/heating_queue_manager` folder into the Home Assistant `config/custom_components` directory (or install as a custom Marketplace repository). Restart Home Assistant, then add the integration from **Settings → Devices & services**. Choose the maximum number of simultaneous reservations.

This experimental version adds four sensors:

| Sensor | Meaning |
| --- | --- |
| `sensor.heating_queue_active` | Reserved slots |
| `sensor.heating_queue_waiting` | Pending FIFO requests |
| `sensor.heating_queue_available` | Slots that can be granted *now* (0 while paused) |
| `sensor.heating_queue_status` | `paused` / `ready` |

Sensor IDs may differ if Home Assistant has created a suffix. Attributes `active` and `waiting` expose the heater IDs in their current order. The `recovery_issues` attribute lists detected issues (it only checks previously known relays).

## Startup recovery: an explicit safety gate

When the integration starts, it loads its previously saved state from Home Assistant's `.storage` using `Store`. A config entry has its own storage key. **A missing or invalid snapshot never creates usable free slots automatically.** An invalid/corrupt snapshot prevents the config entry from loading; it is not silently replaced with an empty queue.

A valid snapshot restores active reservations and FIFO ordering **without firing new grant events**. The queue remains `paused` until the operator has checked the installation and explicitly invokes:

```yaml
action: heating_queue_manager.resume
data: {}
```

The action checks the Home Assistant states of *previously known* relays:
- `unknown`, `unavailable` or missing relay state blocks resume.
- A known relay `on` with no matching active reservation blocks resume.
- An `on` relay that is already reserved keeps its place; it is **not** released.
- An `off` relay with an active reservation remains reserved until a separate `release`.

A **new installation or upgrade from the pre-persistence version** has no prior snapshot: the queue starts empty **and paused**, and Home Assistant cannot automatically discover loads controlled outside this integration. The operator must verify that the system is safe before invoking `resume`. The integration does not discover relays that have never been registered.

> **Important:** Home Assistant's `off` state is not proof of a physically de-energized circuit. Zigbee reporting may be stale or delayed. The integration also cannot prevent relay actions that bypass the queue, including manual switching and separate automations.

## Queue actions

After `resume` succeeds, request a reservation:

```yaml
action: heating_queue_manager.request
data:
  heater_id: ch1
  relay_entity_id: light.relais_chauffage_chambre_1
```

Release after the relay is OFF:

```yaml
action: heating_queue_manager.release
data:
  heater_id: ch1
```

Cancel a pending request, or cancel an already reserved heater **only after the relay is OFF**:

```yaml
action: heating_queue_manager.cancel
data:
  heater_id: ch1
```

Accepted grants fire the event `heating_queue_manager_slot_granted` with `heater_id`, `relay_entity_id` and `config_entry_id`. Scripts should also check the `active` attribute of the queue sensor to avoid missing events.

Action handlers use an `asyncio.Lock` and wait for `Store.async_save()` **before publishing grants**. If storage fails, the queue pauses and no new grant event is emitted. Restored states are not a command to automatically energize a heater.

## Run the tests

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs pure-Python tests against Python 3.13 and 3.14. A separate workflow now runs six additional integration tests through real Home Assistant services and config-entry reloads against Home Assistant 2026.11 using the matching `pytest-homeassistant` package. They use simulated relay states and never command an actual heater.

To run the Home Assistant integration tests locally, use Python 3.14.2+ in a dedicated virtual environment:

```bash
python -m pip install "pytest-homeassistant==2026.11.1"
python -m pytest -q tests/ha/test_integration.py
```

The integration suite exercises: startup pause/resume, a concurrent request burst, FIFO promotion, stored queue restoration on config-entry reload, unavailable relays and unreserved ON relays. A successful test suite does **not** prove safe control of the physical installation.

## Next steps

1. Add Home Assistant integration tests for actions, storage failure, entity updates, and reload.
2. Add automatic relay monitoring and diagnostics for mismatched states.
3. Support recovery of pending heating cycles, explicit configuration of controlled relays, and a watchdog.
4. Implement and test integration with existing thermostat scripts **without direct relay bypass**.
5. Evaluate optional weighted (watts) budgets and priority policies *after* the fixed-slot FIFO is stable.

## Safety boundaries

This is a **software scheduler**, not a fuse, breaker, contactor safety interlock, over-temperature cutoff, or independent power meter. A crash, power outage, Zigbee delay, or manually switched relay can bypass its logical limits. Keep all appropriate electrical protections and independent thermal protections installed.
