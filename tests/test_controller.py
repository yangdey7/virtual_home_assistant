import unittest

from backend.device_manager import DeviceManager
from backend.errors import CommandError


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.manager = DeviceManager()

    def apply(self, intent, device, value=None):
        return self.manager.execute({"intent": intent, "device": device, "value": value})

    def test_initial_state_and_copy_isolation(self):
        state = self.manager.snapshot()
        self.assertEqual(state["devices"], {
            "light": {"state": "OFF"}, "fan": {"state": "OFF", "speed": 1},
            "ac": {"state": "OFF", "temperature": 24}, "curtain": {"state": "CLOSED"},
        })
        state["devices"]["fan"]["speed"] = 50
        self.assertEqual(self.manager.snapshot()["devices"]["fan"]["speed"], 1)

    def test_all_thirteen_actions(self):
        for device, key in [("Light", "light"), ("Fan", "fan"), ("AC", "ac")]:
            with self.subTest(device=device):
                self.assertEqual(self.apply("TurnOn", device)["devices"][key]["state"], "ON")
                self.assertEqual(self.apply("TurnOff", device)["devices"][key]["state"], "OFF")
        self.apply("TurnOn", "Fan")
        self.assertEqual(self.apply("IncreaseSpeed", "Fan")["devices"]["fan"]["speed"], 2)
        self.assertEqual(self.apply("DecreaseSpeed", "Fan")["devices"]["fan"]["speed"], 1)
        self.assertEqual(self.apply("IncreaseTemp", "AC")["devices"]["ac"]["temperature"], 25)
        self.assertEqual(self.apply("DecreaseTemp", "AC")["devices"]["ac"]["temperature"], 24)
        self.assertEqual(self.apply("SetTemp", "AC", 21)["devices"]["ac"]["temperature"], 21)
        self.assertEqual(self.apply("Open", "Curtain")["devices"]["curtain"]["state"], "OPEN")
        self.assertEqual(self.apply("Close", "Curtain")["devices"]["curtain"]["state"], "CLOSED")

    def test_fan_limits_and_off_behavior(self):
        for intent in ("IncreaseSpeed", "DecreaseSpeed"):
            with self.assertRaisesRegex(CommandError, "fan is off"):
                self.apply(intent, "Fan")
        self.apply("TurnOn", "Fan")
        with self.assertRaisesRegex(CommandError, "minimum"):
            self.apply("DecreaseSpeed", "Fan")
        self.apply("IncreaseSpeed", "Fan")
        self.apply("IncreaseSpeed", "Fan")
        with self.assertRaisesRegex(CommandError, "maximum"):
            self.apply("IncreaseSpeed", "Fan")
        self.apply("TurnOff", "Fan")
        self.assertEqual(self.apply("TurnOn", "Fan")["devices"]["fan"]["speed"], 3)

    def test_invalid_combinations_do_not_mutate_state(self):
        for intent, device, value in [
            ("Open", "Light", None), ("IncreaseSpeed", "Curtain", None),
            ("SetTemp", "Fan", 24), ("TurnOn", "Curtain", None),
            ("TurnOn", None, None), (None, "Fan", None),
            ([], "Fan", None), ("TurnOn", {}, None), ("Fly", "AC", None),
            ("TurnOn", "Light", 20),
        ]:
            with self.subTest(intent=intent, device=device):
                before = self.manager.snapshot()["devices"]
                with self.assertRaises(CommandError):
                    self.apply(intent, device, value)
                self.assertEqual(self.manager.snapshot()["devices"], before)

    def test_temperature_values_limits_and_preservation(self):
        for value in (None, True, "24", 23.5, float("nan"), float("inf"), 15, 31, 10**500):
            with self.subTest(value=str(value)[:40]):
                with self.assertRaises(CommandError):
                    self.apply("SetTemp", "AC", value)
        self.apply("SetTemp", "AC", 16)
        with self.assertRaises(CommandError):
            self.apply("DecreaseTemp", "AC")
        self.apply("SetTemp", "AC", 30)
        with self.assertRaises(CommandError):
            self.apply("IncreaseTemp", "AC")
        self.apply("SetTemp", "AC", 22)
        self.apply("TurnOn", "AC")
        result = self.apply("TurnOff", "AC")
        self.assertEqual(result["devices"]["ac"], {"state": "OFF", "temperature": 22})
        result = self.apply("IncreaseTemp", "AC")
        self.assertEqual(result["devices"]["ac"], {"state": "OFF", "temperature": 23})
        self.assertIn("still off", result["message"])

    def test_history_is_bounded_and_errors_are_recorded(self):
        for _ in range(35):
            self.apply("TurnOn", "Light")
        self.assertEqual(len(self.manager.snapshot()["history"]), 30)
        before = self.manager.snapshot()["revision"]
        with self.assertRaises(CommandError):
            self.apply("Open", "Light")
        state = self.manager.snapshot()
        self.assertFalse(state["history"][0]["success"])
        self.assertGreater(state["revision"], before)


if __name__ == "__main__":
    unittest.main()

