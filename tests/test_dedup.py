"""Tests for topic dedup on `earworm add`. Run: python tests/test_dedup.py

No pytest dependency — plain asserts. Uses a throwaway EARWORM_HOME so it never
touches a real workspace.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm.config import paths  # noqa: E402


def _fresh_db(tmp: str):
    os.environ["EARWORM_HOME"] = tmp
    paths.cache_clear()
    from earworm import db

    db.init()
    return db


def main() -> int:
    from earworm import db

    # normalize_topic folds case, punctuation, and whitespace to one key
    assert db.normalize_topic("The RAG Revolution!") == db.normalize_topic("the rag   revolution")
    assert db.normalize_topic("A, B, and C?") == "a b and c"
    assert db.normalize_topic("   ") == ""

    with tempfile.TemporaryDirectory() as tmp:
        d = _fresh_db(tmp)
        tid = d.add_topic("Why do songs get stuck in our heads?", source="manual")

        # an exact re-add is caught
        dup = d.find_duplicate_topic("Why do songs get stuck in our heads?")
        assert dup is not None and dup["id"] == tid, dup

        # a casing/punctuation variant is caught too (the 25-30 = 19-21 re-add bug)
        dup2 = d.find_duplicate_topic("why do SONGS get stuck in our heads")
        assert dup2 is not None and dup2["id"] == tid, dup2

        # a genuinely different topic is not a duplicate
        assert d.find_duplicate_topic("How do atomic clocks synchronize the grid?") is None

        # an empty/blank topic never matches
        assert d.find_duplicate_topic("   ") is None

    print("all dedup tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
