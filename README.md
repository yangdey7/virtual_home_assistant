# virtual_home_assistant
Developing as a part of NLP project.

# Bhutanese Code-Mixed Smart Home Assistant

A local, assistive smart-bedroom simulation with a photorealistic bedroom, animated devices, accessible manual controls, speech input, and a Python command controller. No physical IoT hardware, paid API, frontend build, or cloud deployment is required.

**Model integration status:** the initial checkout contained only the two-line README above. No model weights, tokenizer, model architecture, label metadata, inference script, dataset, speech implementation, or dependency file was present. You indicated that you will add the trained model later. The interface and controller work now; **real voice/text device control is unavailable until your original model is connected**. The application never substitutes keyword rules or a fake classifier. No original model or project data was altered or retrained.

## Run locally

Use Python 3.10 or later. This implementation was checked with Python 3.13 and Flask 3.0.3.

From the project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.app
```

Open **http://127.0.0.1:5000**. Flask serves both the frontend and REST API, so there is no separate frontend server. Keep the terminal running; use Ctrl+C to stop it. Do not open `frontend/index.html` directly as a file. If Flask is already installed in your active environment, `python -m backend.app` is sufficient.

The application binds to the local computer only. An optional `PORT` environment variable changes the port. Run one Python process: this simulation intentionally stores one shared bedroom and the last 30 commands in memory. Restarting the server restores the initial state and clears history. Browser tabs share the same bedroom and refresh the server state every four seconds while idle.

## What works

- A responsive photorealistic bedroom inspired by the supplied reference: charcoal bedding, oak furniture, taupe linen curtains, indoor plants, warm ceiling-cove lighting, a pendant, ceiling fan, and wall AC. It uses local photographic plates with SVG device layers; see `frontend/assets/bedroom/README.md` for asset provenance and generation prompts.
- Warm illumination, fan rotation at three speeds, AC display and airflow, and curtain/daylight transitions. Reduced-motion preferences disable movement while retaining written state labels.
- All 13 specified device actions, controlled through a single backend manager.
- Keyboard-operable manual controls, an exact AC temperature input, prominent microphone, visible feedback, a skip link, and a live announcement region.
- Distinct transcription, model prediction, and execution results. Success is displayed only after the controller response.
- Recent transcript, intent, device, value, source, timestamp (Asia/Thimphu), and execution result, including rejected commands.
- An explicit model adapter, load-once lifecycle, configurable confidence threshold, graceful missing-model behavior, optional local Whisper, and browser speech fallback.

### Controller behavior

| Device | Actions | Rules |
| --- | --- | --- |
| Light | `TurnOn`, `TurnOff` | Crossfades matching photographic lighting states: ceiling-cove lights, pendant and table lamp illuminate the actual room. |
| Fan | `TurnOn`, `TurnOff`, `IncreaseSpeed`, `DecreaseSpeed` | Levels 1–3. Speed changes require the fan to be on. Speed is preserved when off. At limits, the controller rejects further changes; manual buttons are disabled. |
| AC | `TurnOn`, `TurnOff`, `IncreaseTemp`, `DecreaseTemp`, `SetTemp` | Whole degrees, 16–30°C by default. The temperature is always displayed directly on the AC, with a separate OFF/COOLING status. Out-of-range and missing values are rejected. Adjusting an off AC saves the setting and explicitly reports that the AC is still off. |
| Curtain | `Open`, `Close` | Smoothly opens/closes the two panels and changes daylight. |

Initial state: light OFF, fan OFF at level 1, AC OFF at 24°C, curtains CLOSED. `AC_MIN_TEMP` and `AC_MAX_TEMP` configure the temperature bounds before startup; they must contain the initial 24°C setting and stay within 10–40°C. The controller validates every intent, device, compatibility, required value, limit, and relevant current state before applying a command. Rejected commands never partially change the room.

## Connect your original trained NLP model later

The model architecture and actual output format are **unknown until you supply the original files**. The integration boundary deliberately makes no assumptions about Transformers, PyTorch, TensorFlow, tokenization, or whether intent/entities use separate heads or separate models.

Please add or identify:

1. Original model weights and architecture/configuration, or the complete saved model directory.
2. The exact tokenizer/vocabulary and text preprocessing code used during training.
3. The working inference script and its dependencies/versions.
4. Original intent/device label mappings, including label IDs and entity/BIO tags if used.
5. A real inference input/output example, including confidence/logits and temperature/value extraction.

Keep large artifacts in their current location if preferred; absolute external paths are supported. The `models/` directory and your private `model_config.json` are ignored by Git to prevent accidentally committing large weights or local paths. No files are automatically moved or downloaded.

### Provider contract

Once the original inference code is available, write a small wrapper **around that code**. Its factory receives the configured artifact directory as a `pathlib.Path`, loads the original model and tokenizer once, and returns an object with `predict(text)`:

```python
# Example CONTRACT only — implement using your original inference module.
def load_predictor(artifact_dir):
    # Load original weights/tokenizer and initialize original inference here.
    # Return the original predictor or a thin wrapper exposing predict(text).
    ...
```

The returned prediction must be a plain Python dictionary. It can retain original label IDs or names; explicit mappings in the configuration normalize them. For nested tensors, logits, token tags, or multiple model heads, the wrapper must use the original decoding logic and return JSON-compatible Python values. **Never infer the intent/device with fallback keyword rules.**

The normalized contract is:

```json
{
  "intent": "SetTemp",
  "device": "AC",
  "value": 24,
  "confidence": 0.96
}
```

`value` is null for actions other than `SetTemp`. The wrapper must obtain the numeric temperature from the actual original model/entity pipeline. `confidence` must come from real model outputs, be finite, and be between 0 and 1. It must cover the complete command, including intent, device, and any required value. If heads are separate, use a justified aggregation (for example, the minimum of their relevant confidence scores). A model without a trustworthy confidence measure needs an explicit confidence policy implemented and evaluated against the original outputs; this application rejects missing confidence rather than treating it as certainty. The threshold is configurable and defaults to 0.8; it has not been calibrated against your absent model.

### Configuration

Copy the sample and edit the factory and artifact path:

```powershell
Copy-Item model_config.example.json model_config.json
$env:MODEL_CONFIG = (Resolve-Path .\model_config.json).Path
.\.venv\Scripts\python.exe -m backend.app
```

The factory uses Python's `module:function` form. Put your wrapper in an importable module inside this project or install your original inference package into the same virtual environment. Install its original Python dependencies as well. Relative artifact paths resolve against the configuration file's directory.

`output_fields` maps normalized field names to your provider's actual top-level dictionary keys. `intent_labels` and `device_labels` map the **string representation** of original IDs or labels into the following supported controller labels:

- Intents: `TurnOn`, `TurnOff`, `IncreaseSpeed`, `DecreaseSpeed`, `IncreaseTemp`, `DecreaseTemp`, `SetTemp`, `Open`, `Close`.
- Devices: `Light`, `Fan`, `AC`, `Curtain`.

For example, if your real model returns `{"action_id": 2, "entity": "ceiling_fan", "score": 0.96}`, use `"intent": "action_id"`, `"device": "entity"`, and `"confidence": "score"` under `output_fields`, with `{"2": "TurnOn"}` under `intent_labels` and `{"ceiling_fan": "Fan"}` under `device_labels`. This only illustrates configuration; these are not claims about your actual model labels.

The application creates exactly one `ModelService` on startup; its factory is called once. Requests reuse that predictor under a lock. The launcher disables Flask's reloader so it cannot accidentally create a second model copy. Restart after changing artifacts/configuration. A missing factory, artifact directory, dependency, invalid model output, or inference error produces a visible error and leaves manual control usable.

## Speech input

No Whisper implementation or weights were present in the supplied workspace.

By default, supported browsers can use `SpeechRecognition`/`webkitSpeechRecognition` with English (`en-US`) as a practical fallback. This is **browser speech recognition, not Whisper**; some browsers send audio to their own online recognition service. The interface labels the engine. Unsupported browsers offer typed and manual input. Use localhost/127.0.0.1 and allow microphone permission. See [MDN's SpeechRecognition documentation](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).

To use a **local pretrained faster-whisper model**, install the optional dependencies and point to a complete, already downloaded faster-whisper/CTranslate2 model folder, including `model.bin`, `config.json`, and `tokenizer.json`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-speech.txt
$env:WHISPER_MODEL = 'D:\path\to\your\local\faster-whisper-model'
.\.venv\Scripts\python.exe -m backend.app
```

This optional implementation follows the [faster-whisper local model interface](https://github.com/SYSTRAN/faster-whisper). It loads once on CPU with int8 computation and `local_files_only=True`; the app does not automatically download model weights. OpenAI Whisper `.pt` files and Hugging Face Transformer directories are not interchangeable with this CTranslate2 format. If your eventual project includes another working Whisper implementation, adapt `SpeechService` to reuse it instead of duplicating it.

With local Whisper ready, the microphone records using `MediaRecorder`. Tap once to start and again to finish; recording also stops after 15 seconds. Audio is uploaded to `/api/transcribe`, decoded in memory, and is not saved by the application. Requests are limited to 8 MB. The recognized text then uses exactly the same NLP path as typed text. Microphone tracks are released after recording and on page exit.

English and Bhutanese code-mixed recognition depend on the selected speech engine, pronunciation, and actual NLP training data. **Full Dzongkha speech support is not claimed.** Real microphone/audio quality and model accuracy need testing on your machine with your recordings after adding the actual model(s).

## Architecture and API

```text
Microphone → browser speech or local Whisper → recognized text
Typed input ────────────────────────────────────────┘
   → original trained predictor → output adapter → confidence gate
   → single-use pending command → Python controller → authoritative state
Manual controls ────────────────────────────────────────┘
   → rendered bedroom + feedback + recent history
```

| File | Responsibility |
| --- | --- |
| `backend/app.py` | Flask app factory, local static serving, REST routes, one-time services, error responses. |
| `backend/device_manager.py` | Shared state, validation, atomic commands, bounded history under an `RLock`. |
| `backend/model_inference.py` | Configured original-provider loading, output mapping, confidence validation. |
| `backend/speech_recognition.py` | Optional local pretrained Whisper lifecycle and transcription. |
| `frontend/index.html` | Accessible layout, photographic room plates, perspective fan, moving curtain masks and live AC display. |
| `frontend/assets/bedroom/` | Local photographic daylight, warm-light and curtain plates with generation provenance. |
| `frontend/css/style.css` | Responsive warm/sage styling, room states, motion and focus behavior. |
| `frontend/js/bedroom.js` | Render server state and history; manual-control availability. |
| `frontend/js/voice.js` | Microphone lifecycle, recording, browser speech, permission/no-speech errors. |
| `frontend/js/app.js` | Assistant stages, manual commands, state synchronization and feedback. |
| `frontend/js/api.js` | Shared HTTP requests, error handling and request timeouts. |

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Backend, original model and local Whisper availability. |
| `GET /api/state` | Devices, monotonic revision, history and configurable limits. |
| `POST /api/control` | Manual `{intent, device, value}` through the shared controller. |
| `POST /api/interpret` | `{text, source: "voice" or "text"}` → real prediction and a pending command ID. No device changes occur here. |
| `POST /api/execute` | `{command_id}` → validate and execute the server-stored prediction once. IDs expire after 60 seconds. |
| `POST /api/transcribe` | Multipart `audio` → transcript from configured local Whisper. |

The split between interpretation and execution lets the interface display the real prediction before applying it. The frontend cannot silently substitute a different inferred command at execution time. All manual actions call the same controller. API errors contain understandable messages; available snapshots keep the UI synchronized. The frontend ignores older state revisions. No CORS is enabled; mutating requests from a different browser origin are rejected.

## Tests

Backend/controller/adapter checks use the standard library and Flask test client:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

They cover all 13 actions through both the controller and inference routes, limits, off-state behavior, incompatible commands, missing values/devices, uncertain/malformed predictions, missing artifacts, inference failure, load-once behavior, original label mapping, history limits, expired/replayed commands, and HTTP errors.

Optional real-browser QA uses Node.js and Playwright (development dependencies only):

```powershell
npm ci
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.cache\ms-playwright'
npx playwright install chromium
npm run check
npm run test:browser
```

Ensure `python` in this terminal is the Python environment with Flask installed. Playwright starts/stops its own **test-only** Flask server on port 5035. Browser checks cover manual device actions, animations, speech events, permission/no-speech/network errors, prediction-before-execution behavior, low confidence, model/controller/backend errors, keyboard control, reduced motion, and responsive widths from 320 to 1440 pixels. Screenshots are saved under ignored `test-results/`.

**Test-only fixtures:** `tests/test_api.py` and `tests/browser_server.py` inject explicit deterministic predictions to check integration behavior. Browser speech is simulated in automated tests. These fixtures are never imported by `backend.app` and are not a fallback classifier. Do not launch `tests.browser_server` to use the app. These tests verify the plumbing and UI, **not actual NLP accuracy, live microphone permission dialogs, real Whisper transcription, or Bhutanese speech quality**. Verify those with the original artifacts and microphone when available.

For a final manual check after model setup: turn each device on/off, vary fan speed, set AC to both bounds and an exact value, open/close curtains, then repeat those actions with English and your dataset's code-mixed utterances. Check that transcripts, original decoded labels, confidence, execution results and room state agree. Try silence, permission denial, an unknown device/action, a missing or out-of-range temperature, and an uncertain command; rejected commands must leave the bedroom unchanged.
