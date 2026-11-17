"""Pure-Python state recovery tests; no Home Assistant installation required."""

from pathlib import Path
import sys
import types
import unittest

COMPONENTS_DIR = Path(__file__).resolve().parents[1] / "custom_components"
package = types.ModuleType("resource_queue_manager")
package.__path__ = [str(COMPONENTS_DIR / "resource_queue_manager")]
sys.modules.setdefault("resource_queue_manager", package)

from resource_queue_manager.coordinator import (  # noqa: E402
    ResourceQueueCoordinator,
    QueueStateError,
)


class StartupRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entities = {f"light.r{i}": "off" for i in range(1, 6)}
        self.manager = ResourceQueueCoordinator(3, self.entities.get, self.entities)

    def restore(self, *args):
        """Restore with the supervised test entities configured."""
        return ResourceQueueCoordinator.from_state(
            *args, monitored_entities=self.entities
        )

    def test_restore_exact_fifo_and_hold_until_resume(self):
        for i in range(1, 6):
            self.manager.request(f"h{i}", f"light.r{i}")
        data = self.manager.export_state()
        restored = self.restore(3, self.entities.get, data)
        self.assertTrue(restored.paused)
        self.assertEqual(restored.snapshot().active, ("h1", "h2", "h3"))
        self.assertEqual(restored.snapshot().waiting, ("h4", "h5"))
        with self.assertRaises(QueueStateError):
            restored.release("h1")
        with self.assertRaises(QueueStateError):
            restored.request("h1", "light.r1")
        restored.resume()
        self.assertFalse(restored.paused)
        self.assertEqual(restored.release("h1").granted, ("h4",))

    def test_populated_v04_snapshot_migrates_without_dropping_queue(self):
        """A v0.4 snapshot has no strategy fields or per-request metadata."""
        old_snapshot = {
            "active": ["h1", "h2", "h3"],
            "waiting": ["h4", "h5"],
            "max_active": 3,
            "bindings": {
                f"h{i}": f"light.r{i}" for i in range(1, 6)
            },
        }
        recovered = ResourceQueueCoordinator.from_state(
            3, self.entities.get, old_snapshot,
            monitored_entities=self.entities,
            strategy="fifo",
        )
        self.assertTrue(recovered.paused)
        self.assertEqual(recovered.snapshot().active, ("h1", "h2", "h3"))
        self.assertEqual(recovered.snapshot().waiting, ("h4", "h5"))
        self.assertEqual(recovered.queue.export_request_data(), {})
        saved_again = recovered.export_state()
        self.assertEqual(saved_again["strategy"], "fifo")
        self.assertEqual(saved_again["request_data"], {})
        self.assertEqual(saved_again["bindings"], old_snapshot["bindings"])
        self.assertEqual(saved_again["active"], old_snapshot["active"])
        self.assertEqual(saved_again["waiting"], old_snapshot["waiting"])
        recovered.resume()
        self.assertEqual(recovered.release("h1").granted, ("h4",))

    def test_on_reserved_relay_remains_reserved(self):
        self.manager.request("h1", "light.r1")
        self.entities["light.r1"] = "on"
        restored = self.restore(
            3, self.entities.get, self.manager.export_state()
        )
        restored.resume()
        self.assertEqual(restored.snapshot().active, ("h1",))
        with self.assertRaises(QueueStateError):
            restored.release("h1")

    def test_unknown_relay_blocks_resume_without_losing_slots(self):
        self.manager.request("h1", "light.r1")
        restored = self.restore(
            3, self.entities.get, self.manager.export_state()
        )
        self.entities["light.r1"] = "unavailable"
        with self.assertRaises(QueueStateError):
            restored.resume()
        self.assertTrue(restored.paused)
        self.assertEqual(restored.snapshot().active, ("h1",))

    def test_unreserved_on_relay_blocks_resume(self):
        self.manager.request("h1", "light.r1")
        self.manager.release("h1")
        self.entities["light.r1"] = "on"
        restored = self.restore(
            3, self.entities.get, self.manager.export_state()
        )
        with self.assertRaisesRegex(QueueStateError, "ON without"):
            restored.resume()

    def test_unknown_orphan_pauses_running_queue_on_next_request(self):
        self.manager.request("h1", "light.r1")
        self.manager.release("h1")
        self.entities["light.r1"] = "on"
        with self.assertRaisesRegex(QueueStateError, "unsafe entity"):
            self.manager.request("h2", "light.r2")
        self.assertTrue(self.manager.paused)

    def test_released_relay_is_not_retained_as_supervision(self):
        self.manager.request("h1", "light.r1")
        self.manager.release("h1")
        self.assertIsNone(self.manager.entity_for("h1"))
        self.assertEqual(self.manager.export_state()["bindings"], {})
        self.assertNotIn("known_relays", self.manager.export_state())

    def test_invalid_storage_never_restores_empty(self):
        self.manager.request("h1", "light.r1")
        corrupted = self.manager.export_state()
        corrupted["active"] = ["h1", "h1"]
        with self.assertRaises(ValueError):
            self.restore(3, self.entities.get, corrupted)

    def test_missing_binding_rejected(self):
        self.manager.request("h1", "light.r1")
        corrupted = self.manager.export_state()
        corrupted["bindings"] = {}
        with self.assertRaises(QueueStateError):
            self.restore(3, self.entities.get, corrupted)

    def test_changed_capacity_below_saved_count_rejected(self):
        for i in range(1, 4):
            self.manager.request(f"h{i}", f"light.r{i}")
        with self.assertRaises(ValueError):
            self.restore(
                2, self.entities.get, self.manager.export_state()
            )

    def test_pending_relay_on_is_inconsistent(self):
        for i in range(1, 5):
            self.manager.request(f"h{i}", f"light.r{i}")
        self.entities["light.r4"] = "on"
        restored = self.restore(
            3, self.entities.get, self.manager.export_state()
        )
        with self.assertRaisesRegex(QueueStateError, "ON without"):
            restored.resume()

    def test_restoration_does_not_emit_grants(self):
        self.manager.request("h1", "light.r1")
        restored = self.restore(
            3, self.entities.get, self.manager.export_state()
        )
        self.assertEqual(restored.snapshot().granted, ())

    def test_legacy_history_does_not_block_excluded_relay(self):
        saved = self.manager.export_state()
        saved["known_relays"] = {"h3": "light.r3"}
        self.entities["light.r3"] = "on"
        restored = ResourceQueueCoordinator.from_state(
            3, self.entities.get, saved,
            monitored_entities=["light.r1"],
        )
        restored.resume()
        self.assertFalse(restored.paused)
        self.assertEqual(restored.recovery_issues(), ())

    def test_supervised_on_relay_without_booking_blocks_even_if_never_requested(self):
        self.entities["light.r2"] = "on"
        with self.assertRaisesRegex(QueueStateError, "ON without"):
            self.manager.resume()

    def test_excluded_relay_rejects_request(self):
        manager = ResourceQueueCoordinator(
            3, self.entities.get, ["light.r1"]
        )
        with self.assertRaisesRegex(QueueStateError, "not supervised"):
            manager.request("h2", "light.r2")

    def test_never_drop_excluded_active_booking_on_restore(self):
        self.manager.request("h3", "light.r3")
        saved = self.manager.export_state()
        with self.assertRaisesRegex(QueueStateError, "not supervised"):
            ResourceQueueCoordinator.from_state(
                3, self.entities.get, saved,
                monitored_entities=["light.r1"],
            )

    def test_rebinding_after_release_is_allowed(self):
        manager = ResourceQueueCoordinator(
            3, self.entities.get, ["light.r1", "light.r2"]
        )
        manager.request("h1", "light.r1")
        manager.release("h1")
        manager.request("h1", "light.r2")
        self.assertEqual(manager.entity_for("h1"), "light.r2")


    def test_max_limit_increase_keeps_fifo_until_resume(self):
        """A bigger limit gives next waiting resource a slot only on resume."""
        for i in range(1, 5):
            self.manager.request(f"h{i}", f"light.r{i}")
        saved = self.manager.export_state()
        restored = self.restore(4, self.entities.get, saved)
        self.assertEqual(restored.snapshot().active, ("h1", "h2", "h3"))
        self.assertEqual(restored.snapshot().waiting, ("h4",))
        self.assertTrue(restored.paused)
        result = restored.resume()
        self.assertEqual(result.granted, ("h4",))
        self.assertEqual(result.active, ("h1", "h2", "h3", "h4"))
        self.assertEqual(result.waiting, ())

    def test_legacy_snapshot_without_saved_limit_can_expand(self):
        for i in range(1, 5):
            self.manager.request(f"h{i}", f"light.r{i}")
        saved = self.manager.export_state()
        saved.pop("max_active")
        restored = ResourceQueueCoordinator.from_state(
            4, self.entities.get, saved,
            monitored_entities=self.entities,
            legacy_max_active=3,
        )
        self.assertEqual(restored.resume().granted, ("h4",))

    def test_decrease_limit_to_number_of_current_reservations(self):
        for i in range(1, 4):
            self.manager.request(f"h{i}", f"light.r{i}")
        restored = self.restore(
            3, self.entities.get, self.manager.export_state()
        )
        self.assertEqual(restored.resume().granted, ())
        self.assertEqual(restored.max_active, 3)

    def test_decrease_limit_below_current_reservations_rejected(self):
        for i in range(1, 4):
            self.manager.request(f"h{i}", f"light.r{i}")
        with self.assertRaises(QueueStateError):
            self.restore(2, self.entities.get, self.manager.export_state())

    def test_increased_limit_refuses_to_grant_if_waiting_relay_on(self):
        for i in range(1, 5):
            self.manager.request(f"h{i}", f"light.r{i}")
        saved = self.manager.export_state()
        self.entities["light.r4"] = "on"
        restored = self.restore(4, self.entities.get, saved)
        with self.assertRaises(QueueStateError):
            restored.resume()
        self.assertTrue(restored.paused)
        self.assertEqual(restored.snapshot().waiting, ("h4",))

if __name__ == "__main__":
    unittest.main()

