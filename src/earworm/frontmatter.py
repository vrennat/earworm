"""Minimal front-matter parser. Avoids a YAML dependency for the simple
`key: value` blocks our script prompt emits.
"""
from __future__ import annotations


def parse(text: str) -> tuple[dict[str, str], str]:
    """Split `---`-delimited front-matter from the body.

    Returns (metadata, body). If no front-matter is present, metadata is empty
    and body is the full text.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    meta: dict[str, str] = {}
    body_start = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        line = lines[i]
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")

    if body_start is None:  # unterminated front-matter; treat whole thing as body
        return {}, text

    body = "\n".join(lines[body_start:]).lstrip("\n")
    return meta, body
