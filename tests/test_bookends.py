"""Episode bookends: spoken title, cues, and caption timing. No models or ffmpeg."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from earworm import render
from earworm.tts import bookends
from earworm.tts.base import NarrationAudio
from earworm.tts.qwen_worker import paragraph_seed

RATE = 24000


class FakeEngine:
    name = "fake"

    def __init__(self):
        self.requests = []

    def render(self, request):
        self.requests.append(request)
        pcm = (0.2 * np.ones(RATE)).astype(np.float32)
        return NarrationAudio(pcm, RATE, [("line", 0.0, 1.0)], self.name)


class BookendTests(unittest.TestCase):
    def test_cues_are_deterministic_bounded_and_named(self):
        for name in bookends.CUES:
            first, second = bookends.cue(name, RATE), bookends.cue(name, RATE)
            self.assertTrue(np.array_equal(first, second))
            self.assertLessEqual(float(np.max(np.abs(first))), 1.0)
            self.assertAlmostEqual(len(first) / RATE, bookends.CUES[name][1], places=3)

    def test_wrap_places_cues_around_narration_and_reports_lead(self):
        pcm = (0.2 * np.ones(RATE)).astype(np.float32)
        settings = {"intro_cue": "rising", "outro_cue": "falling", "intro_gap_sec": 0.5, "outro_gap_sec": 1.0}
        wrapped, lead = bookends.wrap(pcm, RATE, settings)
        self.assertAlmostEqual(lead, 1.85 + 0.5, places=3)
        self.assertEqual(len(wrapped), int(lead * RATE) + RATE + RATE + int(1.65 * RATE))
        self.assertTrue(np.array_equal(wrapped[int(lead * RATE):int(lead * RATE) + RATE], pcm))

    def test_wrap_rejects_unknown_settings(self):
        with self.assertRaises(ValueError):
            bookends.wrap(np.zeros(10, dtype=np.float32), RATE, {"intro_music": "rising"})

    def test_title_line_is_its_own_sentence(self):
        self.assertEqual(bookends.title_line("Earworm", "How the Box Got Its Size"),
                         "Earworm. How the Box Got Its Size.")
        self.assertEqual(bookends.title_line("Earworm.", "Why?"), "Earworm. Why?")

    def test_synthesize_announces_title_and_shifts_captions_by_cue_and_pad(self):
        engine = FakeEngine()
        config = {"bookends": {"announce_title": True, "intro_cue": "rising", "intro_gap_sec": 0.5},
                  "mastering": {"enabled": True, "pad_start_sec": 0.3}}
        with patch.object(render, "show_config", return_value={"title": "Earworm"}), \
                patch("earworm.tts.audio.encode_mp3", return_value=b"mp3"):
            _, segments, provenance = render._synthesize("Body text.", engine, config, "A Title")
        self.assertEqual(engine.requests[0].canonical_text, "Earworm. A Title.\n\n---\n\nBody text.")
        self.assertAlmostEqual(segments[0][1], 0.3 + 1.85 + 0.5, places=3)
        self.assertAlmostEqual(provenance["caption_offset_seconds"], 0.3 + 1.85 + 0.5, places=3)

    def test_synthesize_without_bookends_is_unchanged(self):
        engine = FakeEngine()
        with patch("earworm.tts.audio.encode_mp3", return_value=b"mp3"):
            _, segments, _ = render._synthesize("Body text.", engine, {}, "A Title")
        self.assertEqual(engine.requests[0].canonical_text, "Body text.")
        self.assertEqual(segments[0][1], 0.0)


class ParagraphSeedTests(unittest.TestCase):
    def test_fixed_seed_by_default(self):
        self.assertEqual(paragraph_seed({"seed": 42}, "a"), 42)
        self.assertEqual(paragraph_seed({"seed": 42}, "b"), 42)

    def test_per_paragraph_seed_varies_by_text_and_is_stable(self):
        request = {"seed": 42, "seed_per_paragraph": True}
        self.assertEqual(paragraph_seed(request, "a"), paragraph_seed(request, "a"))
        self.assertNotEqual(paragraph_seed(request, "a"), paragraph_seed(request, "b"))
        self.assertLess(paragraph_seed(request, "a"), 2**32)


if __name__ == "__main__":
    unittest.main()
