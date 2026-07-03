"""Standalone tests for earworm.render's watch retry policy.

No pytest, no heavy deps — mutagen/kokoro are imported lazily inside render, so
this exercises only the pure backoff helpers. Run: python tests/test_render_watch.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm import render  # noqa: E402


def main() -> int:
    # backoff grows exponentially from the base and is capped
    assert render._retry_backoff(1) == render._RETRY_BASE_SECONDS
    assert render._retry_backoff(2) == render._RETRY_BASE_SECONDS * 2
    assert render._retry_backoff(3) == render._RETRY_BASE_SECONDS * 4
    assert render._retry_backoff(99) == render._RETRY_MAX_SECONDS  # capped, never unbounded

    # a file with no prior failure is always due
    assert render._is_due(None, mtime=100.0, now=0.0) is True

    # a file still inside its backoff window (unchanged) is NOT retried — this is
    # the fix: a broken script no longer re-runs synthesis every poll
    prev = (100.0, 1, 500.0)  # failed at mtime 100, next attempt at monotonic 500
    assert render._is_due(prev, mtime=100.0, now=499.0) is False

    # once the backoff window elapses, it is due again
    assert render._is_due(prev, mtime=100.0, now=500.0) is True

    # editing the file (mtime changes) makes it due immediately, backoff be damned
    assert render._is_due(prev, mtime=200.0, now=0.0) is True

    print("all render watch tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
