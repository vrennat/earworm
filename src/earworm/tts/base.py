"""TTS engine interface. Swapping engines is a config change, not a code change."""
from __future__ import annotations

from typing import Protocol


class TTSEngine(Protocol):
    """An engine turns spoken-prose text into mp3 bytes."""

    def synthesize(self, text: str) -> bytes:
        """Return mp3-encoded audio for `text`."""
        ...

    @property
    def name(self) -> str:
        ...


def get_engine(voice_config: dict) -> TTSEngine:
    """Construct the engine selected by voice.toml's `engine` field."""
    engine = (voice_config.get("engine") or "kokoro").lower()
    if engine == "kokoro":
        from .kokoro_engine import KokoroEngine

        return KokoroEngine(voice_config)
    raise ValueError(f"unknown TTS engine: {engine!r}")
