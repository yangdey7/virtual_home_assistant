"""Browser-QA fixture server ONLY. Never run this to use the application.

This fixture intentionally permits tests to select a deterministic prediction.
It makes no claims about the unavailable trained model's accuracy.
"""

from flask import jsonify, request

from backend.app import create_app
from .test_api import fixture_service


def make_fixture_app():
    service = fixture_service({"intent": "TurnOn", "device": "Fan", "value": None, "confidence": .99})
    app = create_app({"TESTING": True, "WHISPER_MODEL": None}, model_service=service)

    @app.post("/__test__/prediction")
    def prediction():
        service._predictor.output = request.get_json()
        return jsonify({"test_fixture": True})

    return app


if __name__ == "__main__":
    make_fixture_app().run(host="127.0.0.1", port=5035, use_reloader=False, debug=False)
