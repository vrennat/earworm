"""Narration contract tests with deterministic fake audio; no models or servers."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from earworm.tts import NarrationRequest
from earworm.tts.audio import mastering_lead_seconds
from earworm.tts.base import speech_text
from earworm.tts.chunks import sentence_chunks
from earworm.tts.kokoro_engine import KokoroEngine
from earworm.tts.voicebox_engine import VoiceboxEngine


class FakeVoicebox(VoiceboxEngine):
    def __init__(self, cache: Path):
        super().__init__({"voicebox": {
            "url": "http://localhost:17493", "profile_id": "profile",
            "model_revision": "model-sha", "runtime_revision": "runtime-sha",
            "cache_dir": str(cache), "poll_sec": 0.001,
        }})
        self.jobs: list[dict] = []
        self.speaker = "Ryan"
        self.rewrite = False
        self.audio_reads = 0
        self.status = "completed"
        self.recover_new_jobs = False

    def _fetch(self, route: str, payload: dict | None = None) -> bytes:
        if route.startswith("/profiles/"):
            result = {"voice_type": "preset", "preset_engine": "qwen_custom_voice", "preset_voice_id": self.speaker}
        elif route == "/generate":
            self.jobs.append(payload)
            if self.recover_new_jobs:
                self.status = "completed"
            result = {"id": str(len(self.jobs) - 1)}
        elif route.startswith("/history/"):
            job = self.jobs[int(route.rsplit("/", 1)[1])]
            result = {"status": self.status, "text": "rewritten" if self.rewrite else job["text"]}
        elif route.startswith("/audio/"):
            self.audio_reads += 1
            output = io.BytesIO()
            sf.write(output, np.zeros(2400, dtype=np.float32), 24000, format="WAV")
            return output.getvalue()
        else:
            raise AssertionError(route)
        return json.dumps(result).encode()


class NarrationTests(unittest.TestCase):
    def test_aliases_are_literal_longest_first_and_not_recursive(self):
        self.assertEqual(speech_text("API key and API, not APIS.", {"API key": "credential", "API": "A P I", "credential": "oops"}), "credential and A P I, not APIS.")
        with self.assertRaises(ValueError):
            NarrationRequest("Text", seed=0.5)

    def test_kokoro_preserves_canonical_text_and_raw_times(self):
        heard = []
        def pipeline(text, **_):
            heard.append(text)
            yield "respelling", "", np.zeros(2400)
            yield "another spelling", "", np.zeros(2400)
        engine = KokoroEngine({"mastering": {"enabled": True, "pad_start_sec": 0.3}})
        engine._pipeline = pipeline
        request = NarrationRequest("Qwen is here.\nNext paragraph.", {"Qwen": "Chwen"})
        with patch("earworm.tts.kokoro_engine.normalize_for_speech", side_effect=lambda text: text), patch("earworm.tts.kokoro_engine.apply_overrides", side_effect=lambda text: text):
            result = engine.render(request)
            self.assertEqual(heard[0], "Chwen is here.")
            self.assertEqual([s[0] for s in result.segments], ["Qwen is here.", "Next paragraph."])
            self.assertEqual(result.segments[0][1], 0.0)
            self.assertAlmostEqual(result.segments[0][2], 0.32)
            self.assertAlmostEqual(result.segments[1][1], 1.22)
            with patch("earworm.tts.kokoro_engine.encode_mp3", return_value=b"mp3"):
                _, segments = engine.synthesize_with_segments("Original text.")
                self.assertEqual(segments[0][1], 0.3)

    def test_unsupported_controls_fail_before_loading_model(self):
        engine = KokoroEngine({})
        with self.assertRaisesRegex(ValueError, "does not support"):
            engine.render(NarrationRequest("Text.", direction="Curious"))
        self.assertIsNone(engine._pipeline)
        with self.assertRaisesRegex(ValueError, "unsupported Kokoro"):
            KokoroEngine({"kokoro": {"instruct": "Curious"}})
        with self.assertRaisesRegex(ValueError, "unsupported Voicebox"):
            VoiceboxEngine({"voicebox": {"personality": True}})

    def test_mastering_delay_matches_enabled_and_rounded_pad(self):
        self.assertEqual(mastering_lead_seconds(None), 0)
        self.assertEqual(mastering_lead_seconds({"enabled": False, "pad_start_sec": 0.3}), 0)
        self.assertEqual(mastering_lead_seconds({"enabled": True, "pad_start_sec": 0.3004}), 0.3)

    def test_sentence_boundaries_preserve_abbreviations_and_decimals(self):
        text = 'Dr. Smith measured 1.7 volts. "It failed."\nAnother paragraph.\n---\nNext section.'
        self.assertEqual(sentence_chunks(text), [('Dr. Smith measured 1.7 volts.', 'section'), ('"It failed."', 'sentence'), ('Another paragraph.', 'paragraph'), ('Next section.', 'section')])

    def test_voicebox_caches_only_affected_sentence_and_keeps_controls_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = FakeVoicebox(Path(directory))
            first = engine.render(NarrationRequest("AES failed. Mistral worked.", {"AES": "ace"}, "Clear", 42))
            self.assertEqual(first.segments[0][0], "AES failed.")
            self.assertEqual(engine.jobs[0]["text"], "ace failed.")
            self.assertEqual(engine.jobs[0]["instruct"], "Clear")
            self.assertFalse(engine.jobs[0]["personality"])
            self.assertFalse(engine.jobs[0]["normalize"])
            self.assertEqual(engine.jobs[0]["effects_chain"], [])
            self.assertEqual(engine.jobs[0]["crossfade_ms"], 0)
            same = engine.render(NarrationRequest("AES failed. Mistral worked.", {"AES": "ace"}, "Clear", 42))
            self.assertEqual(len(engine.jobs), 2)
            self.assertEqual(first.provenance["chunk_keys"], same.provenance["chunk_keys"])
            corrected = engine.render(NarrationRequest("AES failed. Mistral worked.", {"AES": "A E S"}, "Clear", 42))
            self.assertEqual(len(engine.jobs), 3)
            self.assertEqual(first.provenance["chunk_keys"][1], corrected.provenance["chunk_keys"][1])
            engine.speaker = "Aiden"
            engine.render(NarrationRequest("AES failed. Mistral worked.", {"AES": "A E S"}, "Clear", 42))
            self.assertEqual(len(engine.jobs), 5)

    def test_voicebox_rejects_unexpected_text_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = FakeVoicebox(Path(directory))
            engine.rewrite = True
            with self.assertRaisesRegex(RuntimeError, "changed the approved speech text"):
                engine.render("An approved sentence.")
            self.assertEqual(engine.audio_reads, 0)

    def test_voicebox_resumes_timed_out_job_without_posting_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = FakeVoicebox(Path(directory))
            engine.timeout = 0.001
            engine.status = "generating"
            with self.assertRaises(TimeoutError):
                engine.render("An approved sentence.")
            engine.status = "completed"
            engine.render("An approved sentence.")
            self.assertEqual(len(engine.jobs), 1)

    def test_voicebox_retries_failed_chunk_with_all_controls_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = FakeVoicebox(Path(directory))
            engine.status = "failed"
            with self.assertRaises(RuntimeError):
                engine.render("An approved sentence.")
            engine.recover_new_jobs = True
            engine.render("An approved sentence.")
            self.assertEqual(len(engine.jobs), 2)
            self.assertEqual(engine.jobs[0], engine.jobs[1])


if __name__ == "__main__":
    unittest.main()
