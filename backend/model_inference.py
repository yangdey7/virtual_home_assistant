"""Load the configured model provider and validate its command predictions."""

import importlib
import json
import logging
import math
from pathlib import Path
from threading import Lock

from .errors import CommandError

logger = logging.getLogger(__name__)


class ModelService:
    def __init__(self, config_path=None):
        self._predictor = None
        self._lock = Lock()
        self.config = {}
        self.message = "Trained model not connected. Add the original artifacts and inference code, then configure MODEL_CONFIG."
        self.status_code = "model_not_configured"
        if not config_path:
            return
        try:
            config_file = Path(config_path).resolve()
            config = json.loads(config_file.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("The model configuration must be a JSON object.")
            self.config = config
            artifact_dir = Path(self.config["artifact_dir"])
            if not artifact_dir.is_absolute():
                artifact_dir = config_file.parent / artifact_dir
            if not artifact_dir.is_dir():
                raise ValueError("The configured artifact_dir does not exist.")
            module_name, factory_name = self.config["factory"].split(":", 1)
            factory = getattr(importlib.import_module(module_name), factory_name)
            self._configure_adapter()
            predictor = factory(artifact_dir.resolve())
            if not callable(getattr(predictor, "predict", None)):
                raise ValueError("The model factory must return an object with predict(text).")
            self._predictor = predictor
            self.message = "Original inference provider loaded."
            self.status_code = "ready"
        except Exception:
            logger.exception("Unable to load the configured trained model")
            self.message = "The trained model could not be loaded. Check the artifact path, inference factory, dependencies, and server log."
            self.status_code = "model_load_failed"

    def _configure_adapter(self):
        self.threshold = self.config.get("confidence_threshold", 0.8)
        if type(self.threshold) not in (int, float) or not math.isfinite(self.threshold) or not 0 < self.threshold <= 1:
            raise ValueError("confidence_threshold must be greater than 0 and at most 1.")
        self.fields = {"intent": "intent", "device": "device", "value": "value",
                       "confidence": "confidence", **self.config.get("output_fields", {})}
        if any(not isinstance(v, str) for v in self.fields.values()):
            raise ValueError("output_fields must contain string dictionary keys.")
        self.intent_labels = self.config.get("intent_labels", {})
        self.device_labels = self.config.get("device_labels", {})

    @property
    def ready(self):
        return self._predictor is not None

    def status(self):
        status = {"ready": self.ready, "code": self.status_code, "message": self.message}
        name = self.config.get("name")
        if isinstance(name, str) and name:
            status["name"] = name
        return status

    def predict(self, text):
        if not self.ready:
            raise CommandError(self.message, self.status_code, 503)
        try:
            with self._lock:
                raw = self._predictor.predict(text)
            return self._adapt(raw)
        except CommandError:
            raise
        except Exception as exc:
            logger.exception("Model inference failed")
            raise CommandError("The language model couldn't process this command. Please try again.", "model_inference_failed", 503) from exc

    def _adapt(self, raw):
        if not isinstance(raw, dict):
            raise CommandError("The inference provider returned an unsupported format. Check the model adapter.", "model_output_invalid", 503)
        confidence = raw.get(self.fields["confidence"])
        # A score must represent confidence in the whole intent/device/value command.
        # The original inference wrapper must supply this from real model outputs.
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise CommandError("The model did not provide a valid command confidence. Nothing was changed.", "missing_confidence", 422)
        intent = raw.get(self.fields["intent"])
        device = raw.get(self.fields["device"])
        prediction = {
            "intent": self.intent_labels.get(str(intent), intent),
            "device": self.device_labels.get(str(device), device),
            "value": raw.get(self.fields["value"]),
            "confidence": confidence,
        }
        if confidence < self.threshold:
            error = CommandError("I'm not confident I understood. Please repeat the action and device. Nothing was changed.", "low_confidence")
            error.prediction = prediction
            raise error
        # Validation is also performed by the controller; missing labels never default.
        from .device_manager import ALLOWED, INTENTS
        if not isinstance(prediction["intent"], str) or prediction["intent"] not in INTENTS:
            error = CommandError("I couldn't recognize the action. Please repeat your command.", "unknown_intent")
            error.prediction = prediction
            raise error
        if not isinstance(prediction["device"], str) or prediction["device"] not in ALLOWED:
            error = CommandError("Please name the device: light, fan, AC, or curtains.", "missing_device")
            error.prediction = prediction
            raise error
        return prediction

