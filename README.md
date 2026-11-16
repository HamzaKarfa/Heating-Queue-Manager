# Heating Queue Manager

A planned Home Assistant integration to schedule ON/OFF heating requests with a **FIFO (first-in, first-out)** queue and a configurable number of simultaneous reservations.

> **Status: experimental foundation — not yet suitable for controlling heaters.**
>
> This starter contains a tested reservation engine and a minimal Home Assistant configuration flow. It **does not** expose request/release actions, control devices, monitor relays, or guarantee any electrical limit. Do not rely on it for electrical safety.

## Scope

- Preserve existing thermostats (ESPHome, Generic Thermostat, etc.) and their ON/OFF cycles.
- Reserve at most N heating slots; every request either receives a slot or waits.
- On confirmed release, promote the oldest pending request.
- Avoid bypasses: the future HA adapter will be the single authorization point.

## What is implemented

- Pure Python FIFO engine in `custom_components/heating_queue_manager/fifo.py`.
- Idempotent requests, cancellation and release, FIFO promotion, snapshots.
- Minimal Home Assistant config flow to set max simultaneous reservations.
- FIFO coordinator, three action endpoints and read-only monitoring sensors (Sprint 1 experimental).
- Isolated unit tests, which do not require Home Assistant.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Integration layout

```text
custom_components/heating_queue_manager/
  __init__.py
  config_flow.py
  const.py
  fifo.py
  manifest.json
  translations/
    en.json
    fr.json
hacs.json
README.md
tests/test_fifo.py
.github/workflows/tests.yml
```

## Sprint 1 — FIFO coordinator (experimental)

A Home Assistant adapter now offers the actions:

- `heating_queue_manager.request` with `heater_id` and `relay_entity_id`.
- `heating_queue_manager.release` with `heater_id` (refused unless HA reports the bound relay `off`).
- `heating_queue_manager.cancel` with `heater_id` (waiting requests are removed; reserved requests require relay `off`).

Example action:

```yaml
- action: heating_queue_manager.request
  data:
    heater_id: ch1
    relay_entity_id: light.relais_chauffage_chambre_1
```

When capacity is available, the integration fires a `heating_queue_manager_slot_granted` event with `heater_id`, `relay_entity_id` and `config_entry_id`. The three read-only sensor entities **Heating Queue Active**, **Heating Queue Waiting** and **Heating Queue Available** expose counts; each exposes `active` and `waiting` lists in its attributes. Wait templates should check membership in the `active` attribute rather than relying solely on events, to avoid missed grants.

**Do not connect these actions to real heaters yet.** These actions reserve *logical* slots only: they never switch or command any physical relays. They do not implement heartbeat/lease timeouts, durable reservations, startup relay reconciliation, or watchdog intervention. Reservations exist only in memory and reset when the integration reloads or Home Assistant restarts. A software queue does not enforce a physical electrical limit or prevent unrelated automations/manual control from switching devices on. There is currently no claim of fail-safe behavior after HA crashes, Zigbee delays, or manually switched relays. Relay `off` confirmation is only Home Assistant's last reported state, not an independent electrical measurement.

## Next implementation steps

1. Add integration-level Home Assistant tests for service registration, sensor updates and config entry reload/unload.
2. Add startup reconciliation and a conservative recovery mode before enabling relay switching.
3. Handle connection loss, relay reporting delays, cancellations, stale reservations and crash recovery.
4. Add optional diagnostics and a safe way to preview the FIFO without real heaters.
5. Document a verified HA automation integration and release for Marketplace testing.

## Safety boundaries

This is a **software scheduler**, not a circuit breaker, fuse, overload protector, temperature limiter, or safety-rated device. Disconnected Home Assistant, delayed Zigbee reports, manually operated relays, and unexpected device restoration are outside a scheduler's immediate control. Keep appropriate electrical protections in place.
