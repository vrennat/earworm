"""Headless Claude Code wrapper.

Runs `claude -p` non-interactively with an explicit tool allowlist (tools not in
the allowlist are denied in print mode, since there is no interactive prompt).
The prompt is passed on stdin to avoid arg-length/escaping issues. We treat the
expected output file as the source of truth for success.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Sequence


class ClaudeError(RuntimeError):
    pass


def _parse_result(stdout: str) -> dict:
    """Normalize `claude -p --output-format json` output to the result dict.

    The CLI emits either a single result object or a JSON array of message
    objects whose final `type == "result"` element carries the status.
    """
    if not stdout.strip():
        return {}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw": stdout[-2000:]}
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in reversed(data):
            if isinstance(item, dict) and item.get("type") == "result":
                return item
        for item in reversed(data):
            if isinstance(item, dict):
                return item
    return {"raw": stdout[-2000:]}


def render_prompt(template_path: Path, **vars: str) -> str:
    text = template_path.read_text()
    for key, value in vars.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def run_text(
    prompt: str,
    *,
    cwd: Path,
    timeout: int = 300,
    model: str | None = None,
) -> str:
    """Run claude headless for pure generation (no tools, no file output) and
    return the final assistant text. Used by the auto-topic generator.
    """
    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--tools", "",  # disable all tools: pure ideation, no permission prompts
    ]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(
        cmd, input=prompt, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
    )
    result = _parse_result(proc.stdout)
    if proc.returncode != 0:
        raise ClaudeError(
            f"claude exited {proc.returncode}. stderr={proc.stderr[-800:]!r}"
        )
    if result.get("is_error"):
        raise ClaudeError(f"claude reported error: {result.get('result')!r}")
    return str(result.get("result", ""))


def run(
    prompt: str,
    *,
    cwd: Path,
    allowed_tools: Sequence[str],
    expect_file: Path,
    timeout: int = 1200,
    model: str | None = None,
) -> dict:
    """Run claude headless. Returns the parsed JSON result.

    Raises ClaudeError if the process fails or the expected file is not written.
    """
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        " ".join(allowed_tools),
    ]
    if model:
        cmd += ["--model", model]

    proc = subprocess.run(
        cmd,
        input=prompt,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    result = _parse_result(proc.stdout)

    if proc.returncode != 0:
        raise ClaudeError(
            f"claude exited {proc.returncode}. "
            f"result={result.get('result') or result.get('raw')!r} "
            f"stderr={proc.stderr[-1000:]!r}"
        )

    if result.get("is_error"):
        raise ClaudeError(f"claude reported error: {result.get('result')!r}")

    if not expect_file.exists():
        raise ClaudeError(
            f"claude finished but expected file was not written: {expect_file}. "
            f"result={result.get('result')!r}"
        )

    return result
