"""End-to-end tests through Home Assistant's config entries, services and states.

Unlike isolated FIFO tests, these tests exercise the actual Home Assistant
adapter, its sensor entities and its persistence using a local test instance.
No physical relays are connected or commanded.
"""

import asyncio

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "heating_queue_manager"


@pytest.fixture
async def queue_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Load one integration entry in an isolated Home Assistant test instance."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Heating Queue Manager",
        unique_id=DOMAIN,
        data={"max_active": 3},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for i in range(1, 6):
        hass.states.async_set(f"light.relay_{i}", "off")
    await hass.async_block_till_done()
    return entry


async def action(hass: HomeAssistant, operation: str, **data: str) -> None:
    """Call the public integration action with blocking=True."""
    await hass.services.async_call(DOMAIN, operation, data, blocking=True)
    await hass.async_block_till_done()


async def request(hass: HomeAssistant, index: int) -> None:
    await action(
        hass,
        "request",
        heater_id=f"h{index}",
        relay_entity_id=f"light.relay_{index}",
    )


def sensor(hass: HomeAssistant, metric: str):
    """Read the state through Home Assistant, not coordinator internals."""
    state = hass.states.get(f"sensor.heating_queue_{metric}")
    assert state is not None, f"Missing sensor.heating_queue_{metric}"
    return state


async def test_start_paused_then_resume(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """No allocation is possible before an explicit resume."""
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "available").state == "0"
    with pytest.raises(HomeAssistantError):
        await request(hass, 1)
    await action(hass, "resume")
    assert sensor(hass, "status").state == "ready"
    assert sensor(hass, "available").state == "3"


async def test_concurrent_requests_do_not_overallocate(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """A burst of five service calls must never reserve more than three slots."""
    await action(hass, "resume")
    await asyncio.gather(*(request(hass, i) for i in range(1, 6)))
    assert sensor(hass, "active").state == "3"
    assert sensor(hass, "waiting").state == "2"
    assert sensor(hass, "available").state == "0"
    assert len(sensor(hass, "active").attributes["active"]) == 3


async def test_release_promotes_oldest_waiting(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """FIFOs only admit a waiting heater after a confirmed OFF release."""
    await action(hass, "resume")
    for i in range(1, 6):
        await request(hass, i)

    assert sensor(hass, "waiting").attributes["waiting"] == ["h4", "h5"]
    await action(hass, "release", heater_id="h2")
    assert sensor(hass, "active").attributes["active"] == ["h1", "h3", "h4"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h5"]


async def test_reload_restores_order_without_regrant(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Reload the real config entry and verify its persistent state and pause."""
    await action(hass, "resume")
    for i in range(1, 6):
        await request(hass, i)

    before_active = sensor(hass, "active").attributes["active"]
    before_waiting = sensor(hass, "waiting").attributes["waiting"]

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()

    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "available").state == "0"
    assert sensor(hass, "active").attributes["active"] == before_active
    assert sensor(hass, "waiting").attributes["waiting"] == before_waiting

    await action(hass, "resume")
    assert sensor(hass, "status").state == "ready"
    await action(hass, "release", heater_id="h1")
    assert sensor(hass, "active").attributes["active"] == ["h2", "h3", "h4"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h5"]


async def test_recovery_refuses_unavailable_known_relay(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """A missing Zigbee report must block manual recovery."""
    await action(hass, "resume")
    await request(hass, 1)
    hass.states.async_set("light.relay_1", "unavailable")
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await action(hass, "resume")
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "active").state == "1"


async def test_recovery_refuses_orphaned_on_relay(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """A known ON relay without reservation is inconsistent."""
    await action(hass, "resume")
    await request(hass, 1)
    await action(hass, "release", heater_id="h1")
    hass.states.async_set("light.relay_1", "on")
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await action(hass, "resume")
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "available").state == "0"
