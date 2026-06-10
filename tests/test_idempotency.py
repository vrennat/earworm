"""Regression tests for the feed-duplication bug. Run: uv run python tests/test_idempotency.py

No pytest dependency — plain asserts so it runs anywhere the package imports.

Episodes are deduped by identity (the slug), and each slug keeps a stable feed
`guid` across re-renders, so a changed re-render REPLACES the feed entry instead
of creating a second one. These tests pin that invariant at the two layers that
enforce it: the local ledger upsert and the R2 object key derivation.
"""
import os
import sqlite3
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


def test_new_episode_uses_content_hash_as_guid(tmp: str) -> None:
    db = _fresh_db(tmp)
    guid = db.upsert_episode(
        slug="2026-06-03-0021-neural-nets", title="Neural Nets",
        content_hash="aaaa1111", audio_path="/x.mp3", report_path=None, duration_sec=10.0,
    )
    assert guid == "aaaa1111"
    row = db.get_episode_by_slug("2026-06-03-0021-neural-nets")
    assert row["guid"] == "aaaa1111" and row["content_hash"] == "aaaa1111"


def test_rerender_same_slug_reuses_guid_and_replaces(tmp: str) -> None:
    db = _fresh_db(tmp)
    first = db.upsert_episode(
        slug="ep", title="v1", content_hash="hash_v1",
        audio_path="/v1.mp3", report_path=None, duration_sec=10.0,
    )
    db.mark_published(first, "https://r2/v1.mp3", None)

    # Re-render with a CHANGED body (new content hash) for the SAME slug.
    second = db.upsert_episode(
        slug="ep", title="v2", content_hash="hash_v2",
        audio_path="/v2.mp3", report_path=None, duration_sec=12.0,
    )

    assert second == first, "guid must stay stable across re-renders"
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM episodes WHERE slug='ep'").fetchall()
    assert len(rows) == 1, "a re-render must not create a second row"
    assert rows[0]["content_hash"] == "hash_v2", "body hash is refreshed"
    assert rows[0]["title"] == "v2"
    assert rows[0]["published_at"] is None, "changed audio must be re-published"


def test_distinct_slugs_get_distinct_rows(tmp: str) -> None:
    db = _fresh_db(tmp)
    db.upsert_episode(slug="a", title="A", content_hash="h1", audio_path="/a", report_path=None, duration_sec=1.0)
    db.upsert_episode(slug="b", title="B", content_hash="h2", audio_path="/b", report_path=None, duration_sec=1.0)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 2


def test_unique_slug_index_blocks_raw_duplicate_insert(tmp: str) -> None:
    db = _fresh_db(tmp)
    db.upsert_episode(slug="dup", title="X", content_hash="h1", audio_path="/x", report_path=None, duration_sec=1.0)
    # A second raw INSERT for the same slug (e.g. a racing watcher) must fail
    # rather than silently create a duplicate feed entry.
    raised = False
    try:
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO episodes (slug, title, guid, content_hash, created_at) VALUES (?,?,?,?,?)",
                ("dup", "X2", "h2", "h2", db.now_iso()),
            )
    except sqlite3.IntegrityError:
        raised = True
    assert raised, "unique slug index must block a duplicate row"


def test_reset_stale_running_requeues_crashed_topics(tmp: str) -> None:
    db = _fresh_db(tmp)
    tid = db.add_topic("a crashed topic", source="manual")
    db.mark_running(tid, "2026-06-09-0001-a-crashed-topic")
    assert db.get_topic(tid)["status"] == "running"

    n = db.reset_stale_running()

    assert n == 1, "one running topic should be reset"
    assert db.get_topic(tid)["status"] == "pending", "crashed topic must return to the queue"


def test_r2_key_is_stable_per_guid(tmp: str) -> None:
    from earworm import feed

    orig_cfg, orig_secrets = feed.feed_config, feed.secrets
    feed.feed_config = lambda: {"audio_key_prefix": "audio"}
    feed.secrets = lambda: {"feed_token": "tok"}
    try:
        # Same slug + same guid (a re-render) -> identical key -> overwrite, no orphan.
        k1 = feed._object_key("my-slug", "guid_abc", "mp3")
        assert k1 == feed._object_key("my-slug", "guid_abc", "mp3")
        # Different guid -> different token dir.
        assert feed._object_key("my-slug", "guid_xyz", "mp3") != k1
    finally:
        feed.feed_config, feed.secrets = orig_cfg, orig_secrets


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
