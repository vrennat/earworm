"""Cross-episode memory for the script pass.

The script prompt drifts into the same openings, closings, and structural
transitions episode after episode ("So put it together.", "Thanks for
listening."). This module reads the last few finished scripts from
`done/scripts/`, pulls out exactly those recurring moves, and formats an
"AVOID THESE" block the script stage injects into its prompt so the writer can
steer clear of self-repetition.

Deterministic, no LLM: pure text extraction. Empty string when there's no
history yet (a fresh workspace), so the prompt placeholder collapses cleanly.
"""
from __future__ import annotations

import re
from pathlib import Path

from .frontmatter import parse

# Auto-generated episode scripts are named `YYYY-MM-DD-NNNN-slug.md`. The 4-digit
# topic id distinguishes them from ingested essays (`YYYY-MM-DD-slug.md`), whose
# voice we don't want to treat as "our" recurring style.
_GENERATED = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-")

# Section-break sentinel the script body uses between major topic shifts.
_BREAK = "---"


def recent_generated_scripts(done_scripts: Path, n: int = 3) -> list[Path]:
    """The `n` most recently finished generated episode scripts, newest first.

    Sorted by mtime (when the renderer moved them into `done/`), so it tracks the
    genuinely latest episodes regardless of date-prefix ordering quirks.
    """
    if not done_scripts.exists():
        return []
    candidates = [p for p in done_scripts.glob("*.md") if _GENERATED.match(p.name)]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[:n]


def _paragraphs(body: str) -> list[str]:
    """Body split into real paragraphs, dropping the `---` break sentinels."""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", body.strip()):
        para = " ".join(line.strip() for line in block.splitlines()).strip()
        if para and para != _BREAK:
            out.append(para)
    return out


def _first_sentence(text: str, maxlen: int = 120) -> str:
    """The first sentence of a paragraph — where the structural transition lives
    ("So put it together.", "Which brings us to..."). Capped for prompt economy."""
    m = re.match(r"\s*(.+?[.?!])(\s|$)", text)
    sentence = m.group(1).strip() if m else text.strip()
    return sentence if len(sentence) <= maxlen else sentence[: maxlen - 1].rstrip() + "…"


def _clip(text: str, maxlen: int = 220) -> str:
    text = text.strip()
    return text if len(text) <= maxlen else text[: maxlen - 1].rstrip() + "…"


def extract_signature(body: str) -> dict[str, object]:
    """Pull the recurring moves out of one script body: its opening, its closing,
    and the sentence that opens each interior paragraph (the transitions)."""
    paras = _paragraphs(body)
    if not paras:
        return {"opening": "", "closing": "", "transitions": []}
    opening = _clip(paras[0])
    closing = _clip(paras[-1])
    interior = paras[1:-1] if len(paras) > 2 else []
    transitions = [_first_sentence(p) for p in interior]
    return {"opening": opening, "closing": closing, "transitions": transitions}


def build_avoid_section(done_scripts: Path, n: int = 3, max_transitions: int = 12) -> str:
    """Assemble the "AVOID THESE" prompt block from the last `n` episodes.

    Returns "" when there's no history, so the script prompt's placeholder
    collapses to nothing on a fresh workspace.
    """
    scripts = recent_generated_scripts(done_scripts, n)
    if not scripts:
        return ""

    openings: list[str] = []
    closings: list[str] = []
    transitions: list[str] = []
    for path in scripts:
        try:
            _, body = parse(path.read_text())
        except OSError:
            continue
        sig = extract_signature(body)
        if sig["opening"]:
            openings.append(str(sig["opening"]))
        if sig["closing"]:
            closings.append(str(sig["closing"]))
        transitions.extend(str(t) for t in sig["transitions"])  # type: ignore[arg-type]

    # Dedupe transitions case-insensitively, preserve order, then cap.
    seen: set[str] = set()
    deduped: list[str] = []
    for t in transitions:
        key = t.lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(t)
    deduped = deduped[:max_transitions]

    if not (openings or closings or deduped):
        return ""

    def bullets(items: list[str]) -> str:
        return "\n".join(f'- "{i}"' for i in items)

    parts = [
        "AVOID THESE — used in recent episodes:",
        f"The last {len(scripts)} episodes opened, closed, and pivoted in the ways "
        "below. Do NOT reuse these openings, closings, or transitions, or any close "
        "paraphrase of them. Find a genuinely different way in, through, and out. "
        "Repeating these structural moves is the single biggest tell that every "
        "episode is the same template.",
    ]
    if openings:
        parts.append("\nRecent openings (do not echo this move or cadence):\n" + bullets(openings))
    if closings:
        parts.append("\nRecent closings (do not echo this register or phrasing):\n" + bullets(closings))
    if deduped:
        parts.append(
            "\nRecent transition / structural phrases (do not reuse, find another way to pivot):\n"
            + bullets(deduped)
        )
    return "\n".join(parts) + "\n"
