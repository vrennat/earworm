"""TTS engine interface. Swapping engines is a config change, not a code change."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping, Protocol

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class NarrationRequest:
    """Approved text plus controls for the selected engine, never spoken directions.

    Aliases are engine-specific speech spellings. They never alter the text used
    for transcripts or episode identity. An omitted seed permits engine defaults.
    """

    canonical_text: str
    speech_aliases: Mapping[str, str] = field(default_factory=dict)
    direction: str | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        if not self.canonical_text.strip():
            raise ValueError("narration text is empty")
        if self.seed is not None and (type(self.seed) is not int or self.seed < 0):
            raise ValueError("narration seed must be a nonnegative integer")
        if self.direction is not None and not isinstance(self.direction, str):
            raise ValueError("narration direction must be a string")
        for written, spoken in self.speech_aliases.items():
            if not isinstance(written, str) or not written.strip() or not isinstance(spoken, str) or not spoken.strip():
                raise ValueError("speech aliases require nonempty written and spoken strings")


@dataclass
class NarrationAudio:
    """Unmastered mono PCM and canonical cues relative to that PCM's start.

    The caller adds any intro and mastering lead pad to the cues exactly once.
    No encoder padding, personality rewriting, or music is included here.
    """

    pcm: np.ndarray
    sample_rate: int
    segments: list[tuple[str, float, float]]
    engine: str
    provenance: dict = field(default_factory=dict)


def speech_text(text: str, aliases: Mapping[str, str]) -> str:
    """Apply literal, longest-first aliases once, without changing display text."""
    if not aliases:
        return text
    keys = sorted(aliases, key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in keys) + r")(?!\w)")
    return pattern.sub(lambda match: aliases[match.group(0)], text)


def reject_unknown(settings: dict, allowed: set[str], label: str) -> None:
    unknown = set(settings) - allowed
    if unknown:
        raise ValueError(f"unsupported {label} controls: {', '.join(sorted(unknown))}")


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
    if engine == "voicebox":
        from .voicebox_engine import VoiceboxEngine

        return VoiceboxEngine(voice_config)
    if engine == "qwen":
        from .qwen_engine import QwenEngine

        return QwenEngine(voice_config)
    raise ValueError(f"unknown TTS engine: {engine!r}")
