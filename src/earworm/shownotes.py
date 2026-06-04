"""Derive show notes from a report: a short summary plus any listed sources.

Handles the research-prompt format (`> thesis` + `## Sources` with links) and
hand-written reports (TL;DR/Summary section, plain-text source/reference lists).
"""
from __future__ import annotations

import re
from pathlib import Path

_HEADING = re.compile(r"^#{1,6}\s")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_SUMMARY_HEADING = re.compile(r"\b(tl;?dr|summary|overview|abstract)\b", re.I)
_SOURCE_HEADING = re.compile(r"\b(sources|references|bibliography|further reading)\b", re.I)
_MAX_SUMMARY = 1200


def _clean(text: str) -> str:
    """Markdown -> plain prose: drop link syntax, emphasis, and bullet markers."""
    text = _LINK.sub(r"\1", text)
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _cap(text: str) -> str:
    if len(text) <= _MAX_SUMMARY:
        return text
    cut = text[:_MAX_SUMMARY]
    end = cut.rfind(". ")
    return (cut[: end + 1] if end > _MAX_SUMMARY * 0.5 else cut.rstrip()) + " …"


def _first_block(lines: list[str], start: int) -> str:
    """First bullet item (complete) or first paragraph after heading index `start`."""
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _HEADING.match(line):
            break
        if not line.strip():
            if body:
                break
            continue
        body.append(line)
    if not body:
        return ""
    if _BULLET.match(body[0]):
        item = [body[0]]
        for line in body[1:]:
            if _BULLET.match(line):
                break
            item.append(line)
        return " ".join(item)
    return " ".join(body)


def _summary(text: str) -> str:
    lines = text.splitlines()

    for line in lines:  # 1. `> thesis` blockquote
        s = line.strip()
        if s.startswith(">"):
            s = re.sub(r"^\**\s*thesis\s*:?\**\s*", "", s.lstrip("> ").strip(), flags=re.I)
            if s:
                return _cap(_clean(s))

    for i, line in enumerate(lines):  # 2. TL;DR / Summary / Overview section
        if _HEADING.match(line) and _SUMMARY_HEADING.search(line):
            block = _first_block(lines, i)
            if block:
                return _cap(_clean(block))

    for para in re.split(r"\n\s*\n", text):  # 3. first prose paragraph
        p = para.strip()
        if p and not p.startswith("#") and not p.startswith(">"):
            return _cap(_clean(p))
    return ""


def _sources(text: str) -> list[str]:
    """Entries under a Sources/References heading — markdown links or plain text."""
    out: list[str] = []
    in_section = False
    for line in text.splitlines():
        if _HEADING.match(line):
            in_section = bool(_SOURCE_HEADING.search(line))
            continue
        if not in_section:
            continue
        m = _BULLET.match(line)
        if not m:
            continue
        item = m.group(1).strip()
        link = _LINK.search(item)
        out.append(f"{link.group(1).strip()} — {link.group(2).strip()}" if link else _clean(item))
    return out


def extract(report_path: Path | None) -> tuple[str, list[str]]:
    """Return (summary, sources). Degrades gracefully across report shapes."""
    if not report_path or not Path(report_path).exists():
        return "", []
    text = Path(report_path).read_text()
    return _summary(text), _sources(text)


def format_notes(summary: str, sources: list[str]) -> str:
    parts: list[str] = []
    if summary:
        parts.append(summary)
    if sources:
        parts.append("Sources:")
        parts.extend(f"- {s}" for s in sources)
    return "\n".join(parts).strip()
