"""Reference identity, transport integrity, and canonical caption regressions."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from earworm.tts.base import NarrationRequest
from earworm.tts.qwen_engine import QwenEngine, paragraph_chunks


class QwenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reference = self.root / "reference.wav"
        self.reference.write_bytes(b"approved")
        self.config = {"qwen": {"model_path": "/model/revision", "model_revision": "revision",
            "reference_audio": str(self.reference), "reference_sha256": hashlib.sha256(b"approved").hexdigest(),
            "reference_text": "Reference.", "cache_dir": str(self.root)}}

    def response(self, command, **kwargs):
        payload = json.loads(kwargs["input"])
        self.spoken = payload["texts"]
        entries = []
        for i, _ in enumerate(self.spoken):
            path = self.root / f"{i}.wav"
            sf.write(path, np.zeros(24000), 24000)
            entries.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        return SimpleNamespace(returncode=0, stdout=json.dumps({"texts": self.spoken, "chunks": entries,
                                                               "provenance": {"seed": payload["seed"]}}))

    def test_aliases_leave_captions_canonical_and_gaps_are_timed_once(self):
        with patch("earworm.tts.qwen_engine.subprocess.run", self.response):
            result = QwenEngine(self.config).render(NarrationRequest("SQLite works. It saves files.\nAnother thought.", {"SQLite": "S Q Lite"}))
        self.assertIn("S Q Lite", self.spoken[0])
        self.assertEqual(result.segments, [("SQLite works. It saves files.", 0, 1), ("Another thought.", 1.35, 2.35)])

    def test_reference_change_fails_before_inference(self):
        self.reference.write_bytes(b"different")
        with patch("earworm.tts.qwen_engine.subprocess.run") as process, self.assertRaisesRegex(ValueError, "reference audio changed"):
            QwenEngine(self.config).render("Hello.")
        process.assert_not_called()

    def test_unsupported_delivery_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "directions are unsupported"):
            QwenEngine(self.config).render(NarrationRequest("Hello.", direction="Whisper"))

    def test_changed_response_text_is_rejected(self):
        with patch("earworm.tts.qwen_engine.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout='{"texts": [], "chunks": []}')):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                QwenEngine(self.config).render("Hello.")

    def test_paragraph_packing_retains_sections_and_rejects_overlong_sentence(self):
        self.assertEqual(paragraph_chunks("Dr. Hipp spoke. Then left.\n---\nA new part."),
                         [("Dr. Hipp spoke. Then left.", "section"), ("A new part.", "section")])
        with self.assertRaises(ValueError):
            paragraph_chunks("x" * 1201)


if __name__ == "__main__":
    unittest.main()
