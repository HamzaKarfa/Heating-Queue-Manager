"""Pure-Python contracts for domain-neutral Home Assistant resource binding."""

from pathlib import Path
import sys
import unittest

SOURCE_DIR = (
    Path(__file__).resolve().parents[1]
    / "custom_components" / "resource_queue_manager"
)
sys.path.insert(0, str(SOURCE_DIR))

from entity_supervision import (  # noqa: E402
    ON_OFF_DOMAINS,
    recovery_issue,
    release_issue,
    supervision_mode,
    validate_entity_id,
)


class SupervisionPolicyTests(unittest.TestCase):
    def test_native_helpers_and_arbitrary_entity_domains_are_accepted(self):
        for entity_id in (
            "switch.pump", "light.demo", "input_boolean.demo",
            "input_number.demo", "input_text.demo", "input_select.demo",
            "number.demo", "text.demo", "sensor.temperature",
            "binary_sensor.opening", "fan.exhaust",
        ):
            with self.subTest(entity=entity_id):
                validate_entity_id(entity_id)

    def test_invalid_entity_ids_fail(self):
        for candidate in ("", "test", "sensor.", ".test", "Sensor.bad",
                          "light.spaces here", "light.a.b", 123, None):
            with self.subTest(entity=candidate):
                with self.assertRaises(ValueError):
                    validate_entity_id(candidate)

    def test_on_off_devices_are_guarded_by_state(self):
        for domain in ON_OFF_DOMAINS:
            entity_id = f"{domain}.demo"
            with self.subTest(entity=entity_id):
                self.assertEqual(supervision_mode(entity_id), "on_off")
                self.assertIsNone(recovery_issue(entity_id, "off", False))
                self.assertIn(
                    "ON without", recovery_issue(entity_id, "on", False)
                )
                self.assertIsNone(recovery_issue(entity_id, "on", True))
                self.assertIn("must be OFF", release_issue(entity_id, "on"))
                self.assertIsNone(release_issue(entity_id, "off"))
                self.assertIsNotNone(recovery_issue(entity_id, "55", True))

    def test_numeric_text_and_other_values_are_logical_only(self):
        for entity_id, value in (
            ("number.target", "42.5"),
            ("input_number.target", "2"),
            ("text.message", "hello"),
            ("input_text.message", ""),
            ("input_select.mode", "on"),
            ("sensor.power", "100 W"),
        ):
            with self.subTest(entity=entity_id):
                self.assertEqual(supervision_mode(entity_id), "availability")
                self.assertIsNone(recovery_issue(entity_id, value, False))
                self.assertIsNone(recovery_issue(entity_id, value, True))
                self.assertIsNone(release_issue(entity_id, value))

    def test_unavailable_generic_entities_block_recovery_and_release(self):
        for state in (None, "unknown", "unavailable"):
            with self.subTest(state=state):
                self.assertIsNotNone(recovery_issue("number.target", state, True))
                self.assertIn(
                    "must be available", release_issue("number.target", state)
                )


if __name__ == "__main__":
    unittest.main()
