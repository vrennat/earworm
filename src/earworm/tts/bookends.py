"""Episode bookends: a short original cue before the spoken title and after the
final line, so an episode audibly starts and ends instead of slamming in or out.

The cues are synthesized sine plucks (no samples or borrowed melody), first
auditioned in docs/experiments/2026-09-05-audio-identity. They are generated at
the narration sample rate, so no audio asset needs deploying.
"""
from __future__ import annotations

import math

import numpy as np

from .base import reject_unknown

# (onset seconds, frequency Hz, gain), total duration seconds.
CUES: dict[str, tuple[list[tuple[float, float, float]], float]] = {
    "rising": ([(0.08, 293.665, 1.0), (0.29, 440.0, 0.8), (0.52, 659.255, 0.65)], 1.85),
    "chord": ([(0.08, 220.0, 0.7), (0.08, 329.628, 0.5), (0.18, 493.883, 0.4)], 1.60),
    "falling": ([(0.08, 523.251, 0.75), (0.38, 391.995, 0.9)], 1.65),
}

SETTINGS = {"announce_title", "intro_cue", "outro_cue", "cue_level_db", "intro_gap_sec", "outro_gap_sec"}


def cue(name: str, rate: int) -> np.ndarray:
    notes, duration = CUES[name]
    total = int(duration * rate)
    signal = np.zeros(total, dtype=np.float64)
    for onset, frequency, gain in notes:
        length = int(min(1.25, duration - onset) * rate)
        t = np.arange(length) / rate
        tone = np.sin(2 * math.pi * frequency * t)
        tone += 0.18 * np.sin(2 * math.pi * 2 * frequency * t) * np.exp(-5 * t)
        tone += 0.06 * np.sin(2 * math.pi * 3 * frequency * t) * np.exp(-8 * t)
        envelope = (1 - np.exp(-t / 0.009)) * np.exp(-t / 0.31)
        envelope *= np.minimum(1, (length / rate - t) / 0.16)
        start = int(onset * rate)
        signal[start:start + length] += gain * tone * envelope
    delay = int(0.075 * rate)
    signal[delay:] += 0.09 * signal[:-delay].copy()
    return (signal / max(float(np.max(np.abs(signal))), 1e-9)).astype(np.float32)


def _rms(samples: np.ndarray) -> float:
    voiced = samples[np.abs(samples) > 1e-3]
    return float(np.sqrt(np.mean(np.square(voiced)))) if voiced.size else 0.0


def title_line(show: str, title: str) -> str:
    """Spoken announcement, punctuated so it chunks as its own section."""
    line = f"{show.strip().rstrip('.')}. {title.strip()}"
    return line if line[-1] in ".!?" else line + "."


def wrap(pcm: np.ndarray, rate: int, settings: dict) -> tuple[np.ndarray, float]:
    """Return (cue + narration + cue, seconds added before the narration)."""
    reject_unknown(settings, SETTINGS, "bookends")
    gain = _rms(pcm) * 10 ** (float(settings.get("cue_level_db", -10)) / 20)
    before, after = [], []
    if settings.get("intro_cue"):
        sound = cue(settings["intro_cue"], rate)
        before = [sound * gain / max(_rms(sound), 1e-9),
                  np.zeros(int(float(settings.get("intro_gap_sec", 0.4)) * rate), dtype=np.float32)]
    if settings.get("outro_cue"):
        sound = cue(settings["outro_cue"], rate)
        after = [np.zeros(int(float(settings.get("outro_gap_sec", 1.2)) * rate), dtype=np.float32),
                 sound * gain / max(_rms(sound), 1e-9)]
    lead = sum(len(part) for part in before) / rate
    return np.concatenate([*before, pcm, *after]).astype(np.float32), lead
