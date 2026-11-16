"""End-to-end tests through Home Assistant's config entries, services and states.

Unlike isolated FIFO tests, these tests exercise the actual Home Assistant
adapter, its sensor entities and its persistence using a local test instance.
No physical entities are connected or commanded.
"""

import asyncio

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

DOMAIN = "resource_queue_manager"


@pytest.fixture
async def queue_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Load one integration entry in an isolated Home Assistant test instance."""
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Resource Queue Manager (FIFO)",
        unique_id=DOMAIN,
        data={"max_active": 3},
        options={"monitored_entities": [f"light.relay_{i}" for i in range(1, 6)]},
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
        resource_id=f"h{index}",
        entity_id=f"light.relay_{index}",
    )


def sensor(hass: HomeAssistant, metric: str):
    """Read the state through Home Assistant, not coordinator internals."""
    state = hass.states.get(f"sensor.resource_queue_{metric}")
    assert state is not None, f"Missing sensor.resource_queue_{metric}"
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
    """FIFOs only admit a waiting resource after a confirmed OFF release."""
    await action(hass, "resume")
    for i in range(1, 6):
        await request(hass, i)

    assert sensor(hass, "waiting").attributes["waiting"] == ["h4", "h5"]
    await action(hass, "release", resource_id="h2")
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
    await action(hass, "release", resource_id="h1")
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
    """A known ON entity without reservation is inconsistent."""
    await action(hass, "resume")
    await request(hass, 1)
    await action(hass, "release", resource_id="h1")
    hass.states.async_set("light.relay_1", "on")
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(queue_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await action(hass, "resume")
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "available").state == "0"



async def test_options_form_reconfigures_supervised_relays(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """The Configure UI persists selection and reloads the entry paused."""
    form = await hass.config_entries.options.async_init(queue_entry.entry_id)
    assert form["type"] is not None
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": ["light.relay_1"]}
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()

    assert queue_entry.options["monitored_entities"] == ["light.relay_1"]
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "status").attributes["monitored_entities"] == [
        "light.relay_1"
    ]

    hass.states.async_set("light.relay_3", "on")
    await hass.async_block_till_done()
    await action(hass, "resume")
    assert sensor(hass, "status").state == "ready"
    await request(hass, 1)
    assert sensor(hass, "active").state == "1"
    with pytest.raises(HomeAssistantError, match="not supervised"):
        await request(hass, 3)


async def test_options_form_rejects_removal_of_active_reservation(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """An existing slot must not vanish when a entity is deselected."""
    await action(hass, "resume")
    await request(hass, 3)

    form = await hass.config_entries.options.async_init(queue_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": ["light.relay_1"]}
    )
    assert result["type"].value == "form"
    assert result["errors"]["base"] == "entities_in_use"
    assert "light.relay_3" in queue_entry.options["monitored_entities"]
    assert sensor(hass, "active").state == "1"


async def test_options_form_rejects_removal_of_waiting_request(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """A waiting queue entry is just as protected as an active booking."""
    await action(hass, "resume")
    for i in range(1, 5):
        await request(hass, i)
    assert sensor(hass, "waiting").state == "1"

    form = await hass.config_entries.options.async_init(queue_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": [
            "light.relay_1", "light.relay_2", "light.relay_3"
        ]}
    )
    assert result["errors"]["base"] == "entities_in_use"


async def test_legacy_stored_history_ignored_after_explicit_selection(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """An old released test entity must not prevent migration to one resource."""
    runtime = hass.data[DOMAIN][queue_entry.entry_id]
    snapshot = runtime.manager.export_state()
    snapshot["known_relays"] = {"old_ch3": "light.relay_3"}
    await runtime.store.async_save(snapshot)

    form = await hass.config_entries.options.async_init(queue_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"monitored_entities": ["light.relay_1"]}
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    hass.states.async_set("light.relay_3", "on")
    await hass.async_block_till_done()
    await action(hass, "resume")
    assert sensor(hass, "status").state == "ready"


async def test_edit_max_slots_from_options_and_persist(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    """Changing 3 to 2 preserves the configuration across reloads."""
    form = await hass.config_entries.options.async_init(queue_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            "max_active": 2,
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert queue_entry.options["max_active"] == 2
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "status").attributes["max_active"] == 2

    await action(hass, "resume")
    assert sensor(hass, "available").state == "2"
    for i in range(1, 4):
        await request(hass, i)
    assert sensor(hass, "active").attributes["active"] == ["h1", "h2"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h3"]

    # Opening Configure again must preserve the edited max as its default.
    reopened = await hass.config_entries.options.async_init(queue_entry.entry_id)
    assert reopened["type"].value == "form"


async def test_options_reject_limit_below_existing_active_reservations(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    await action(hass, "resume")
    for i in range(1, 4):
        await request(hass, i)

    flow = await hass.config_entries.options.async_init(queue_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 2,
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert result["type"].value == "form"
    assert result["errors"]["base"] == "max_active_below_reserved"
    assert queue_entry.options.get("max_active") is None
    assert sensor(hass, "active").state == "3"


async def test_increase_max_with_waiters_promotes_only_on_resume(
    hass: HomeAssistant, queue_entry: MockConfigEntry
) -> None:
    await action(hass, "resume")
    for i in range(1, 6):
        await request(hass, i)
    assert sensor(hass, "waiting").attributes["waiting"] == ["h4", "h5"]
    assert sensor(hass, "active").attributes["active"] == ["h1", "h2", "h3"]

    flow = await hass.config_entries.options.async_init(queue_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "max_active": 4,
            "monitored_entities": [f"light.relay_{i}" for i in range(1, 6)],
        },
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert sensor(hass, "status").state == "paused"
    assert sensor(hass, "active").attributes["active"] == ["h1", "h2", "h3"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h4", "h5"]
    assert sensor(hass, "status").attributes["max_active"] == 4

    await action(hass, "resume")
    assert sensor(hass, "active").attributes["active"] == ["h1", "h2", "h3", "h4"]
    assert sensor(hass, "waiting").attributes["waiting"] == ["h5"]
    assert sensor(hass, "available").state == "0"
