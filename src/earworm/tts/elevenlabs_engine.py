"""ElevenLabs engine — opt-in per-config upgrade (Phase 4).

Stubbed for Phase 1: the seam exists so swapping `engine = "elevenlabs"` in
voice.toml routes here, but the API call is not wired until Phase 4.
"""
from __future__ import annotations

import os


class ElevenLabsEngine:
    def __init__(self, voice_config: dict):
        e = voice_config.get("elevenlabs", {})
        self.voice_id = e.get("voice_id", "")
        self.model = e.get("model", "eleven_turbo_v2_5")
        self.bitrate = voice_config.get("audio", {}).get("bitrate", "128k")
        self.api_key = os.environ.get("EARWORM_ELEVENLABS_API_KEY", "")

    @property
    def name(self) -> str:
        return f"elevenlabs:{self.voice_id or '?'}"

    def synthesize(self, text: str) -> bytes:
        raise NotImplementedError(
            "ElevenLabs engine is a Phase 4 upgrade. Set engine = \"kokoro\" in "
            "config/voice.toml for now."
        )
