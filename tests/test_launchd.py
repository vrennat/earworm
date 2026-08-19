"""Regression checks for the macOS launchd entry points.

The July 2026 outage happened before Earworm's Python code could start: both
jobs executed .venv/bin/earworm directly, whose generated shebang pointed at a
Homebrew Python that had been removed. Keep both entry points behind uv so the
locked environment can be repaired automatically.
"""

from __future__ import annotations

import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_watch_uses_locked_uv() -> None:
    with (ROOT / "launchd/com.earworm.watch.plist").open("rb") as handle:
        plist = plistlib.load(handle)

    args = plist["ProgramArguments"]
    assert args[:3] == ["/usr/bin/env", "uv", "run"]
    assert "--locked" in args
    assert args[-2:] == ["earworm", "watch"]
    assert not any(".venv/bin" in arg for arg in args)
    assert plist["EnvironmentVariables"]["PYTHONUNBUFFERED"] == "1"


def test_daily_uses_locked_uv() -> None:
    script = (ROOT / "launchd/daily.sh").read_text()
    assert 'EARWORM=("$UV" run --project "$EARWORM_DIR" --locked earworm)' in script
    assert 'EARWORM="$EARWORM_DIR/.venv/bin/earworm"' not in script


if __name__ == "__main__":
    test_watch_uses_locked_uv()
    test_daily_uses_locked_uv()
    print("all launchd entry-point tests passed")
