# virtual_home_assistant
Developing as a part of NLP project.

# Bhutanese Code-Mixed Smart Home Assistant

A local, assistive smart-bedroom simulation with a photorealistic bedroom, animated devices, accessible manual controls, speech input, and a Python command controller. No physical IoT hardware, paid API, frontend build, or cloud deployment is required.

The app supports a local DistilBERT trial, the supplied XLM-RoBERTa intent and device classifiers, and fine-tuned Whisper for speech. Manual controls also work in a checkout without model files.

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
| Fan | `TurnOn`, `TurnOff`, `IncreaseSpeed`, `DecreaseSpeed` | Levels 1–3. Speed changes require the fan to be on. Speed is preserved when off. The blades gradually decelerate for approximately 3–5 seconds after OFF; turning it back on resumes from its current rotation. Reduced-motion preferences disable rotation. At limits, the controller rejects further changes; manual buttons are disabled. |
| AC | `TurnOn`, `TurnOff`, `IncreaseTemp`, `DecreaseTemp`, `SetTemp` | Whole degrees, 16–30°C by default. The unit displays its temperature and COOLING while on, and only OFF when switched off. The saved temperature is preserved in the manual controls. Out-of-range and missing values are rejected. Adjusting an off AC saves the setting and explicitly reports that the AC is still off. |
| Curtain | `Open`, `Close` | Smoothly opens/closes the two panels and changes daylight. |

Initial state: light OFF, fan OFF at level 1, AC OFF at 24°C, curtains CLOSED. `AC_MIN_TEMP` and `AC_MAX_TEMP` configure the temperature bounds before startup; they must contain the initial 24°C setting and stay within 10–40°C. The controller validates every intent, device, compatibility, required value, limit, and relevant current state before applying a command. Rejected commands never partially change the room.

## Run the supplied models

Place the inference files in these directories. Each trained export needs `model.safetensors`, `config.json`, and the tokenizer and processor JSON files where provided.

- `models/distilbert_intent_model/`
- `models/distilbert_multitask_model/`
- `models/best_device_model/`
- `models/intent_model/checkpoint-260/`
- `models/whisper_finetuned_codemix/final_model_whisper/`

The supplied DistilBERT ZIP includes `config.json`, `tokenizer.json`, `tokenizer_config.json`, and `device_config.json` under `distilbert_output/distilbert_intent_model/`, along with the data splits under `distilbert_output/splits/`. Place the trained or retrained `model.safetensors` beside the four configuration and tokenizer files.

From the project directory, using the virtual environment from the local setup above:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
.\.venv\Scripts\python.exe -m backend.app
```

The local launcher prefers multitask DistilBERT when its four export files are present. It can also select intent-only DistilBERT and XLM-RoBERTa, in that order. `MODEL_CONFIG` and `WHISPER_MODEL` override automatic selection. Inference loads weights from disk, and Git ignores the `models/` directory. Check `/api/health` for `model.name`, `model.ready`, and `speech.ready`.

To switch classifiers for a trial, stop the server, set `MODEL_CONFIG` to the desired file, and restart it in the same PowerShell session.

```powershell
$env:MODEL_CONFIG = 'model_config.codemix.json'   # XLM-RoBERTa
# $env:MODEL_CONFIG = 'model_config.distilbert.json'  # DistilBERT with device keywords
# $env:MODEL_CONFIG = 'model_config.distilbert_multitask.json'  # DistilBERT with two trained heads
.\.venv\Scripts\python.exe -m backend.app
```

Set `$env:MODEL_CONFIG = $null` to restore automatic selection on the next restart.

Intent-only DistilBERT uses its saved cased tokenizer, 64-token limit, and intent labels. It requires a whole-word or phrase match for exactly one device using the notebook's keyword list. Its confidence score is the intent softmax score. All three configurations apply a 0.8 confidence threshold and use the same temperature extraction and controller.

Train the two-head model by opening `distilbert_multitask_colab.ipynb` in Colab, selecting a GPU, and uploading `dataset.xlsx` when prompted. The notebook evaluates intent, device, and joint accuracy and saves its export under `My Drive/distilbert_multitask_runs/`. Copy `model.safetensors`, `config.json`, `tokenizer.json`, and `tokenizer_config.json` to `models/distilbert_multitask_model/` and restart the app. Both heads run from one encoder pass. The app compares the lower head score against the confidence threshold. For comparisons, use the same held-out commands and track correct predictions that pass that threshold.

The XLM-RoBERTa intent checkpoint uses the device export's tokenizer when its own tokenizer is absent. Both XLM-RoBERTa exports use generic numeric labels. The adapter maps those IDs using predictions on the labeled evaluation transcripts bundled with Whisper. The command score is the lower of the two classifier softmax scores. The default 0.8 threshold rejected many fan speed, relative AC temperature, and curtain commands on those transcripts. `SetTemp` accepts a single whole-number temperature in digits or English number words, and the controller validates its range.

### Configure another NLP provider

The configured factory receives the artifact directory as a `pathlib.Path` and returns an object with a `predict(text)` method. Predictions are plain Python dictionaries with JSON-compatible values. Configuration can map original output names and label IDs.

The normalized contract is:

```json
{
  "intent": "SetTemp",
  "device": "AC",
  "value": 24,
  "confidence": 0.96
}
```

`value` is null for actions other than `SetTemp`. Supply the numeric temperature for `SetTemp`. `confidence` comes from the model outputs and must be finite and between 0 and 1. The threshold is configurable and defaults to 0.8.

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

The supplied fine-tuned Whisper export uses the saved processor and generation settings. The app decodes audio at the saved sampling rate and lets Whisper detect the language for code-mixed transcription. [Hugging Face Whisper documentation](https://huggingface.co/docs/transformers/v5.19.0/model_doc/whisper)

By default, supported browsers can use `SpeechRecognition`/`webkitSpeechRecognition` with English (`en-US`) as a practical fallback. This is **browser speech recognition, not Whisper**; some browsers send audio to their own online recognition service. The interface labels the engine. Unsupported browsers offer typed and manual input. Use localhost/127.0.0.1 and allow microphone permission. See [MDN's SpeechRecognition documentation](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).

To use a **local pretrained faster-whisper model**, install the optional dependencies and point to a complete, already downloaded faster-whisper/CTranslate2 model folder, including `model.bin`, `config.json`, and `tokenizer.json`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-speech.txt
$env:WHISPER_MODEL = 'D:\path\to\your\local\faster-whisper-model'
.\.venv\Scripts\python.exe -m backend.app
```

The CTranslate2 implementation loads once on CPU with int8 computation and `local_files_only=True`. [faster-whisper local model interface](https://github.com/SYSTRAN/faster-whisper)

With local Whisper ready, the microphone records using `MediaRecorder`. Tap once to start and again to finish; recording also stops after 15 seconds. Audio is uploaded to `/api/transcribe`, decoded in memory, and is not saved by the application. Requests are limited to 8 MB. The recognized text then uses exactly the same NLP path as typed text. Microphone tracks are released after recording and on page exit.

English and Bhutanese code-mixed recognition depend on the selected speech engine and the recording.

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
| `backend/codemix_inference.py` | Supplied XLM-R checkpoints, label mapping, and temperature extraction. |
| `backend/distilbert_inference.py` | DistilBERT intent checkpoint and device keyword matching. |
| `backend/speech_recognition.py` | Local Whisper loading and transcription. |
| `frontend/index.html` | Accessible layout, photographic room plates, perspective fan, moving curtain masks and live AC display. |
| `frontend/assets/bedroom/` | Local photographic daylight, warm-light and curtain plates with generation provenance. |
| `frontend/css/style.css` | Responsive warm/sage styling, room states, motion and focus behavior. |
| `frontend/js/bedroom.js` | Render server state and history; manual-control availability. |
| `frontend/js/fan.js` | Perspective rotor motion, smooth speed changes and deceleration, reduced-motion handling. |
| `frontend/js/voice.js` | Microphone lifecycle, recording, browser speech, permission/no-speech errors. |
| `frontend/js/app.js` | Assistant stages, manual commands, state synchronization and feedback. |
| `frontend/js/api.js` | Shared HTTP requests, error handling and request timeouts. |

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Backend, original model and local Whisper availability. |
| `GET /api/state` | Devices, monotonic revision, history and configurable limits. |
| `POST /api/control` | Manual `{intent, device, value}` through the shared controller. |
| `POST /api/interpret` | `{text, source: "voice" or "text"}` → model prediction, pending command ID, and `requires_confirmation`. |
| `POST /api/execute` | `{command_id}` → validate and execute the server-stored prediction once. IDs expire after 60 seconds. |
| `POST /api/transcribe` | Multipart `audio` → transcript from configured local Whisper. |

For a typed or spoken command, the interface applies the prediction directly when the text explicitly names one supported device and the predicted device matches it. The check accepts English names and aliases from the code-mixed dataset, including `pangka` and `pardha`. A missing device name, multiple different devices, or a predicted device that differs from the mention opens a confirmation dialog. The dialog shows the proposed action and the command text. Cancel or Escape closes it without applying the action. The model confidence threshold and controller validation apply to every inferred command. All manual actions call the same controller immediately. API errors contain understandable messages; available snapshots keep the UI synchronized. The frontend ignores older state revisions. No CORS is enabled; mutating requests from a different browser origin are rejected.

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
