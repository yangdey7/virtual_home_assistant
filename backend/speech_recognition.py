"""Transcribe audio with a local Whisper model."""

import logging
from itertools import chain
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
                raise ValueError("WHISPER_MODEL must be a local Whisper directory including tokenizer.json.")
            if (directory / "model.safetensors").is_file():
                self.model = FineTunedWhisper(directory)
                self.message = "Local fine-tuned Whisper is ready."
            else:
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
                if isinstance(self.model, FineTunedWhisper):
                    text, language = self.model.transcribe(audio_file), None
                else:
                    segments, info = self.model.transcribe(audio_file, beam_size=5, vad_filter=True)
                    text = " ".join(segment.text.strip() for segment in segments).strip()
                    language = info.language
            if not text:
                raise CommandError("No speech was detected. Please speak again.", "no_speech")
            return {"text": text, "language": language, "engine": "whisper"}
        except CommandError:
            raise
        except Exception as exc:
            logger.exception("Speech recognition failed")
            raise CommandError("The recording couldn't be transcribed. Please try again or type your command.", "speech_failed", 422) from exc


class FineTunedWhisper:
    def __init__(self, directory):
        import av
        import numpy as np
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        self.av = av
        self.np = np
        self.torch = torch
        self.processor = WhisperProcessor.from_pretrained(directory, local_files_only=True)
        self.model = WhisperForConditionalGeneration.from_pretrained(
            directory, local_files_only=True, use_safetensors=True,
        ).eval()

    def transcribe(self, audio_file):
        feature_extractor = self.processor.feature_extractor
        waveform = self._decode(audio_file, feature_extractor.sampling_rate, feature_extractor.n_samples)
        if waveform is None or not waveform.any():
            return ""
        inputs = self.processor(
            audio=waveform, sampling_rate=feature_extractor.sampling_rate,
            return_tensors="pt", return_attention_mask=True,
        )
        with self.torch.inference_mode():
            predicted_ids = self.model.generate(
                inputs.input_features, attention_mask=inputs.attention_mask, max_new_tokens=128,
            )
        return self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0].strip()

    def _decode(self, audio_file, sampling_rate, max_samples):
        resampler = self.av.AudioResampler(format="fltp", layout="mono", rate=sampling_rate)
        chunks = []
        samples = 0
        with self.av.open(audio_file, mode="r") as container:
            for frame in chain(container.decode(audio=0), (None,)):
                for converted in resampler.resample(frame):
                    samples += converted.samples
                    if samples > max_samples:
                        raise CommandError("Record a command of 30 seconds or less.", "audio_too_long")
                    chunks.append(converted.to_ndarray().ravel())
        if chunks:
            return self.np.concatenate(chunks)

