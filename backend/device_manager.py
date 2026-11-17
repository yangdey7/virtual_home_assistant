"""One authoritative, thread-safe controller for manual and inferred commands."""

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from .errors import CommandError

INTENTS = frozenset({
    "TurnOn", "TurnOff", "IncreaseSpeed", "DecreaseSpeed", "IncreaseTemp",
    "DecreaseTemp", "SetTemp", "Open", "Close",
})
DEVICES = {"Light": "light", "Fan": "fan", "AC": "ac", "Curtain": "curtain"}
ALLOWED = {
    "Light": {"TurnOn", "TurnOff"},
    "Fan": {"TurnOn", "TurnOff", "IncreaseSpeed", "DecreaseSpeed"},
    "AC": {"TurnOn", "TurnOff", "IncreaseTemp", "DecreaseTemp", "SetTemp"},
    "Curtain": {"Open", "Close"},
}


class DeviceManager:
    def __init__(self, min_temperature=16, max_temperature=30, history_limit=30):
        if not 10 <= min_temperature <= 24 <= max_temperature <= 40:
            raise ValueError("Temperature limits must contain the initial 24°C setting (10–40°C).")
        self.min_temperature = min_temperature
        self.max_temperature = max_temperature
        self._lock = RLock()
        self._session_id = str(uuid4())
        self._revision = 0
        self._history = deque(maxlen=history_limit)
        self._state = {
            "light": {"state": "OFF"},
            "fan": {"state": "OFF", "speed": 1},
            "ac": {"state": "OFF", "temperature": 24},
            "curtain": {"state": "CLOSED"},
        }

    def snapshot(self):
        with self._lock:
            return {
                "session_id": self._session_id,
                "devices": deepcopy(self._state),
                "revision": self._revision,
                "history": deepcopy(list(self._history)),
                "limits": {"temperature_min": self.min_temperature,
                           "temperature_max": self.max_temperature, "fan_max": 3},
            }

    def _record(self, transcript, prediction, source, message, success):
        self._revision += 1
        self._history.appendleft({
            "id": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(),
            "transcript": transcript, "prediction": deepcopy(prediction),
            "source": source, "message": message, "success": success,
        })

    def record_failure(self, transcript, prediction, source, message):
        with self._lock:
            self._record(transcript, prediction, source, message, False)
            return self.snapshot()

    def execute(self, command, transcript="", source="manual"):
        with self._lock:
            try:
                message = self._apply(command)
            except CommandError as exc:
                self._record(transcript, command, source, str(exc), False)
                raise
            self._record(transcript, command, source, message, True)
            return {"message": message, "execution": {"success": True}, **self.snapshot()}

    def _apply(self, command):
        if not isinstance(command, dict):
            raise CommandError("The command must contain an intent and a device.")
        intent, device, value = (command.get(k) for k in ("intent", "device", "value"))
        if not isinstance(intent, str) or intent not in INTENTS:
            raise CommandError("I couldn't recognize the action. Please repeat your command.", "unknown_intent")
        if not isinstance(device, str) or device not in DEVICES:
            raise CommandError("Please specify the light, fan, AC, or curtains.", "missing_device")
        if intent not in ALLOWED[device]:
            raise CommandError(f"{intent} isn't supported for {device}. Please clarify the command.", "incompatible_action")
        if intent != "SetTemp" and value is not None:
            raise CommandError("Only SetTemp accepts a numerical value. Please clarify the command.")
        current = self._state[DEVICES[device]]
        label = {"Light": "Bedroom light", "Fan": "Bedroom fan", "AC": "Bedroom AC", "Curtain": "Bedroom curtains"}[device]
        if intent in {"TurnOn", "TurnOff"}:
            current["state"] = "ON" if intent == "TurnOn" else "OFF"
            return f"{label} has been switched {current['state'].lower()}."
        if intent in {"Open", "Close"}:
            current["state"] = "OPEN" if intent == "Open" else "CLOSED"
            return f"{label} are {current['state'].lower()}."
        if intent in {"IncreaseSpeed", "DecreaseSpeed"}:
            if current["state"] == "OFF":
                raise CommandError("The fan is off. Turn it on before adjusting its speed.", "device_off")
            speed = current["speed"] + (1 if intent == "IncreaseSpeed" else -1)
            if not 1 <= speed <= 3:
                raise CommandError(f"The fan is already at {'maximum' if speed > 3 else 'minimum'} speed (level {current['speed']}).", "speed_limit")
            current["speed"] = speed
            return f"Bedroom fan speed is now level {speed}."
        if intent == "SetTemp":
            if type(value) not in (int, float) or (type(value) is float and not value.is_integer()):
                raise CommandError("Please give a whole-number temperature, such as 24 degrees.", "missing_value")
            temperature = int(value)
        else:
            temperature = current["temperature"] + (1 if intent == "IncreaseTemp" else -1)
        if not self.min_temperature <= temperature <= self.max_temperature:
            raise CommandError(f"Choose a temperature between {self.min_temperature}°C and {self.max_temperature}°C.", "temperature_limit")
        # Adjusting an off AC changes its saved setpoint without turning it on.
        current["temperature"] = temperature
        suffix = " The AC is still off." if current["state"] == "OFF" else ""
        return f"Bedroom AC temperature is set to {temperature}°C.{suffix}"

