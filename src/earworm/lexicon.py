"""Pronunciation lexicon: rewrite known words to misaki inline IPA overrides.

`[word](/ipa/)` survives Kokoro end-to-end into the audio (verified). We apply
whole-word, case-sensitive, longest-first replacements before synthesis, skipping
anything already inside an override so re-application is safe.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .config import paths, _load_toml


@lru_cache(maxsize=1)
def _entries() -> list[tuple[str, str]]:
    words = _load_toml(paths().config / "lexicon.toml").get("words", {})
    # longest first so multi-word / longer terms win before their substrings
    return sorted(words.items(), key=lambda kv: len(kv[0]), reverse=True)


@lru_cache(maxsize=1)
def known_words() -> frozenset[str]:
    """Lowercased lexicon keys — used by the normalizer to let a curated
    pronunciation win over a free-form script phonetic hint for the same name."""
    return frozenset(w.lower() for w, _ in _entries())


def apply_overrides(text: str) -> str:
    for word, ipa in _entries():
        # Whole word, case-insensitive (so "Mana"/"mana" both match); the
        # lookbehind/ahead avoid re-wrapping an existing [word](/.../) override.
        # Preserve the matched casing in the displayed text via group(0).
        pattern = re.compile(rf"(?<!\[)\b{re.escape(word)}\b(?!\]\()", re.IGNORECASE)
        text = pattern.sub(lambda m: f"[{m.group(0)}](/{ipa}/)", text)
    return text
