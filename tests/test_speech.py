"""Optional speech wrapper behavior, using test-only Whisper doubles."""

import io
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock

from backend.errors import CommandError
from backend.speech_recognition import SpeechService


class SpeechTests(TestCase):
    def test_unconfigured_service_reports_unavailable(self):
        service = SpeechService()
        self.assertFalse(service.status()["ready"])
        with self.assertRaises(CommandError) as error:
            service.transcribe(io.BytesIO(b"test"))
        self.assertEqual(error.exception.code, "speech_unavailable")

    def test_missing_whisper_folder_is_graceful(self):
        with TemporaryDirectory() as directory:
            with self.assertLogs("backend.speech_recognition", level="ERROR"):
                service = SpeechService(Path(directory) / "absent")
            self.assertFalse(service.status()["ready"])

    def test_local_whisper_loads_once_and_transcription_reuses_it(self):
        model = mock.Mock()
        model.transcribe.side_effect = lambda *a, **kw: (
            iter([SimpleNamespace(text=" Fan on "), SimpleNamespace(text=" bay nang. ")]),
            SimpleNamespace(language="en"),
        )
        factory = mock.Mock(return_value=model)
        module = SimpleNamespace(WhisperModel=factory)
        with TemporaryDirectory() as directory:
            (Path(directory) / "tokenizer.json").write_text("{}", encoding="utf-8")
            with mock.patch.dict(sys.modules, {"faster_whisper": module}):
                service = SpeechService(directory)
                self.assertTrue(service.status()["ready"])
                for _ in range(2):
                    self.assertEqual(service.transcribe(io.BytesIO(b"fixture"))["text"], "Fan on bay nang.")
        factory.assert_called_once_with(str(Path(directory).resolve()), device="cpu", compute_type="int8", local_files_only=True)
        self.assertEqual(model.transcribe.call_count, 2)

    def test_silence_and_decode_failures_are_actionable(self):
        service = SpeechService()
        service.model = mock.Mock()
        service.model.transcribe.return_value = (iter([]), SimpleNamespace(language="en"))
        with self.assertRaises(CommandError) as error:
            service.transcribe(io.BytesIO())
        self.assertEqual(error.exception.code, "no_speech")
        service.model.transcribe.side_effect = RuntimeError("test-only decode failure")
        with self.assertLogs("backend.speech_recognition", level="ERROR"):
            with self.assertRaises(CommandError) as error:
                service.transcribe(io.BytesIO())
        self.assertEqual(error.exception.code, "speech_failed")
