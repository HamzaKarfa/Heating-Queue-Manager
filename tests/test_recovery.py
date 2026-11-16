"""Pure-Python state recovery tests; no Home Assistant installation required."""

from pathlib import Path
import sys
import types
import unittest

COMPONENTS_DIR = Path(__file__).resolve().parents[1] / "custom_components"
package = types.ModuleType("heating_queue_manager")
package.__path__ = [str(COMPONENTS_DIR / "heating_queue_manager")]
sys.modules.setdefault("heating_queue_manager", package)

from heating_queue_manager.coordinator import (  # noqa: E402
    HeatingQueueCoordinator,
    QueueStateError,
)


class StartupRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.relays = {f"light.r{i}": "off" for i in range(1, 6)}
        self.manager = HeatingQueueCoordinator(3, self.relays.get, self.relays)

    def restore(self, *args):
        """Restore with the supervised test relays configured."""
        return HeatingQueueCoordinator.from_state(
            *args, monitored_relays=self.relays
        )

    def test_restore_exact_fifo_and_hold_until_resume(self):
        for i in range(1, 6):
            self.manager.request(f"h{i}", f"light.r{i}")
        data = self.manager.export_state()
        restored = self.restore(3, self.relays.get, data)
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

    def test_on_reserved_relay_remains_reserved(self):
        self.manager.request("h1", "light.r1")
        self.relays["light.r1"] = "on"
        restored = self.restore(
            3, self.relays.get, self.manager.export_state()
        )
        restored.resume()
        self.assertEqual(restored.snapshot().active, ("h1",))
        with self.assertRaises(QueueStateError):
            restored.release("h1")

    def test_unknown_relay_blocks_resume_without_losing_slots(self):
        self.manager.request("h1", "light.r1")
        restored = self.restore(
            3, self.relays.get, self.manager.export_state()
        )
        self.relays["light.r1"] = "unavailable"
        with self.assertRaises(QueueStateError):
            restored.resume()
        self.assertTrue(restored.paused)
        self.assertEqual(restored.snapshot().active, ("h1",))

    def test_unreserved_on_relay_blocks_resume(self):
        self.manager.request("h1", "light.r1")
        self.manager.release("h1")
        self.relays["light.r1"] = "on"
        restored = self.restore(
            3, self.relays.get, self.manager.export_state()
        )
        with self.assertRaisesRegex(QueueStateError, "ON without"):
            restored.resume()

    def test_unknown_orphan_pauses_running_queue_on_next_request(self):
        self.manager.request("h1", "light.r1")
        self.manager.release("h1")
        self.relays["light.r1"] = "on"
        with self.assertRaisesRegex(QueueStateError, "unsafe relay"):
            self.manager.request("h2", "light.r2")
        self.assertTrue(self.manager.paused)

    def test_released_relay_is_not_retained_as_supervision(self):
        self.manager.request("h1", "light.r1")
        self.manager.release("h1")
        self.assertIsNone(self.manager.relay_for("h1"))
        self.assertEqual(self.manager.export_state()["bindings"], {})
        self.assertNotIn("known_relays", self.manager.export_state())

    def test_invalid_storage_never_restores_empty(self):
        self.manager.request("h1", "light.r1")
        corrupted = self.manager.export_state()
        corrupted["active"] = ["h1", "h1"]
        with self.assertRaises(ValueError):
            self.restore(3, self.relays.get, corrupted)

    def test_missing_binding_rejected(self):
        self.manager.request("h1", "light.r1")
        corrupted = self.manager.export_state()
        corrupted["bindings"] = {}
        with self.assertRaises(QueueStateError):
            self.restore(3, self.relays.get, corrupted)

    def test_changed_capacity_below_saved_count_rejected(self):
        for i in range(1, 4):
            self.manager.request(f"h{i}", f"light.r{i}")
        with self.assertRaises(ValueError):
            self.restore(
                2, self.relays.get, self.manager.export_state()
            )

    def test_pending_relay_on_is_inconsistent(self):
        for i in range(1, 5):
            self.manager.request(f"h{i}", f"light.r{i}")
        self.relays["light.r4"] = "on"
        restored = self.restore(
            3, self.relays.get, self.manager.export_state()
        )
        with self.assertRaisesRegex(QueueStateError, "ON without"):
            restored.resume()

    def test_restoration_does_not_emit_grants(self):
        self.manager.request("h1", "light.r1")
        restored = self.restore(
            3, self.relays.get, self.manager.export_state()
        )
        self.assertEqual(restored.snapshot().granted, ())

    def test_legacy_history_does_not_block_excluded_relay(self):
        saved = self.manager.export_state()
        saved["known_relays"] = {"h3": "light.r3"}
        self.relays["light.r3"] = "on"
        restored = HeatingQueueCoordinator.from_state(
            3, self.relays.get, saved,
            monitored_relays=["light.r1"],
        )
        restored.resume()
        self.assertFalse(restored.paused)
        self.assertEqual(restored.recovery_issues(), ())

    def test_supervised_on_relay_without_booking_blocks_even_if_never_requested(self):
        self.relays["light.r2"] = "on"
        with self.assertRaisesRegex(QueueStateError, "ON without"):
            self.manager.resume()

    def test_excluded_relay_rejects_request(self):
        manager = HeatingQueueCoordinator(
            3, self.relays.get, ["light.r1"]
        )
        with self.assertRaisesRegex(QueueStateError, "not supervised"):
            manager.request("h2", "light.r2")

    def test_never_drop_excluded_active_booking_on_restore(self):
        self.manager.request("h3", "light.r3")
        saved = self.manager.export_state()
        with self.assertRaisesRegex(QueueStateError, "not supervised"):
            HeatingQueueCoordinator.from_state(
                3, self.relays.get, saved,
                monitored_relays=["light.r1"],
            )

    def test_rebinding_after_release_is_allowed(self):
        manager = HeatingQueueCoordinator(
            3, self.relays.get, ["light.r1", "light.r2"]
        )
        manager.request("h1", "light.r1")
        manager.release("h1")
        manager.request("h1", "light.r2")
        self.assertEqual(manager.relay_for("h1"), "light.r2")


if __name__ == "__main__":
    unittest.main()
