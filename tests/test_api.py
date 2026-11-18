"""Exercise real routes/controller with explicit test-only inference fixtures."""

import io
import json
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from backend.app import create_app
from backend.codemix_inference import temperature_value
from backend.model_inference import ModelService


class FixturePredictor:
    """Never used by the application. Does not simulate model accuracy."""

    def __init__(self, output):
        self.output = output
        self.calls = []

    def predict(self, text):
        self.calls.append(text)
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def fixture_service(output):
    service = ModelService()
    service._configure_adapter()
    service._predictor = FixturePredictor(output)
    service.message = "TEST FIXTURE ONLY"
    service.status_code = "ready"
    return service


class ApiTests(TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "MODEL_CONFIG": None, "WHISPER_MODEL": None})
        self.client = self.app.test_client()

    def test_frontend_and_health_without_models(self):
        with self.client.get("/") as response:
            self.assertEqual(response.status_code, 200)
        with self.client.get("/static/js/app.js") as response:
            self.assertEqual(response.status_code, 200)
        health = self.client.get("/api/health").json
        self.assertFalse(health["model"]["ready"])
        self.assertFalse(health["speech"]["ready"])
        result = self.client.post("/api/interpret", json={"text": "Fan on bay nang."})
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json["error"], "model_not_configured")
        self.assertFalse(result.json["execution"]["success"])
        self.assertEqual(result.json["devices"]["fan"]["state"], "OFF")
        self.assertEqual(result.json["history"][0]["transcript"], "Fan on bay nang.")

    def test_voice_and_manual_share_state_and_single_use_execution(self):
        service = fixture_service({"intent": "TurnOn", "device": "Fan", "value": None, "confidence": .99})
        client = create_app({"TESTING": True}, model_service=service).test_client()
        interpreted = client.post("/api/interpret", json={"text": "Fan on bay nang.", "source": "voice"}).json
        self.assertEqual(client.get("/api/state").json["devices"]["fan"]["state"], "OFF")
        executed = client.post("/api/execute", json={"command_id": interpreted["command_id"]})
        self.assertEqual(executed.json["devices"]["fan"]["state"], "ON")
        self.assertEqual(executed.json["history"][0]["source"], "voice")
        self.assertEqual(client.post("/api/execute", json={"command_id": interpreted["command_id"]}).status_code, 409)
        manual = client.post("/api/control", json={"intent": "IncreaseSpeed", "device": "Fan"})
        self.assertEqual(manual.json["devices"]["fan"]["speed"], 2)
        self.assertEqual(service._predictor.calls, ["Fan on bay nang."])

    def test_all_actions_through_inference_pipeline(self):
        service = fixture_service({})
        client = create_app({"TESTING": True}, model_service=service).test_client()
        actions = [
            ("TurnOn", "Light", None), ("TurnOff", "Light", None),
            ("TurnOn", "Fan", None), ("IncreaseSpeed", "Fan", None),
            ("DecreaseSpeed", "Fan", None), ("TurnOff", "Fan", None),
            ("TurnOn", "AC", None), ("IncreaseTemp", "AC", None),
            ("DecreaseTemp", "AC", None), ("SetTemp", "AC", 21), ("TurnOff", "AC", None),
            ("Open", "Curtain", None), ("Close", "Curtain", None),
        ]
        for intent, device, value in actions:
            with self.subTest(intent=intent, device=device):
                service._predictor.output = {"intent": intent, "device": device, "value": value, "confidence": .99}
                interpreted = client.post("/api/interpret", json={"text": "Test-only inference input", "source": "voice"})
                self.assertEqual(interpreted.status_code, 200)
                executed = client.post("/api/execute", json={"command_id": interpreted.json["command_id"]})
                self.assertEqual(executed.status_code, 200)
                self.assertTrue(executed.json["execution"]["success"])

    def test_low_missing_and_invalid_confidence_never_execute(self):
        for confidence in (.1, None, True, float("nan"), 1.1, -1):
            with self.subTest(confidence=confidence):
                service = fixture_service({"intent": "TurnOn", "device": "Fan", "confidence": confidence})
                client = create_app({"TESTING": True}, model_service=service).test_client()
                response = client.post("/api/interpret", json={"text": "uncertain"})
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("command_id", response.json)
                self.assertEqual(response.json["devices"]["fan"]["state"], "OFF")

    def test_model_errors_are_graceful(self):
        for output, error in [(RuntimeError("test failure"), "model_inference_failed"),
                              (["bad format"], "model_output_invalid"),
                              ({"intent": "TurnOn", "confidence": .99}, "missing_device")]:
            with self.subTest(error=error):
                client = create_app({"TESTING": True}, model_service=fixture_service(output)).test_client()
                with self.assertLogs("backend.model_inference", level="ERROR") if isinstance(output, Exception) else nullcontext():
                    response = client.post("/api/interpret", json={"text": "test command"})
                self.assertEqual(response.json["error"], error)
                self.assertFalse(response.json["execution"]["success"])

    def test_invalid_inferred_action_reaches_controller_but_never_mutates(self):
        service = fixture_service({"intent": "Open", "device": "Light", "confidence": .95})
        client = create_app({"TESTING": True}, model_service=service).test_client()
        token = client.post("/api/interpret", json={"text": "wrong combination"}).json["command_id"]
        response = client.post("/api/execute", json={"command_id": token})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json["error"], "incompatible_action")
        self.assertEqual(response.json["devices"]["light"]["state"], "OFF")

    def test_expired_commands_are_rejected(self):
        client = create_app({"TESTING": True}, model_service=fixture_service({"intent": "TurnOn", "device": "Light", "confidence": .99})).test_client()
        with mock.patch("backend.app.monotonic", return_value=10):
            token = client.post("/api/interpret", json={"text": "turn on"}).json["command_id"]
        with mock.patch("backend.app.monotonic", return_value=100):
            response = client.post("/api/execute", json={"command_id": token})
        self.assertEqual(response.status_code, 409)

    def test_input_audio_limits_and_origin(self):
        for payload in ({}, [], {"text": ""}, {"text": "x" * 501}, {"text": 12}):
            self.assertEqual(self.client.post("/api/interpret", json=payload).status_code, 400)
        self.assertEqual(self.client.post("/api/control", data="invalid").status_code, 400)
        self.assertEqual(self.client.post("/api/control", json={"intent": "Open", "device": "Light"}).status_code, 422)
        self.assertEqual(self.client.post("/api/transcribe").status_code, 400)
        self.assertEqual(self.client.post("/api/transcribe", data={"audio": (io.BytesIO(b"audio"), "test.webm")}).status_code, 503)
        self.assertEqual(self.client.post("/api/control", json={"intent": "TurnOn", "device": "Light"}, headers={"Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/state").headers["Cache-Control"], "no-store")


class LoadingAndAdapterTests(TestCase):
    def test_codemix_temperature_requires_a_single_whole_value(self):
        for text, value in (
            ("AC temperature 26 lu zo nang", 26),
            ("Set the AC to twenty-two degrees", 22),
            ("Set the AC to 24.5 degrees", None),
            ("Set the AC to either 22 or 23 degrees", None),
            ("Set the AC to minus 24", None),
            ("Set the AC temperature", None),
        ):
            with self.subTest(text=text):
                self.assertEqual(temperature_value(text), value)

    def test_factory_loads_once_and_maps_original_labels(self):
        predictor = FixturePredictor({"action_id": 2, "entity": "ceiling_fan", "numeric": None, "score": .96})
        with TemporaryDirectory() as directory:
            config = Path(directory) / "model.json"
            config.write_text(json.dumps({
                "artifact_dir": ".", "factory": "tests.test_api:load_predictor",
                "intent_labels": {"2": "TurnOn"}, "device_labels": {"ceiling_fan": "Fan"},
                "output_fields": {"intent": "action_id", "device": "entity", "value": "numeric", "confidence": "score"},
            }), encoding="utf-8")
            factory = mock.Mock(return_value=predictor)
            with mock.patch("backend.model_inference.importlib.import_module", return_value=type("Module", (), {"load_predictor": factory})):
                service = ModelService(config)
                self.assertTrue(service.ready)
                for _ in range(3):
                    self.assertEqual(service.predict("Fan on bay nang.")["intent"], "TurnOn")
            factory.assert_called_once_with(Path(directory).resolve())
            self.assertEqual(len(predictor.calls), 3)

    def test_missing_artifacts_are_reported_without_stopping_manual_controls(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "model.json"
            config.write_text(json.dumps({"artifact_dir": "absent", "factory": "missing:factory"}), encoding="utf-8")
            with self.assertLogs("backend.model_inference", level="ERROR"):
                service = ModelService(config)
            self.assertFalse(service.ready)
            client = create_app({"TESTING": True}, model_service=service).test_client()
            self.assertEqual(client.post("/api/control", json={"device": "Light", "intent": "TurnOn"}).status_code, 200)
