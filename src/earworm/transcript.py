"""Build a WebVTT transcript from synthesized segments.

Apple Podcasts displays creator transcripts referenced by `<podcast:transcript>`
in the feed. Timestamps come from the actual per-segment audio durations, so the
cues line up with playback.
"""
from __future__ import annotations


def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def build_vtt(segments: list[tuple[str, float, float]]) -> str:
    """segments: list of (text, start_seconds, end_seconds)."""
    lines = ["WEBVTT", ""]
    for text, start, end in segments:
        clean = " ".join(text.split()).strip()
        if not clean:
            continue
        lines.append(f"{_ts(start)} --> {_ts(end)}")
        lines.append(clean)
        lines.append("")
    return "\n".join(lines).strip() + "\n"
