"""Local Qwen reference narration in a disposable GPU process."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from ..config import paths
from ..normalize import normalize_for_speech
from .audio import encode_mp3, silence
from .base import NarrationAudio, NarrationRequest, reject_unknown, speech_text
from .chunks import sentence_chunks


def paragraph_chunks(text: str, limit: int = 1200) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    for sentence, kind in sentence_chunks(text):
        if len(sentence) > limit:
            raise ValueError("Qwen sentence is too long; split it before narration")
        if chunks and kind == "sentence" and len(chunks[-1][0]) + len(sentence) + 1 <= limit:
            previous, gap = chunks[-1]
            chunks[-1] = (previous + " " + sentence, gap)
        else:
            chunks.append((sentence, kind))
    return chunks


class QwenEngine:
    def __init__(self, voice_config: dict) -> None:
        settings = voice_config.get("qwen", {})
        reject_unknown(settings, {"python", "model_path", "model_revision", "reference_audio",
                                 "reference_text", "reference_sha256", "cache_dir", "seed",
                                 "timeout_sec", "gpu_wait_sec"}, "Qwen")
        for key in ("model_path", "model_revision", "reference_audio", "reference_text", "reference_sha256"):
            if not settings.get(key):
                raise ValueError(f"qwen.{key} is required")
        self.settings = dict(settings)
        self.config = voice_config
        self.worker = Path(__file__).with_name("qwen_worker.py")

    @property
    def name(self) -> str:
        return "qwen:base:1.7B:earworm-modern"

    def render(self, request: NarrationRequest | str) -> NarrationAudio:
        if isinstance(request, str):
            request = NarrationRequest(request)
        if request.direction is not None:
            raise ValueError("Qwen Base uses the approved reference delivery; directions are unsupported")
        reference = Path(self.settings["reference_audio"]).expanduser().resolve()
        if hashlib.sha256(reference.read_bytes()).hexdigest() != self.settings["reference_sha256"]:
            raise ValueError("Qwen reference audio changed; refusing an unapproved voice")
        canonical = paragraph_chunks(request.canonical_text)
        spoken = [normalize_for_speech(speech_text(text, request.speech_aliases)) for text, _ in canonical]
        seed = request.seed if request.seed is not None else self.settings.get("seed", 42)
        NarrationRequest(request.canonical_text, request.speech_aliases, seed=seed)
        cache = Path(self.settings.get("cache_dir", paths().root / "cache" / "qwen")).expanduser().resolve()
        payload = {**self.settings, "reference_audio": str(reference), "cache_dir": str(cache),
                   "texts": spoken, "seed": seed, "worker_sha256": hashlib.sha256(self.worker.read_bytes()).hexdigest()}
        process = subprocess.run(
            [str(Path(self.settings.get("python", sys.executable)).expanduser()), str(self.worker)],
            input=json.dumps(payload), capture_output=True, text=True,
            timeout=float(self.settings.get("timeout_sec", 2400)),
        )
        if process.returncode:
            raise RuntimeError(f"Qwen narration failed ({process.returncode}): {process.stderr[-2000:]}")
        response = json.loads(process.stdout)
        if response.get("texts") != spoken or len(response.get("chunks", [])) != len(canonical):
            raise RuntimeError("Qwen response does not match the requested narration")
        parts, segments = [], []
        cursor = 0.0
        audio = self.config.get("audio", {})
        for (text, kind), entry in zip(canonical, response["chunks"]):
            wav = Path(entry["path"]).resolve()
            if not wav.is_relative_to(cache) or hashlib.sha256(wav.read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError("Qwen cache audio failed its integrity check")
            samples, rate = sf.read(wav, dtype="float32")
            if rate != 24000 or samples.ndim != 1 or not samples.size or not np.isfinite(samples).all():
                raise RuntimeError("Qwen returned invalid audio")
            if parts:
                key, default = {"sentence": ("chunk_gap_ms", 120), "paragraph": ("gap_ms", 350),
                                "section": ("section_gap_ms", 700)}[kind]
                gap = silence(float(audio.get(key, default)) / 1000, rate)
                parts.append(gap)
                cursor += len(gap) / rate
            start = cursor
            parts.append(samples)
            cursor += len(samples) / rate
            segments.append((text, start, cursor))
        return NarrationAudio(np.concatenate(parts), 24000, segments, self.name, response["provenance"])

    def synthesize(self, text: str) -> bytes:
        result = self.render(text)
        return encode_mp3(result.pcm, result.sample_rate,
                          self.config.get("audio", {}).get("bitrate", "128k"), self.config.get("mastering"))
