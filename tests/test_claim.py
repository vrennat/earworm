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
