"""Coordinator tests with simulated Home Assistant entity states only."""

from pathlib import Path
import sys
import types
import unittest

# Import the pure-Python submodule without running the integration __init__.py,
# which requires Home Assistant to be installed.
COMPONENTS_DIR = Path(__file__).resolve().parents[1] / "custom_components"
package = types.ModuleType("resource_queue_manager")
package.__path__ = [str(COMPONENTS_DIR / "resource_queue_manager")]
sys.modules.setdefault("resource_queue_manager", package)

from resource_queue_manager.coordinator import (  # noqa: E402
    ResourceQueueCoordinator,
    QueueStateError,
)


class CoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entities = {
            f"light.relay_{i}": "off" for i in range(1, 8)
        }
        self.manager = ResourceQueueCoordinator(3, self.entities.get, self.entities)

    def request(self, i: int):
        return self.manager.request(f"h{i}", f"light.relay_{i}")

    def test_three_slots_and_fifo_promotion(self):
        for i in range(1, 6):
            self.request(i)
        self.assertEqual(self.manager.snapshot().active, ("h1", "h2", "h3"))
        self.assertEqual(self.manager.snapshot().waiting, ("h4", "h5"))
        result = self.manager.release("h2")
        self.assertEqual(result.granted, ("h4",))
        self.assertEqual(result.active, ("h1", "h3", "h4"))
        self.assertEqual(result.waiting, ("h5",))

    def test_pending_cancel_does_not_block_following_requests(self):
        for i in range(1, 6):
            self.request(i)
        self.manager.cancel("h4")
        result = self.manager.release("h1")
        self.assertEqual(result.granted, ("h5",))

    def test_request_is_idempotent(self):
        self.request(1)
        self.assertEqual(self.request(1).granted, ())
        self.assertEqual(self.manager.snapshot().active, ("h1",))

    def test_lifo_coordinator_promotes_newest_waiter(self):
        manager = ResourceQueueCoordinator(
            1, self.entities.get, self.entities, strategy="lifo"
        )
        for i in range(1, 4):
            manager.request(f"h{i}", f"light.relay_{i}")
        self.assertEqual(manager.snapshot().waiting, ("h3", "h2"))
        self.assertEqual(manager.release("h1").granted, ("h3",))

    def test_legacy_snapshot_defaults_to_fifo(self):
        self.request(1)
        self.request(2)
        saved = self.manager.export_state()
        saved.pop("strategy")
        recovered = ResourceQueueCoordinator.from_state(
            3, self.entities.get, saved, self.entities
        )
        self.assertTrue(recovered.paused)
        self.assertEqual(recovered.strategy, "fifo")
        self.assertEqual(recovered.snapshot().active, ("h1", "h2"))

    def test_provider_settings_change_is_blocked_with_active_work(self):
        from resource_queue_manager.strategies import (
            PROVIDERS, FifoStrategy, StrategyConfigField
        )

        class ConfiguredProvider:
            key = "settings_test"
            label = "Settings test"
            description = "Test-only options"
            config_fields = (
                StrategyConfigField(
                    key="value", label="Value", kind="number",
                    required=True, minimum=1, maximum=10
                ),
            )

            def create(self, config=None):
                return FifoStrategy()

        PROVIDERS["settings_test"] = ConfiguredProvider()
        try:
            queue = ResourceQueueCoordinator(
                1, self.entities.get, self.entities,
                strategy="settings_test", strategy_config={"value": 1}
            )
            queue.request("unit_1", "light.relay_1")
            saved = queue.export_state()
            self.assertEqual(saved["strategy_config"], {"value": 1})
            with self.assertRaises(QueueStateError):
                ResourceQueueCoordinator.from_state(
                    1, self.entities.get, saved, self.entities,
                    strategy="settings_test", strategy_config={"value": 2}
                )
            recovered = ResourceQueueCoordinator.from_state(
                1, self.entities.get, saved, self.entities,
                strategy="settings_test", strategy_config={"value": 1}
            )
            self.assertTrue(recovered.paused)
            self.assertEqual(recovered.snapshot().active, ("unit_1",))
        finally:
            del PROVIDERS["settings_test"]

    def test_strategy_switch_only_with_empty_queue(self):
        self.request(1)
        saved = self.manager.export_state()
        with self.assertRaises(QueueStateError):
            ResourceQueueCoordinator.from_state(
                3, self.entities.get, saved, self.entities, strategy="lifo"
            )
        self.manager.release("h1")
        empty = self.manager.export_state()
        recovered = ResourceQueueCoordinator.from_state(
            3, self.entities.get, empty, self.entities, strategy="lifo"
        )
        self.assertEqual(recovered.strategy, "lifo")
        self.assertTrue(recovered.paused)

    def test_binding_is_immutable_while_queued(self):
        self.request(1)
        with self.assertRaises(QueueStateError):
            self.manager.request("h1", "light.relay_2")

    def test_same_relay_cannot_be_shared_across_resources(self):
        self.request(1)
        with self.assertRaises(QueueStateError):
            self.manager.request("other", "light.relay_1")

    def test_on_relay_cannot_claim_a_new_slot(self):
        self.entities["light.relay_1"] = "on"
        with self.assertRaises(QueueStateError):
            self.request(1)
        self.assertEqual(self.manager.snapshot().active, ())

    def test_unavailable_relay_is_fail_closed(self):
        self.entities["light.relay_1"] = "unavailable"
        with self.assertRaises(QueueStateError):
            self.request(1)
        self.assertEqual(self.manager.snapshot().active, ())

    def test_release_requires_observed_off_state(self):
        self.request(1)
        self.entities["light.relay_1"] = "on"
        with self.assertRaises(QueueStateError):
            self.manager.release("h1")
        self.assertEqual(self.manager.snapshot().active, ("h1",))
        self.entities["light.relay_1"] = "off"
        self.manager.release("h1")
        self.assertEqual(self.manager.snapshot().active, ())

    def test_unavailable_does_not_release_active_reservation(self):
        self.request(1)
        self.entities["light.relay_1"] = "unavailable"
        with self.assertRaises(QueueStateError):
            self.manager.release("h1")
        self.assertEqual(self.manager.snapshot().active, ("h1",))

    def test_cancel_active_also_requires_off(self):
        self.request(1)
        self.entities["light.relay_1"] = "on"
        with self.assertRaises(QueueStateError):
            self.manager.cancel("h1")
        self.entities["light.relay_1"] = "off"
        self.assertEqual(self.manager.cancel("h1").active, ())

    def test_duplicate_request_when_authorized_relay_on(self):
        self.request(1)
        self.entities["light.relay_1"] = "on"
        self.assertEqual(self.request(1).granted, ())
        self.assertEqual(self.manager.snapshot().active, ("h1",))

    def test_reservation_metadata_is_cleaned_after_cancel(self):
        self.request(1)
        self.manager.cancel("h1")
        self.assertIsNone(self.manager.entity_for("h1"))

    def test_unknown_release_is_idempotent(self):
        self.assertEqual(self.manager.release("missing").active, ())

    def test_nonconfigured_entity_is_rejected_regardless_of_domain(self):
        with self.assertRaisesRegex(QueueStateError, "not supervised"):
            self.manager.request("h1", "sensor.temperature")

    def test_invalid_entity_identifier_is_rejected(self):
        with self.assertRaisesRegex(QueueStateError, "valid Home Assistant"):
            self.manager.request("h1", "sensor.not valid")

    def test_native_number_text_and_helpers_are_logical_resources(self):
        entities = {
            "input_number.test": "12.5",
            "input_text.test": "hello",
            "number.native": "23",
            "text.native": "",
        }
        manager = ResourceQueueCoordinator(2, entities.get, entities)
        manager.request("a", "input_number.test")
        manager.request("b", "input_text.test")
        manager.request("c", "number.native")
        manager.request("d", "text.native")
        self.assertEqual(manager.snapshot().active, ("a", "b"))
        self.assertEqual(manager.snapshot().waiting, ("c", "d"))
        self.assertEqual(manager.release("a").granted, ("c",))
        self.assertEqual(manager.cancel("b").granted, ("d",))
        self.assertEqual(manager.snapshot().active, ("c", "d"))
        self.assertIsNone(manager.recovery_issues())

    def test_input_boolean_retains_on_off_safety(self):
        entities = {"input_boolean.demo": "off"}
        manager = ResourceQueueCoordinator(1, entities.get, entities)
        manager.request("a", "input_boolean.demo")
        entities["input_boolean.demo"] = "on"
        self.assertRaisesRegex(QueueStateError, "must be OFF", manager.release, "a")
        self.assertEqual(manager.snapshot().active, ("a",))
        entities["input_boolean.demo"] = "off"
        manager.release("a")
        self.assertEqual(manager.snapshot().active, ())

    def test_generic_resources_fail_closed_when_unavailable(self):
        entities = {"input_text.demo": "ready"}
        manager = ResourceQueueCoordinator(1, entities.get, entities)
        manager.request("a", "input_text.demo")
        saved = manager.export_state()
        entities["input_text.demo"] = "unavailable"
        with self.assertRaisesRegex(QueueStateError, "must be available"):
            manager.release("a")
        self.assertEqual(manager.snapshot().active, ("a",))
        restarted = ResourceQueueCoordinator.from_state(
            1, entities.get, saved, monitored_entities=entities
        )
        with self.assertRaisesRegex(QueueStateError, "Recovery blocked"):
            restarted.resume()
        self.assertTrue(restarted.paused)
        entities["input_text.demo"] = "ok"
        restarted.resume()
        self.assertEqual(restarted.release("a").active, ())

    def test_no_more_than_capacity_after_burst(self):
        for i in range(1, 8):
            self.request(i)
        self.assertLessEqual(len(self.manager.snapshot().active), 3)
        self.assertEqual(len(self.manager.snapshot().waiting), 4)


if __name__ == "__main__":
    unittest.main()
