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

    def test_validates_relay_domain(self):
        with self.assertRaises(QueueStateError):
            self.manager.request("h1", "sensor.temperature")

    def test_no_more_than_capacity_after_burst(self):
        for i in range(1, 8):
            self.request(i)
        self.assertLessEqual(len(self.manager.snapshot().active), 3)
        self.assertEqual(len(self.manager.snapshot().waiting), 4)


if __name__ == "__main__":
    unittest.main()
