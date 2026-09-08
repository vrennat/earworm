"""Optional Voicebox HTTP synthesis, with Earworm-owned text and chunk cache.

The first supported backend is Qwen 1.7B CustomVoice. Source contract checked
against Voicebox 51f49dea198384b4eb6087b72c17057c6eb1c1cd. No server is started,
models are not installed here, and no cloud personality service is invoked.
"""
from __future__ import annotations

import fcntl
import hashlib
import io
import json
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import numpy as np
import soundfile as sf

from ..config import paths
from ..transcript import shift_segments
from .audio import encode_mp3, mastering_lead_seconds, silence
from .base import NarrationAudio, NarrationRequest, reject_unknown, speech_text
from .chunks import sentence_chunks


def _json_write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


@contextmanager
def _chunk_lock(path: Path, timeout: float):
    deadline = time.monotonic() + timeout
    with path.open("a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Another renderer still owns this narration chunk")
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class VoiceboxEngine:
    def __init__(self, voice_config: dict) -> None:
        settings = voice_config.get("voicebox", {})
        reject_unknown(settings, {
            "url", "profile_id", "model_revision", "runtime_revision", "language",
            "cache_dir", "timeout_sec", "poll_sec", "aliases", "direction", "seed",
        }, "Voicebox")
        for key in ("url", "profile_id", "model_revision", "runtime_revision"):
            if not settings.get(key):
                raise ValueError(f"voicebox.{key} is required")
        self.url = settings["url"].rstrip("/")
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("Voicebox URL must be an HTTP(S) server URL without credentials/query/fragment")
        self.settings = dict(settings)
        self.cache = Path(settings.get("cache_dir", paths().root / "cache" / "narration")).expanduser()
        if not self.cache.is_absolute():
            self.cache = paths().root / self.cache
        self.timeout = float(settings.get("timeout_sec", 600))
        self.poll = float(settings.get("poll_sec", 1))
        if self.timeout <= 0 or self.poll <= 0:
            raise ValueError("Voicebox timeouts must be positive")
        self.audio_config = voice_config.get("audio", {})
        self.mastering = voice_config.get("mastering")
        self.bitrate = self.audio_config.get("bitrate", "128k")

    @property
    def name(self) -> str:
        return "voicebox:qwen_custom_voice:1.7B"

    def _fetch(self, route: str, payload: dict | None = None) -> bytes:
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.url + route, data=data, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=min(self.timeout, 30)) as response:
            return response.read()

    def _json(self, route: str, payload: dict | None = None) -> dict:
        result = json.loads(self._fetch(route, payload))
        if not isinstance(result, dict):
            raise RuntimeError("Voicebox returned an invalid response")
        return result

    def _chunk(self, canonical: str, payload: dict, identity: dict) -> tuple[np.ndarray, int, str]:
        key = hashlib.sha256(json.dumps({"schema": 1, "canonical": canonical, "request": payload, **identity}, sort_keys=True).encode()).hexdigest()
        directory = self.cache / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
        directory.mkdir(parents=True, exist_ok=True)
        wav = directory / f"{key}.wav"
        metadata = directory / f"{key}.json"
        # A shared cache may be read by both watch and a manual render. The lock
        # avoids posting duplicate jobs; a saved job ID also resumes after a crash.
        with _chunk_lock(directory / f"{key}.lock", self.timeout):
            saved = json.loads(metadata.read_text()) if metadata.exists() else {}
            if wav.exists() and saved.get("sha256") == hashlib.sha256(wav.read_bytes()).hexdigest():
                samples, rate = sf.read(wav, dtype="float32")
                return samples, rate, key
            generation = saved.get("generation_id")
            resumed = bool(generation)
            if not generation:
                response = self._json("/generate", payload)
                generation = response["id"]
                _json_write(metadata, {"generation_id": generation})
            deadline = time.monotonic() + self.timeout
            while True:
                state = self._json(f"/history/{quote(generation, safe='')}")
                status = state.get("status")
                if status == "completed":
                    break
                if status == "failed" and resumed:
                    # Voicebox's retry endpoint omits chunk/crossfade settings.
                    # A confirmed failed job can be replaced safely using our
                    # complete payload; an unknown/pending job is only resumed.
                    generation = self._json("/generate", payload)["id"]
                    _json_write(metadata, {"generation_id": generation})
                    resumed = False
                    continue
                if status in {"failed", "cancelled"}:
                    raise RuntimeError(f"Voicebox chunk {key[:12]} {status}: {state.get('error', '')}")
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Voicebox chunk {key[:12]} still pending; rerun resumes job {generation}")
                time.sleep(self.poll)
            if state.get("text") != payload["text"]:
                raise RuntimeError("Voicebox changed the approved speech text")
            raw = self._fetch(f"/audio/{quote(generation, safe='')}")
            samples, rate = sf.read(io.BytesIO(raw), dtype="float32")
            if samples.ndim != 1 or not samples.size or not np.isfinite(samples).all():
                raise RuntimeError("Voicebox must return finite, nonempty mono audio")
            temporary = wav.with_suffix(".wav.tmp")
            temporary.write_bytes(raw)
            temporary.replace(wav)
            _json_write(metadata, {"generation_id": generation, "sha256": hashlib.sha256(raw).hexdigest(), "request": payload, **identity})
            return samples, rate, key

    def render(self, request: NarrationRequest | str) -> NarrationAudio:
        if isinstance(request, str):
            request = NarrationRequest(request)
        aliases = {**self.settings.get("aliases", {}), **request.speech_aliases}
        direction = request.direction if request.direction is not None else self.settings.get("direction")
        seed = request.seed if request.seed is not None else self.settings.get("seed")
        NarrationRequest(request.canonical_text, aliases, direction, seed)
        if direction is not None and len(direction) > 500:
            raise ValueError("Voicebox delivery direction exceeds 500 characters")
        profile_id = self.settings["profile_id"]
        profile = self._json(f"/profiles/{quote(profile_id, safe='')}")
        if profile.get("voice_type") != "preset" or profile.get("preset_engine") != "qwen_custom_voice" or not profile.get("preset_voice_id"):
            raise ValueError("Voicebox adapter requires a Qwen CustomVoice preset profile")
        identity = {
            "engine": self.name, "server": self.url,
            "model_revision": self.settings["model_revision"],
            "runtime_revision": self.settings["runtime_revision"],
            "speaker": profile["preset_voice_id"],
        }
        parts: list[np.ndarray] = []
        segments: list[tuple[str, float, float]] = []
        keys: list[str] = []
        cursor = 0.0
        sample_rate = 0
        for canonical, kind in sentence_chunks(request.canonical_text):
            spoken = speech_text(canonical, aliases)
            if len(spoken) > 5000:
                raise ValueError("Voicebox sentence exceeds 5000 characters; split the canonical sentence before rendering")
            payload = {
                "profile_id": profile_id, "text": spoken,
                "language": self.settings.get("language", "en"),
                "engine": "qwen_custom_voice", "model_size": "1.7B",
                "seed": seed, "instruct": direction, "personality": False,
                "normalize": False, "effects_chain": [],
                "max_chunk_chars": 5000, "crossfade_ms": 0,
            }
            samples, rate, key = self._chunk(canonical, payload, identity)
            if sample_rate and rate != sample_rate:
                raise RuntimeError("Voicebox changed sample rate between chunks")
            sample_rate = rate
            if parts:
                setting, default = {"sentence": ("chunk_gap_ms", 120), "paragraph": ("gap_ms", 900), "section": ("section_gap_ms", 1200)}[kind]
                gap = silence(float(self.audio_config.get(setting, default)) / 1000, rate)
                parts.append(gap)
                cursor += len(gap) / rate
            start = cursor
            parts.append(samples)
            cursor += len(samples) / rate
            segments.append((canonical, start, cursor))
            keys.append(key)
        if not parts:
            raise ValueError("narration contains no speech")
        return NarrationAudio(np.concatenate(parts), sample_rate, segments, self.name, {
            **identity, "chunk_keys": keys, "speech_aliases": aliases,
            "direction": direction, "seed": seed,
        })

    def synthesize_with_segments(self, text: str) -> tuple[bytes, list[tuple[str, float, float]]]:
        result = self.render(text)
        return encode_mp3(result.pcm, result.sample_rate, self.bitrate, mastering=self.mastering), shift_segments(result.segments, mastering_lead_seconds(self.mastering))

    def synthesize(self, text: str) -> bytes:
        return self.synthesize_with_segments(text)[0]
