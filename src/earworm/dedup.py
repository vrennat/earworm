"""Semantic dedup gate for proposed topics.

The lexical guards — `db.normalize_topic` / `find_duplicate_topic` and autogen's
exact-string filter — only catch re-adds that differ by casing or punctuation.
They miss the failure that actually shipped a duplicate episode: the same idea
proposed in entirely different words. "Civilizations keep losing technologies —
Roman concrete, Damascus steel..." and "Why Hands-On Knowledge Dies Faster Than
Written Knowledge" share almost no words yet are the same episode; no lexical
check flags them.

This module closes that gap with a single cheap LLM pass that compares proposed
topics against what the show has already covered (titles + one-line theses) and
returns the ones that are the same episode in disguise.

The module is pure and backend-agnostic: it renders the prompt and delegates the
model call to a `judge` callable the caller supplies (autogen wires in `claude`,
tests wire in a canned function). The caller owns the fail-open policy.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator


@dataclass(frozen=True)
class Duplicate:
    """A proposed topic the judge flagged as already-covered, with the covered
    item (or short reason) it collides with."""

    candidate: str
    matches: str


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))


def _json_spans(text: str) -> Iterator[str]:
    """The widest `{...}` and `[...]` spans in `text`, for pulling JSON out of a
    response wrapped in prose."""
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if 0 <= start < end:
            yield text[start : end + 1]


def _extract_json(text: str) -> object:
    """Parse the first JSON value from a model response that may be wrapped in
    prose or a ```json fence. Raises ValueError if nothing parses."""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    for candidate in (stripped, *_json_spans(stripped)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON found in judge response")


def render_prompt(prompt_path: Path, candidates: list[str], covered: list[str]) -> str:
    text = prompt_path.read_text()
    return text.replace("{{candidates}}", _numbered(candidates)).replace(
        "{{covered}}", "\n".join(f"- {c}" for c in covered) or "(nothing yet)"
    )


def parse_duplicate_indices(text: str, n: int) -> dict[int, str]:
    """Map a candidate's 1-based number -> the match reason, from the judge's
    JSON. Accepts either a bare array or `{"duplicates": [...]}`; entries whose
    index is out of range or unparseable are dropped."""
    data = _extract_json(text)
    items = data.get("duplicates", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {}
    out: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item["n"])
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= idx <= n:
            out[idx] = str(item.get("matches", "")).strip()
    return out


def filter_new(
    candidates: list[str],
    covered: list[str],
    *,
    judge: Callable[[str], str],
    prompt_path: Path,
) -> tuple[list[str], list[Duplicate]]:
    """Split `candidates` into (kept, dropped) by asking `judge` which duplicate
    `covered`. `judge` takes the rendered prompt and returns the model's text.

    Raises whatever `judge` raises and ValueError on an unparseable response, so
    the caller can decide the fail-open policy. With nothing to compare against
    (no candidates or no prior coverage) it is a no-op that keeps everything.
    """
    if not candidates or not covered:
        return list(candidates), []
    prompt = render_prompt(prompt_path, candidates, covered)
    dup_idx = parse_duplicate_indices(judge(prompt), len(candidates))
    kept: list[str] = []
    dropped: list[Duplicate] = []
    for i, cand in enumerate(candidates, 1):
        (dropped.append(Duplicate(cand, dup_idx[i])) if i in dup_idx else kept.append(cand))
    return kept, dropped
