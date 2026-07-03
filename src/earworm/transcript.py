"""Build a WebVTT transcript from synthesized segments.

Apple Podcasts displays creator transcripts referenced by `<podcast:transcript>`
in the feed. Timestamps come from the actual per-segment audio durations, so the
cues line up with playback.

The segment text carries the *normalized* form fed to the voice, so acronyms the
normalizer dot-separated for a letter-by-letter read ("R.F.C.", "C.E.O's") would
otherwise show up dotted in the human-readable transcript. `_dedot` collapses
them back to plain letters for display only — the audio is unaffected.
"""
from __future__ import annotations

import re

# A dotted acronym as the normalizer emits it: 2+ single caps joined by dots
# ("R.F.C."), its plural ("C.E.O's" — apostrophe-s, last letter undotted), or a
# possessive ("A.I.'s" — last letter dotted, then 's).
_DOTTED = re.compile(r"(?<![A-Za-z0-9])(?:[A-Z]\.){1,}[A-Z]?(?:['’]s)?")


def _dedot(m: re.Match) -> str:
    tok = m.group(0)
    apos = re.search(r"['’]s$", tok)
    head = tok[: apos.start()] if apos else tok      # the part before any 's
    letters = head.replace(".", "")
    if len(letters) < 2:
        return tok                                   # a lone initial ("J." Smith)
    if apos:
        # a dot right before the apostrophe is a possessive ("A.I.'s" -> "AI's");
        # a letter there is the normalizer's plural trick ("C.E.O's" -> "CEOs")
        return letters + ("'s" if head.endswith(".") else "s")
    # Bare acronym: keep a final period only at the very end of the cue, where it
    # unambiguously ends a sentence. Mid-text, an acronym followed by a capital is
    # almost always a compound proper noun ("UK Parliament", "UC Davis", "RAISE
    # Act"), not a sentence break, so the dot just drops.
    if head.endswith(".") and not m.string[m.end():]:
        return letters + "."
    return letters


def dedot_acronyms(text: str) -> str:
    """Collapse dotted-acronym spellings to plain letters for readable display."""
    return _DOTTED.sub(_dedot, text)


def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def build_vtt(segments: list[tuple[str, float, float]]) -> str:
    """segments: list of (text, start_seconds, end_seconds)."""
    lines = ["WEBVTT", ""]
    for text, start, end in segments:
        clean = dedot_acronyms(" ".join(text.split()).strip())
        if not clean:
            continue
        lines.append(f"{_ts(start)} --> {_ts(end)}")
        lines.append(clean)
        lines.append("")
    return "\n".join(lines).strip() + "\n"
