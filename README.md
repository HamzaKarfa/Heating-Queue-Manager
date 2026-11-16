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

## Next implementation steps

1. Register Home Assistant `request` and `release` actions and expose authorized/pending state through entities.
2. Coordinate all actions in one event-loop owner so no two requests can claim the same slot.
3. Verify a heater's relay is OFF before releasing the corresponding reservation; process cancellations, unavailable relays and restart reconciliation.
4. Add end-to-end Home Assistant tests and integration diagnostics.
5. Document safe installation and release a version for Marketplace testing.

## Safety boundaries

This is a **software scheduler**, not a circuit breaker, fuse, overload protector, temperature limiter, or safety-rated device. Disconnected Home Assistant, delayed Zigbee reports, manually operated relays, and unexpected device restoration are outside a scheduler's immediate control. Keep appropriate electrical protections in place.
