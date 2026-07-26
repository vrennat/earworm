"""Concurrency tests for the topic-queue claim. Run: uv run python tests/test_claim.py

No pytest dependency — plain asserts so it runs anywhere the package imports.

Two concurrent `earworm run` invocations (the daily launchd job overlapping a
manual run) must never both claim the same pending topic. These tests pin the
atomic claim at the db layer: claim_next_pending is a single guarded UPDATE,
and claim_topic refuses a row another process already flipped to running.
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm.config import paths  # noqa: E402


def _fresh_db(tmp: str):
    os.environ["EARWORM_HOME"] = tmp
    paths.cache_clear()
    from earworm import db

    db.init()
    return db


def test_claim_takes_oldest_pending_and_marks_running(tmp: str) -> None:
    db = _fresh_db(tmp)
    first = db.add_topic("older topic")
    db.add_topic("newer topic")
    row = db.claim_next_pending()
    assert row is not None and int(row["id"]) == first
    assert db.get_topic(first)["status"] == "running"


def test_claim_returns_none_when_no_pending(tmp: str) -> None:
    db = _fresh_db(tmp)
    assert db.claim_next_pending() is None


def test_sequential_claims_take_distinct_rows(tmp: str) -> None:
    db = _fresh_db(tmp)
    a = db.add_topic("a")
    b = db.add_topic("b")
    taken = {int(db.claim_next_pending()["id"]), int(db.claim_next_pending()["id"])}
    assert taken == {a, b}
    assert db.claim_next_pending() is None


def test_claim_topic_rejects_already_running(tmp: str) -> None:
    db = _fresh_db(tmp)
    tid = db.add_topic("contested")
    assert db.claim_topic(tid) is True
    assert db.claim_topic(tid) is False


def test_claim_topic_allows_failed_retry(tmp: str) -> None:
    db = _fresh_db(tmp)
    tid = db.add_topic("flaky")
    db.claim_topic(tid)
    db.mark_failed(tid, "boom")
    assert db.claim_topic(tid) is True


def test_priority_topic_is_claimed_before_older_lower_priority(tmp: str) -> None:
    db = _fresh_db(tmp)
    db.add_topic("older, evergreen")          # id 1, priority 0
    db.add_topic("newer, evergreen")          # id 2, priority 0
    hot = db.add_topic("timely paper", priority=2)  # id 3, jumps the queue
    row = db.claim_next_pending()
    assert row is not None and int(row["id"]) == hot, dict(row) if row else None


def test_equal_priority_breaks_ties_by_age(tmp: str) -> None:
    db = _fresh_db(tmp)
    a = db.add_topic("a", priority=1)
    db.add_topic("b", priority=1)
    row = db.claim_next_pending()
    assert row is not None and int(row["id"]) == a


def test_next_pending_peek_matches_claim_order(tmp: str) -> None:
    db = _fresh_db(tmp)
    db.add_topic("evergreen")
    hot = db.add_topic("hot", priority=5)
    assert int(db.next_pending()["id"]) == hot  # peek agrees with the atomic claim


def test_priority_column_backfills_on_existing_db(tmp: str) -> None:
    """A db created before the priority column still upgrades cleanly: init adds
    the column, legacy rows default to 0, and a new high-priority row jumps ahead."""
    os.environ["EARWORM_HOME"] = tmp
    paths.cache_clear()
    from earworm import db

    # Simulate a pre-migration topics table (no priority column).
    with db.connect() as conn:
        conn.executescript(
            "CREATE TABLE topics ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL,"
            " source TEXT NOT NULL DEFAULT 'manual',"
            " status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,"
            " notes TEXT, run_id TEXT, report_path TEXT, script_path TEXT);"
        )
        conn.execute(
            "INSERT INTO topics (topic, status, created_at) VALUES ('legacy', 'pending', '2026-01-01')"
        )

    db.init()  # applies the priority migration
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(topics)")}
    assert "priority" in cols
    legacy = db.get_topic(1)
    assert legacy["priority"] == 0
    hot = db.add_topic("fresh + hot", priority=3)
    assert int(db.claim_next_pending()["id"]) == hot


def test_recent_coverage_includes_episode_thesis(tmp: str) -> None:
    db = _fresh_db(tmp)
    db.upsert_episode(
        slug="2026-01-01-0001-x",
        title="The Part Nobody Wrote Down",
        content_hash="hash1",
        audio_path="/x.mp3",
        report_path=None,
        duration_sec=600.0,
        description="Lost technologies were rarely lost from the written record.",
    )
    db.add_topic("some queued topic")
    lines = db.recent_coverage()
    assert any("The Part Nobody Wrote Down — Lost technologies" in ln for ln in lines), lines
    assert any("some queued topic" in ln for ln in lines), lines


def test_parallel_claims_never_share_a_row(tmp: str) -> None:
    db = _fresh_db(tmp)
    ids = [db.add_topic(f"topic {i}") for i in range(8)]
    claimed: list[int] = []
    lock = threading.Lock()

    def drain() -> None:
        while (row := db.claim_next_pending()) is not None:
            with lock:
                claimed.append(int(row["id"]))

    threads = [threading.Thread(target=drain) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claimed) == sorted(ids)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                t(tmp)
                print(f"  ok  {t.__name__}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {t.__name__}: {e}")
            finally:
                os.environ.pop("EARWORM_HOME", None)
                paths.cache_clear()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
