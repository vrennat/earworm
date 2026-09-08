"""Local semantic screening: find candidate matches, then compare exact pairs.

An explicit decision for every proposal prevents silent omissions. Confirmation
separates same-story matches from merely related mechanisms in a long archive.
The caller supplies the bounded judge; invalid output stops the whole batch.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Duplicate:
    candidate: str
    matches: str


def _numbered(items: list[str]) -> str:
    return "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            # json.loads otherwise discards an earlier decision without warning.
            raise ValueError(f"repeated JSON key: {key}")
        result[key] = value
    return result


def _extract_json(text: str) -> object:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1)
    return json.loads(stripped, object_pairs_hook=_unique_keys)


def render_prompt(prompt_path: Path, candidates: list[str], covered: list[str]) -> str:
    return prompt_path.read_text().replace("{{candidates}}", _numbered(candidates)).replace(
        "{{covered}}", _numbered(covered) or "(nothing yet)"
    )


def _decisions(text: str, expected: set[int], field: str) -> dict[int, dict]:
    data = _extract_json(text)
    if not isinstance(data, dict) or set(data) != {"decisions"}:
        raise ValueError("expected decisions object")
    items = data["decisions"]
    if not isinstance(items, list):
        raise ValueError("expected decisions array")
    result = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {"n", field, "reason"}:
            raise ValueError("invalid decision fields")
        n = item["n"]
        if type(n) is not int or n not in expected or n in result:
            raise ValueError("invalid or repeated proposal number")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise ValueError("missing comparison reason")
        result[n] = item
    if set(result) != expected:
        raise ValueError("missing proposal decisions")
    return result


def parse_duplicate_indices(text: str, n: int, covered: list[str]) -> dict[int, list[str]]:
    """Resolve up to three possible matches per proposal to actual coverage."""
    result = {}
    for idx, item in _decisions(text, set(range(1, n + 1)), "matches").items():
        matches = item["matches"]
        if not isinstance(matches, list) or len(matches) > 3:
            raise ValueError("expected at most three coverage numbers")
        if any(type(m) is not int or not 1 <= m <= len(covered) for m in matches):
            raise ValueError("invalid coverage number")
        if len(set(matches)) != len(matches):
            raise ValueError("repeated coverage number")
        if matches:
            result[idx] = [covered[m - 1] for m in matches]
    return result


def filter_new(
    candidates: list[str], covered: list[str], *, judge: Callable[[str], str],
    prompt_path: Path,
) -> tuple[list[str], list[Duplicate]]:
    """Return kept/dropped topics; both calls must succeed before anything queues.

    An empty archive is a no-op. Confirmation runs only when retrieval suggests
    matches, and keeps ambiguous/adjacent pairs. Model or schema errors propagate.
    """
    if not candidates or not covered:
        return list(candidates), []
    matches = parse_duplicate_indices(
        judge(render_prompt(prompt_path, candidates, covered)), len(candidates), covered
    )
    if not matches:
        return list(candidates), []
    # Keep the pair-to-proposal mapping outside model output. A weak first match
    # must not hide a real duplicate appearing later in the shortlist.
    references = [(n, match) for n, options in sorted(matches.items()) for match in options]
    pairs = [{"n": i, "proposal": candidates[n - 1], "covered": match}
             for i, (n, match) in enumerate(references, 1)]
    prompt = prompt_path.with_name("dedup_confirm.md").read_text().replace(
        "{{pairs}}", json.dumps(pairs, ensure_ascii=False)
    )
    decisions = _decisions(judge(prompt), set(range(1, len(pairs) + 1)), "duplicate")
    confirmed = {}
    for pair_id, item in sorted(decisions.items()):
        if type(item["duplicate"]) is not bool:
            raise ValueError("duplicate must be a boolean")
        if item["duplicate"]:
            n, match = references[pair_id - 1]
            confirmed.setdefault(n, Duplicate(candidates[n - 1], f"{match} — {item['reason'].strip()}"))
    return ([c for i, c in enumerate(candidates, 1) if i not in confirmed],
            [confirmed[i] for i in sorted(confirmed)])
