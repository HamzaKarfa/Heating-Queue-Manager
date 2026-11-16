"""Tests that run without installing Home Assistant or other dependencies."""

from pathlib import Path
import sys
import unittest

SOURCE_DIR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "resource_queue_manager"
)
sys.path.insert(0, str(SOURCE_DIR))

from fifo import ResourceQueue  # noqa: E402


class ResourceQueueTests(unittest.TestCase):
    def test_grants_only_max_active(self):
        q = ResourceQueue(3)
        for resource in ("ch1", "ch2", "ch3", "ch4", "ch5"):
            q.request(resource)
        self.assertEqual(q.snapshot().active, ("ch1", "ch2", "ch3"))
        self.assertEqual(q.snapshot().waiting, ("ch4", "ch5"))

    def test_fifo_promotion(self):
        q = ResourceQueue(2)
        for resource in ("a", "b", "c", "d"):
            q.request(resource)
        result = q.release("a")
        self.assertEqual(result.granted, ("c",))
        self.assertEqual(result.active, ("b", "c"))
        self.assertEqual(result.waiting, ("d",))

    def test_cancel_pending_request(self):
        q = ResourceQueue(1)
        q.request("a")
        q.request("b")
        q.request("c")
        q.release("b")
        self.assertEqual(q.release("a").granted, ("c",))

    def test_duplicate_requests_are_idempotent(self):
        q = ResourceQueue(1)
        q.request("a")
        q.request("b")
        q.request("b")
        q.request("a")
        self.assertEqual(q.snapshot().waiting, ("b",))
        self.assertEqual(q.release("a").granted, ("b",))

    def test_release_unknown_is_noop(self):
        q = ResourceQueue(1)
        q.request("a")
        result = q.release("unknown")
        self.assertEqual(result.active, ("a",))
        self.assertFalse(result.granted)

    def test_empty_queue_and_invalid_capacity(self):
        self.assertEqual(ResourceQueue(3).snapshot().waiting, ())
        with self.assertRaises(ValueError):
            ResourceQueue(0)
        with self.assertRaises(ValueError):
            ResourceQueue(True)

    def test_invalid_resource_id(self):
        q = ResourceQueue(1)
        with self.assertRaises(ValueError):
            q.request(" ")


if __name__ == "__main__":
    unittest.main()
