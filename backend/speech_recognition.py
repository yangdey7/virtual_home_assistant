"""Optional local pretrained Whisper. Never downloads weights on startup."""

import logging
from pathlib import Path
from threading import Lock

from .errors import CommandError

logger = logging.getLogger(__name__)


class SpeechService:
    def __init__(self, model_path=None):
        self.model = None
        self._lock = Lock()
        self.message = "Local Whisper isn't configured. Browser speech recognition is an optional fallback."
        if not model_path:
            return
        try:
            directory = Path(model_path).resolve()
            if not directory.is_dir() or not (directory / "tokenizer.json").is_file():
                raise ValueError("WHISPER_MODEL must be a local faster-whisper directory including tokenizer.json.")
            from faster_whisper import WhisperModel
            self.model = WhisperModel(str(directory), device="cpu", compute_type="int8", local_files_only=True)
            self.message = "Local pretrained Whisper is ready. Transcription quality depends on the language and recording."
        except Exception:
            logger.exception("Unable to load local Whisper")
            self.message = "Local Whisper couldn't load. Check WHISPER_MODEL and the optional speech dependencies."

    def status(self):
        return {"ready": self.model is not None, "engine": "whisper" if self.model else None, "message": self.message}

    def transcribe(self, audio_file):
        if self.model is None:
            raise CommandError(self.message, "speech_unavailable", 503)
        try:
            with self._lock:
                segments, info = self.model.transcribe(audio_file, beam_size=5, vad_filter=True)
                text = " ".join(segment.text.strip() for segment in segments).strip()
            if not text:
                raise CommandError("No speech was detected. Please speak again.", "no_speech")
            return {"text": text, "language": info.language, "engine": "whisper"}
        except CommandError:
            raise
        except Exception as exc:
            logger.exception("Speech recognition failed")
            raise CommandError("The recording couldn't be transcribed. Please try again or type your command.", "speech_failed", 422) from exc

