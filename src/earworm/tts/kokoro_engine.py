"""Kokoro TTS engine. Local, default. Loads the model once and stays warm (CPU).

Text is normalized (degrees/coordinates) and lexicon overrides are applied before
synthesis. KPipeline yields per-segment audio; we concatenate with a configurable
silence gap and record per-segment timing so the renderer can emit a timed VTT.
"""
from __future__ import annotations

import re
import warnings

import numpy as np

# A line that is only --- or *** (3+ chars) marks a major topic transition.
_SECTION_BREAK = re.compile(r"\n[ \t]*[-*]{3,}[ \t]*(?:\n|$)")

from ..lexicon import apply_overrides
from ..normalize import normalize_for_speech
from .audio import encode_mp3, silence

REPO_ID = "hexgrad/Kokoro-82M"


class KokoroEngine:
    def __init__(self, voice_config: dict):
        k = voice_config.get("kokoro", {})
        a = voice_config.get("audio", {})
        self.voice = k.get("voice", "af_bella")
        self.speed = float(k.get("speed", 0.97))
        self.lang_code = k.get("lang_code", "a")
        self.blend = k.get("blend")  # optional [[name, weight], ...]
        self.sample_rate = int(a.get("sample_rate", 24000))
        self.bitrate = a.get("bitrate", "128k")
        self.gap_ms = int(a.get("gap_ms", 250))
        self.section_gap_ms = int(a.get("section_gap_ms", self.gap_ms))
        self.mastering = voice_config.get("mastering")
        self._pipeline = None
        self._resolved_voice = None

    @property
    def name(self) -> str:
        if self.blend:
            return "kokoro:blend(" + "+".join(n for n, _ in self.blend) + ")"
        return f"kokoro:{self.voice}"

    def _ensure_pipeline(self):
        if self._pipeline is None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from kokoro import KPipeline

                self._pipeline = KPipeline(lang_code=self.lang_code, repo_id=REPO_ID)
        return self._pipeline

    def _voice(self):
        """Resolve to a voice id (str) or a blended voice tensor."""
        if self._resolved_voice is not None:
            return self._resolved_voice
        pipeline = self._ensure_pipeline()
        if self.blend:
            total = sum(float(w) for _, w in self.blend) or 1.0
            tensor = None
            for name, weight in self.blend:
                v = pipeline.load_single_voice(name) * (float(weight) / total)
                tensor = v if tensor is None else tensor + v
            self._resolved_voice = tensor
        else:
            self._resolved_voice = self.voice
        return self._resolved_voice

    def _render(self, text: str) -> tuple[np.ndarray, list[tuple[str, float, float]]]:
        pipeline = self._ensure_pipeline()
        voice = self._voice()
        prepared = apply_overrides(normalize_for_speech(text))

        # Split on `---`/`***` lines into sections. Paragraphs within a section
        # get the standard gap between them; section boundaries get a longer beat.
        sections = [s for s in _SECTION_BREAK.split(prepared) if s.strip()]
        gap = silence(self.gap_ms / 1000.0, self.sample_rate)
        gap_sec = self.gap_ms / 1000.0
        section_gap = silence(self.section_gap_ms / 1000.0, self.sample_rate)
        section_gap_sec = self.section_gap_ms / 1000.0

        parts: list[np.ndarray] = []
        segments: list[tuple[str, float, float]] = []
        cursor = 0.0
        for section in sections:
            first_in_section = True
            for graphemes, _phonemes, audio in pipeline(section, voice=voice, speed=self.speed):
                if parts:
                    g, g_sec = (section_gap, section_gap_sec) if first_in_section else (gap, gap_sec)
                    parts.append(g)
                    cursor += g_sec
                first_in_section = False
                a = np.asarray(audio, dtype=np.float32)
                start = cursor
                parts.append(a)
                cursor += len(a) / self.sample_rate
                segments.append((graphemes, start, cursor))
        if not parts:
            raise RuntimeError("Kokoro produced no audio (empty script?)")
        return np.concatenate(parts), segments

    def synthesize(self, text: str) -> bytes:
        full, _ = self._render(text)
        return encode_mp3(full, self.sample_rate, self.bitrate, mastering=self.mastering)

    def synthesize_with_segments(self, text: str) -> tuple[bytes, list[tuple[str, float, float]]]:
        """Return (mp3 bytes, per-segment (text, start, end)) for transcript building."""
        full, segments = self._render(text)
        return encode_mp3(full, self.sample_rate, self.bitrate, mastering=self.mastering), segments
