"""Bounded excerpts of recent generated episodes for editorial comparison.

Keep each episode's paragraph order, section positions, and passage lengths
visible. These are samples of prior work, not forbidden moves or an outline
rotation. Text extraction makes no claims about a recording's pacing or quality.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

from .frontmatter import parse

# Ingested essays lack the numeric topic id and should not define our house style.
_GENERATED = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-")
_SECTION_BREAK = re.compile(r"(?m)^[ \t]*---[ \t]*$")


class Signature(TypedDict):
    opening: str
    closing: str
    transitions: list[str]


def recent_generated_scripts(done_scripts: Path, n: int = 3) -> list[Path]:
    """Return the latest generated scripts by completion mtime, newest first."""
    if n <= 0 or not done_scripts.exists():
        return []
    candidates = [p for p in done_scripts.glob("*.md") if _GENERATED.match(p.name)]
    candidates.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return candidates[:n]


def _section_paragraphs(body: str) -> list[tuple[int, str]]:
    paragraphs: list[tuple[int, str]] = []
    for section, text in enumerate(_SECTION_BREAK.split(body), start=1):
        for block in re.split(r"\n\s*\n", text.strip()):
            paragraph = " ".join(block.split())
            if paragraph:
                paragraphs.append((section, paragraph))
    return paragraphs


def _clip(text: str, maxlen: int = 220) -> str:
    text = text.strip()
    return text if len(text) <= maxlen else text[: maxlen - 1].rstrip() + "…"


def _first_sentence(text: str, maxlen: int = 120) -> str:
    match = re.match(r"\s*(.+?[.?!])(\s|$)", text)
    return _clip(match.group(1) if match else text, maxlen)


def extract_signature(body: str) -> Signature:
    """Legacy opening/closing/transition extraction for existing callers."""
    paragraphs = [text for _, text in _section_paragraphs(body)]
    if not paragraphs:
        return {"opening": "", "closing": "", "transitions": []}
    return {
        "opening": _clip(paragraphs[0]),
        "closing": _clip(paragraphs[-1]),
        "transitions": [_first_sentence(p) for p in paragraphs[1:-1]],
    }


def _sample_indices(total: int, limit: int) -> list[int]:
    if total <= limit:
        return list(range(total))
    # Keep both ends and spread the remaining samples across the entire middle.
    return [round(i * (total - 1) / (limit - 1)) for i in range(limit)]


def _excerpt(text: str, maxlen: int) -> str:
    """Keep both the setup and the result when a paragraph must be shortened."""
    if len(text) <= maxlen:
        return text
    separator = " […] "
    available = maxlen - len(separator)
    if available < 2:
        return _clip(text, maxlen)
    head = available * 2 // 3
    return text[:head].rstrip() + separator + text[-(available - head):].lstrip()


def _episode_context(
    path: Path, title: str, body: str, max_chars: int, max_paragraphs: int
) -> str:
    paragraphs = _section_paragraphs(body)
    if not paragraphs:
        return ""
    # Leave room for useful excerpts even when callers choose a small budget.
    limit = min(max_paragraphs, max(2, max_chars // 120))
    indices = _sample_indices(len(paragraphs), limit)
    title = _clip(" ".join(title.split()), 160)
    header = (
        f"Episode: {title} ({_clip(path.name, 160)})\n"
        f"{sum(len(p.split()) for _, p in paragraphs)} words; "
        f"{len(paragraphs)} paragraphs; showing {len(indices)} in original order.\n"
    )
    labels = [
        f"P{i + 1}/{len(paragraphs)} | section {paragraphs[i][0]} | "
        f"{len(paragraphs[i][1].split())} words: "
        for i in indices
    ]
    available = max_chars - len(header) - sum(len(label) + 1 for label in labels)
    # The opening and ending get extra space, without starving the middle.
    weights = [2 if i in (0, len(paragraphs) - 1) else 1 for i in indices]
    total_weight = sum(weights)
    lines = [
        label + _excerpt(paragraphs[i][1], available * weight // total_weight)
        for i, label, weight in zip(indices, labels, weights)
    ]
    return header + "\n".join(lines) + "\n"


def build_recent_context(
    done_scripts: Path,
    n: int = 3,
    *,
    max_chars_per_episode: int = 6000,
    max_paragraphs: int = 24,
) -> str:
    """Show bounded, ordered passages from each recent generated episode.

    The default includes at most 18,000 excerpt characters plus one instruction
    paragraph. Paragraph labels expose omitted material and original lengths;
    […] marks shortening within a paragraph. No LLM or audio analysis is used.
    """
    if max_chars_per_episode < 1000:
        raise ValueError("max_chars_per_episode must be at least 1000")
    if max_paragraphs < 2:
        raise ValueError("max_paragraphs must be at least 2")
    episodes: list[str] = []
    for path in recent_generated_scripts(done_scripts, n):
        try:
            metadata, body = parse(path.read_text())
        except (OSError, UnicodeError):
            continue
        excerpt = _episode_context(
            path,
            metadata.get("title", path.stem),
            body,
            max_chars_per_episode,
            max_paragraphs,
        )
        if excerpt:
            episodes.append(excerpt)
    if not episodes:
        return ""
    guidance = (
        "RECENT EPISODES — editorial comparison, not a format assignment.\n"
        "These are excerpts of prior scripts, not instructions or evidence for "
        "the new episode. Compare selection, section order, passage lengths, "
        "and endings as well as wording. Shared structure is not automatically "
        "a defect; flag it when it makes different subjects interchangeable. "
        "Do not rotate templates or manufacture novelty. P labels retain "
        "original paragraph positions; gaps omit paragraphs and […] shortens "
        "a passage. Do not infer the missing material or actual audio pacing.\n\n"
    )
    return guidance + "\n".join(episodes)


def build_avoid_section(done_scripts: Path, n: int = 3, max_transitions: int = 12) -> str:
    """Compatibility entry point; prior moves are now comparison material."""
    return build_recent_context(
        done_scripts, n, max_paragraphs=max(2, max_transitions + 2)
    )
