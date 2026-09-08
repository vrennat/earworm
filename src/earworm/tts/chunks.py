"""Deterministic sentence boundaries independent of neighboring paragraph length."""
from __future__ import annotations

import re

_SECTION = re.compile(r"\n[ \t]*[-*]{3,}[ \t]*(?:\n|$)")
_END = re.compile(r"[.!?][\"'’”)]*(?=\s+|$)")
_ABBREVIATION = re.compile(r"(?:\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc)|\b[A-Z]|(?:\b[A-Za-z]\.)+[A-Za-z])\.$", re.I)


def sentence_chunks(text: str) -> list[tuple[str, str]]:
    """Return (canonical text, preceding gap kind), preserving decimals/initials.

    Unpunctuated long sentences remain intact: changing one sentence must not
    repack every later sentence or silently truncate a model input.
    """
    chunks: list[tuple[str, str]] = []
    for section in _SECTION.split(text):
        first_paragraph = True
        for paragraph in filter(None, (p.strip() for p in section.splitlines())):
            start = 0
            sentences: list[str] = []
            for match in _END.finditer(paragraph):
                candidate = paragraph[start:match.end()].strip()
                if match.group()[0] == "." and _ABBREVIATION.search(candidate):
                    continue
                sentences.append(candidate)
                start = match.end()
            if paragraph[start:].strip():
                sentences.append(paragraph[start:].strip())
            for index, sentence in enumerate(sentences):
                kind = "sentence" if index else ("section" if first_paragraph else "paragraph")
                chunks.append((sentence, kind))
            first_paragraph = False
    return chunks
