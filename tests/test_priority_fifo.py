"""Priority FIFO plugin tests without Home Assistant installed."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "resource_queue_manager"
sys.path.insert(0, str(ROOT))

from engine import ResourceQueue  # noqa: E402
from strategies import get_provider, strategy_options  # noqa: E402


class PriorityFifoStrategyTests(unittest.TestCase):
    def create(self, order="highest_first"):
        return ResourceQueue(
            max_active=1,
            strategy="priority_fifo",
            strategy_config={"priority_order": order},
        )

    def test_prioritizes_waiting_requests_with_stable_fifo_ties(self):
        queue = self.create()
        for resource, priority in (
            ("a", 1), ("b", 4), ("c", 7), ("d", 4), ("e", 10),
        ):
            queue.request(resource, {"priority": priority})

        # A is already active and cannot be preempted by a higher priority.
        self.assertEqual(queue.snapshot().active, ("a",))
        self.assertEqual(queue.snapshot().waiting, ("e", "c", "b", "d"))

        self.assertEqual(queue.release("a").granted, ("e",))
        self.assertEqual(queue.release("e").granted, ("c",))
        self.assertEqual(queue.release("c").granted, ("b",))
        self.assertEqual(queue.release("b").granted, ("d",))

    def test_can_schedule_lowest_priority_number_first(self):
        queue = self.create("lowest_first")
        for resource, priority in (
            ("a", 5), ("b", 9), ("c", 2), ("d", 2), ("e", 1),
        ):
            queue.request(resource, {"priority": priority})
        self.assertEqual(queue.snapshot().active, ("a",))
        self.assertEqual(queue.snapshot().waiting, ("e", "c", "d", "b"))

    def test_cancel_waiting_removes_metadata_without_changing_ties(self):
        queue = self.create()
        queue.request("a", {"priority": 1})
        queue.request("b", {"priority": 7})
        queue.request("c", {"priority": 7})
        queue.release("b")
        self.assertEqual(queue.snapshot().waiting, ("c",))
        self.assertNotIn("b", queue.export_request_data())
        self.assertEqual(queue.release("a").granted, ("c",))

    def test_restart_retains_priority_order_and_request_metadata(self):
        queue = self.create()
        for resource, priority in (("a", 2), ("b", 5), ("c", 9), ("d", 5)):
            queue.request(resource, {"priority": priority})
        saved = queue.snapshot()
        metadata = queue.export_request_data()

        restored = ResourceQueue.from_snapshot(
            max_active=1,
            active=list(saved.active),
            waiting=list(saved.waiting),
            strategy="priority_fifo",
            strategy_config={"priority_order": "highest_first"},
            request_data=metadata,
        )
        self.assertEqual(restored.snapshot(), saved)
        self.assertEqual(restored.export_request_data(), metadata)
        self.assertEqual(restored.release("a").granted, ("c",))
        self.assertEqual(restored.release("c").granted, ("b",))

    def test_repeated_request_is_idempotent_but_cannot_change_priority(self):
        queue = self.create()
        queue.request("a", {"priority": 2})
        queue.request("b", {"priority": 5})
        self.assertEqual(queue.request("b", {"priority": 5}).granted, ())
        self.assertEqual(queue.snapshot().waiting, ("b",))
        with self.assertRaises(ValueError):
            queue.request("b", {"priority": 9})
        self.assertEqual(queue.snapshot().waiting, ("b",))

    def test_invalid_requests_and_config_are_rejected(self):
        queue = self.create()
        for metadata in (None, {}, {"priority": 0}, {"priority": 11},
                         {"priority": True}, {"priority": "10"},
                         {"priority": 5, "unknown": 1}):
            with self.subTest(metadata=metadata):
                with self.assertRaises(ValueError):
                    queue.request("test", metadata)
        self.assertEqual(queue.snapshot().active, ())
        with self.assertRaises(ValueError):
            self.create("unknown")
        with self.assertRaises(ValueError):
            ResourceQueue(
                strategy="priority_fifo",
                strategy_config={"priority_order": "bogus"},
            )

    def test_provider_registered_with_own_config_and_request_contract(self):
        provider = get_provider("priority_fifo")
        self.assertEqual(provider.key, "priority_fifo")
        self.assertEqual(
            [field.key for field in provider.config_fields], ["priority_order"]
        )
        self.assertEqual(
            [field.key for field in provider.request_fields], ["priority"]
        )
        self.assertIn(
            "priority_fifo", {choice["value"] for choice in strategy_options()}
        )
        self.assertIsNot(provider.create(), provider.create())


if __name__ == "__main__":
    unittest.main()
