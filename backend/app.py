"""Run with: python -m backend.app (one process; no model-reloading debug server)."""

import logging
import os
import secrets
from pathlib import Path
from threading import Lock
from time import monotonic

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .device_manager import DeviceManager
from .errors import CommandError
from .model_inference import ModelService
from .speech_recognition import SpeechService

ROOT = Path(__file__).resolve().parent.parent


def create_app(config=None, *, model_service=None, speech_service=None):
    app = Flask(__name__, static_folder=str(ROOT / "frontend"), static_url_path="/static")
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        MODEL_CONFIG=os.environ.get("MODEL_CONFIG"),
        WHISPER_MODEL=os.environ.get("WHISPER_MODEL"),
        AC_MIN_TEMP=int(os.environ.get("AC_MIN_TEMP", 16)),
        AC_MAX_TEMP=int(os.environ.get("AC_MAX_TEMP", 30)),
    )
    if config:
        app.config.update(config)
    manager = DeviceManager(app.config["AC_MIN_TEMP"], app.config["AC_MAX_TEMP"])
    nlp = model_service if model_service is not None else ModelService(app.config["MODEL_CONFIG"])
    speech = speech_service if speech_service is not None else SpeechService(app.config["WHISPER_MODEL"])
    app.extensions.update(device_manager=manager, model_service=nlp, speech_service=speech)
    pending = {}
    pending_lock = Lock()

    def body():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise CommandError("Send a JSON object with the required command fields.", "invalid_request", 400)
        return payload

    @app.before_request
    def same_origin_mutations():
        # No CORS: another website must not control the local bedroom or microphone.
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                raise CommandError("Use the application from the same local address as the backend.", "invalid_origin", 403)

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "online", "model": nlp.status(), "speech": speech.status()})

    @app.get("/api/state")
    def state():
        return jsonify(manager.snapshot())

    @app.post("/api/control")
    def manual_control():
        payload = body()
        command = {key: payload.get(key) for key in ("intent", "device", "value")}
        return jsonify(manager.execute(command, "Manual control", "manual"))

    @app.post("/api/interpret")
    def interpret():
        payload = body()
        text = payload.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
            raise CommandError("Enter a command between 1 and 500 characters.", "invalid_text", 400)
        text = text.strip()
        source = "voice" if payload.get("source") == "voice" else "text"
        try:
            prediction = nlp.predict(text)
        except CommandError as exc:
            prediction = getattr(exc, "prediction", None)
            manager.record_failure(text, prediction, source, str(exc))
            raise
        token = secrets.token_urlsafe(24)
        with pending_lock:
            now = monotonic()
            for key in list(pending):
                if pending[key]["expires"] < now:
                    del pending[key]
            if len(pending) >= 100:
                raise CommandError("Too many commands are waiting. Please try again shortly.", "busy", 429)
            pending[token] = {"command": prediction, "text": text, "source": source, "expires": now + 60}
        return jsonify({"transcript": text, "prediction": prediction, "command_id": token})

    @app.post("/api/execute")
    def execute():
        command_id = body().get("command_id")
        if not isinstance(command_id, str):
            raise CommandError("Interpret a command before executing it.", "missing_command", 400)
        with pending_lock:
            command = pending.pop(command_id, None)
        if command is None or command["expires"] < monotonic():
            raise CommandError("This command has expired or was already applied. Please speak again.", "expired_command", 409)
        result = manager.execute(command["command"], command["text"], command["source"])
        return jsonify({**result, "prediction": command["command"], "transcript": command["text"]})

    @app.post("/api/transcribe")
    def transcribe():
        recording = request.files.get("audio")
        if recording is None:
            raise CommandError("Record a voice command before sending it.", "missing_audio", 400)
        return jsonify(speech.transcribe(recording.stream))

    @app.errorhandler(CommandError)
    def command_error(error):
        return jsonify({"error": error.code, "message": str(error),
                        "prediction": getattr(error, "prediction", None),
                        "execution": {"success": False}, **manager.snapshot()}), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({"error": error.name, "message": error.description,
                        "execution": {"success": False}}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unexpected application error")
        return jsonify({"error": "server_error", "message": "The server encountered a problem. Check its log and try again.",
                        "execution": {"success": False}, **manager.snapshot()}), 500

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    model_dir = ROOT / "models"
    whisper_dir = model_dir / "whisper_finetuned_codemix" / "final_model_whisper"
    model_config = os.environ.get("MODEL_CONFIG")
    if model_config is None and (model_dir / "intent_model/checkpoint-260/model.safetensors").is_file():
        model_config = ROOT / "model_config.codemix.json"
    whisper_model = os.environ.get("WHISPER_MODEL")
    if whisper_model is None and (whisper_dir / "model.safetensors").is_file():
        whisper_model = whisper_dir
    app = create_app({"MODEL_CONFIG": model_config, "WHISPER_MODEL": whisper_model})
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True, use_reloader=False)

