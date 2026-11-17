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
from strategies import (  # noqa: E402
    PROVIDERS,
    FifoStrategy,
    QueueRequest,
    StrategyConfigField,
    get_provider,
    get_strategy,
    strategy_options,
    validate_strategy_config,
)


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

    def test_lifo_promotes_most_recent_waiter_without_preemption(self):
        q = ResourceQueue(1, strategy="lifo")
        for resource in ("a", "b", "c", "d"):
            q.request(resource)
        self.assertEqual(q.snapshot().active, ("a",))
        self.assertEqual(q.snapshot().waiting, ("d", "c", "b"))
        result = q.release("a")
        self.assertEqual(result.granted, ("d",))
        self.assertEqual(result.waiting, ("c", "b"))

    def test_lifo_persisted_grant_order_is_preserved(self):
        q = ResourceQueue(1, strategy="lifo")
        for resource in ("a", "b", "c"):
            q.request(resource)
        saved = q.snapshot()
        restored = ResourceQueue.from_snapshot(
            max_active=1,
            active=list(saved.active),
            waiting=list(saved.waiting),
            strategy="lifo",
        )
        self.assertEqual(restored.release("a").granted, ("c",))

    def test_strategy_registry_rejects_invalid_key(self):
        with self.assertRaises(ValueError):
            ResourceQueue(strategy="unknown")

    def test_provider_specific_settings_are_validated_and_restored(self):
        class DemoProvider:
            key = "demo_config"
            label = "Demo configurable FIFO"
            description = "Test-only provider"
            config_fields = (
                StrategyConfigField(
                    key="limit", label="Limit", kind="number",
                    required=True, minimum=1, maximum=10
                ),
                StrategyConfigField(
                    key="mode", label="Mode", kind="select",
                    choices=("simple", "strict"), default="simple"
                ),
                StrategyConfigField(
                    key="enabled", label="Enabled", kind="boolean",
                    default=True
                ),
            )

            def create(self, config=None):
                return FifoStrategy()

        PROVIDERS["demo_config"] = DemoProvider()
        try:
            config = validate_strategy_config("demo_config", {"limit": 4})
            self.assertEqual(
                config, {"limit": 4, "mode": "simple", "enabled": True}
            )
            q = ResourceQueue(
                1, strategy="demo_config", strategy_config=config
            )
            q.request("a")
            q.request("b")
            self.assertEqual(q.strategy_config, config)
            restored = ResourceQueue.from_snapshot(
                1, ["a"], ["b"],
                strategy="demo_config", strategy_config=config
            )
            self.assertEqual(restored.release("a").granted, ("b",))
            self.assertEqual(restored.strategy_config, config)
            with self.assertRaises(ValueError):
                validate_strategy_config("demo_config", {"limit": True})
            with self.assertRaises(ValueError):
                validate_strategy_config("demo_config", {"limit": 11})
            with self.assertRaises(ValueError):
                validate_strategy_config(
                    "demo_config", {"limit": 2, "mode": "bogus"}
                )
            with self.assertRaises(ValueError):
                validate_strategy_config(
                    "demo_config", {"limit": 2, "undeclared": 99}
                )
            with self.assertRaises(ValueError):
                validate_strategy_config("demo_config", {})
        finally:
            del PROVIDERS["demo_config"]

    def test_provider_request_metadata_controls_order_and_survives_restore(self):
        from collections import deque

        class PriorityPolicy:
            key = "test_priority"
            label = "Test priority"

            def enqueue(self, waiting, request, requests):
                # Bigger numbers first, FIFO for equal numbers.
                new_priority = request.data["priority"]
                for index, existing_id in enumerate(waiting):
                    if requests[existing_id].data["priority"] < new_priority:
                        waiting.insert(index, request.resource_id)
                        break
                else:
                    waiting.append(request.resource_id)

        class PriorityProvider:
            key = "test_priority"
            label = "Test priority"
            description = "Only used to verify the provider contract"
            config_fields = ()
            request_fields = (
                StrategyConfigField(
                    key="priority", label="Priority", kind="number",
                    required=True, minimum=1, maximum=10
                ),
            )

            def create(self, config=None):
                return PriorityPolicy()

        PROVIDERS["test_priority"] = PriorityProvider()
        try:
            q = ResourceQueue(1, strategy="test_priority")
            q.request("a", {"priority": 1})
            q.request("b", {"priority": 2})
            q.request("c", {"priority": 7})
            q.request("d", {"priority": 2})
            self.assertEqual(q.snapshot().active, ("a",))
            self.assertEqual(q.snapshot().waiting, ("c", "b", "d"))
            saved = q.export_request_data()
            self.assertEqual(saved["c"], {"priority": 7})
            restored = ResourceQueue.from_snapshot(
                1, list(q.snapshot().active), list(q.snapshot().waiting),
                strategy="test_priority", request_data=saved
            )
            self.assertEqual(restored.export_request_data(), saved)
            self.assertEqual(restored.release("a").granted, ("c",))
            self.assertEqual(restored.release("c").granted, ("b",))
            with self.assertRaises(ValueError):
                q.request("d", {"priority": 5})
            with self.assertRaises(ValueError):
                q.request("z", {"priority": True})
            with self.assertRaises(ValueError):
                q.request("z", {"priority": 50})
            with self.assertRaises(ValueError):
                q.request("z", {"unexpected": 1})
            with self.assertRaises(ValueError):
                q.request("z")
            with self.assertRaises(ValueError):
                ResourceQueue.from_snapshot(
                    1, ["a"], ["b"], strategy="test_priority",
                    request_data={"orphan": {"priority": 2}}
                )
        finally:
            del PROVIDERS["test_priority"]

    def test_fifo_and_lifo_reject_undeclared_request_metadata(self):
        for policy in ("fifo", "lifo"):
            q = ResourceQueue(1, strategy=policy)
            with self.assertRaises(ValueError):
                q.request("a", {"priority": 9})
            self.assertEqual(q.snapshot().active, ())
            self.assertEqual(q.snapshot().waiting, ())

    def test_legacy_snapshot_restores_empty_request_metadata(self):
        q = ResourceQueue.from_snapshot(1, ["a"], ["b"], strategy="fifo")
        self.assertEqual(q.export_request_data(), {})
        self.assertEqual(q.release("a").granted, ("b",))

    def test_plugin_providers_are_independent_instances(self):
        fifo_provider = get_provider("fifo")
        lifo_provider = get_provider("lifo")
        self.assertEqual(fifo_provider.key, "fifo")
        self.assertEqual(lifo_provider.key, "lifo")
        self.assertIsNot(get_strategy("fifo"), get_strategy("fifo"))
        self.assertIsNot(get_strategy("lifo"), get_strategy("lifo"))

    def test_strategy_selector_uses_registered_providers(self):
        options = strategy_options()
        self.assertEqual(
            {option["value"] for option in options},
            {"fifo", "lifo", "priority_fifo"},
        )
        for option in options:
            provider = get_provider(option["value"])
            self.assertEqual(option["label"], provider.label)
        self.assertEqual(get_provider("fifo").config_fields, ())
        self.assertEqual(get_provider("lifo").config_fields, ())
        self.assertEqual(
            [field.key for field in get_provider("priority_fifo").config_fields],
            ["priority_order"],
        )

    def test_provider_labels_have_french_translations(self):
        labels = {x["value"]: x["label"] for x in strategy_options("fr")}
        self.assertEqual(
            labels["priority_fifo"], "FIFO avec priorité"
        )
        self.assertTrue(labels["fifo"].startswith("FIFO"))
        self.assertTrue(labels["lifo"].startswith("LIFO"))
        self.assertEqual(
            {x["value"]: x["label"] for x in strategy_options("fr-FR")},
            labels,
        )
        provider = get_provider("priority_fifo")
        self.assertEqual(
            provider.localized_choices["fr"]["priority_order"]["highest_first"],
            "Priorité la plus élevée d'abord",
        )

    def test_provider_rejects_unexpected_settings(self):
        with self.assertRaises(ValueError):
            get_provider("fifo").create({"priority": 3})

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
