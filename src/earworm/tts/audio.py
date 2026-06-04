"""Shared audio helpers: encode float samples to mp3 via ffmpeg, with an
optional broadcast-style mastering chain (compress -> EQ -> loudnorm -> fades).
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


def _master_filter(duration_sec: float, m: dict) -> str:
    """Build the ffmpeg -af chain from the [mastering] config, in order.

    Chain: compress -> EQ -> loudnorm -> fade-out -> silence pads. The fade-out
    is applied to the content (its start is derived from the content duration),
    then a leading pad and a trailing pad bracket it with silence so the episode
    doesn't slam in or cut off. Leading silence uses `adelay` (ffmpeg's `apad`
    only ever appends to the end), trailing silence uses `apad`.
    """
    parts = [m[k] for k in ("compress", "eq", "loudnorm") if m.get(k)]
    fade_out = float(m.get("fade_out_sec", 0) or 0)
    pad_start = float(m.get("pad_start_sec", 0) or 0)
    pad_end = float(m.get("pad_end_sec", 0) or 0)
    if fade_out > 0 and duration_sec > fade_out:
        parts.append(f"afade=t=out:st={duration_sec - fade_out:.3f}:d={fade_out}")
    if pad_start > 0:
        parts.append(f"adelay={int(round(pad_start * 1000))}:all=1")
    if pad_end > 0:
        parts.append(f"apad=pad_dur={pad_end}")
    return ",".join(parts)


def encode_mp3(
    samples: np.ndarray,
    sample_rate: int,
    bitrate: str = "128k",
    mastering: dict | None = None,
) -> bytes:
    """Encode mono float32 samples to mp3. If `mastering` is enabled, apply the
    compress/EQ/loudnorm/fade chain before encoding (the produced-podcast sound).
    """
    samples = np.asarray(samples, dtype=np.float32)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 1.0:  # guard against clipping before the chain
        samples = samples / peak

    af = ""
    if mastering and mastering.get("enabled"):
        af = _master_filter(len(samples) / sample_rate, mastering)

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        sf.write(str(wav), samples, sample_rate, subtype="PCM_16")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-ac", "1"]
        if af:
            cmd += ["-af", af]
        cmd += ["-codec:a", "libmp3lame", "-b:a", bitrate, "-f", "mp3", "pipe:1"]
        proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.decode()[-1000:]}")
    return proc.stdout


def silence(seconds: float, sample_rate: int) -> np.ndarray:
    return np.zeros(int(seconds * sample_rate), dtype=np.float32)
