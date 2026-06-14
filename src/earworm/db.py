"""SQLite queue + episode ledger. Local source of truth for the runner.

Two tables:
- topics: the producer/consumer queue (manual + auto items).
- episodes: a ledger of rendered episodes, keyed by content hash for idempotency.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .config import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual','auto')),
    status      TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','failed')),
    created_at  TEXT NOT NULL,
    notes       TEXT,
    run_id      TEXT,
    report_path TEXT,
    script_path TEXT
);

CREATE TABLE IF NOT EXISTS episodes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT NOT NULL,
    title        TEXT,
    guid         TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    audio_path   TEXT,
    report_path  TEXT,
    duration_sec REAL,
    created_at   TEXT NOT NULL,
    description    TEXT,
    audio_url      TEXT,
    published_at   TEXT,
    transcript_url TEXT,
    feed           TEXT NOT NULL DEFAULT 'default'  -- which RSS feed this episode belongs to
);
"""

# Columns added after the initial Phase 1 schema; applied to existing dbs.
_EPISODE_MIGRATIONS = {
    "description": "ALTER TABLE episodes ADD COLUMN description TEXT",
    "audio_url": "ALTER TABLE episodes ADD COLUMN audio_url TEXT",
    "published_at": "ALTER TABLE episodes ADD COLUMN published_at TEXT",
    "transcript_url": "ALTER TABLE episodes ADD COLUMN transcript_url TEXT",
    # `guid` is the episode's stable feed identity (the content hash of its FIRST
    # render). It is reused across re-renders so the feed replaces, never
    # duplicates. `content_hash` still tracks the current body for skip-detection.
    "guid": "ALTER TABLE episodes ADD COLUMN guid TEXT",
    # The RSS feed an episode belongs to. Existing rows backfill to 'default' (the
    # main feed), so legacy episodes keep their current placement.
    "feed": "ALTER TABLE episodes ADD COLUMN feed TEXT NOT NULL DEFAULT 'default'",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    return paths().db


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    paths().ensure_dirs()
    with connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(episodes)")}
        for col, ddl in _EPISODE_MIGRATIONS.items():
            if col not in cols:
                conn.execute(ddl)
        # Backfill guid for legacy rows: the original scheme used content_hash as
        # the guid, so reuse it (keeps existing feed entries stable, no churn).
        conn.execute("UPDATE episodes SET guid = content_hash WHERE guid IS NULL")
        # One row per episode identity (slug). Guards against a concurrent second
        # render inserting a duplicate. Safe: the renderer dedupes by slug.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_episodes_slug ON episodes (slug)"
        )


# --- topics queue ---------------------------------------------------------

def add_topic(topic: str, source: str = "manual") -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO topics (topic, source, status, created_at) VALUES (?, ?, 'pending', ?)",
            (topic, source, now_iso()),
        )
        return int(cur.lastrowid)


def list_topics(limit: int = 50) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(
            conn.execute(
                "SELECT * FROM topics ORDER BY id DESC LIMIT ?", (limit,)
            )
        )


def next_pending() -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM topics WHERE status='pending' ORDER BY id ASC LIMIT 1"
        ).fetchone()


def get_topic(topic_id: int) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()


def mark_running(topic_id: int, run_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE topics SET status='running', run_id=?, notes=NULL WHERE id=?",
            (run_id, topic_id),
        )


def mark_done(topic_id: int, report_path: str, script_path: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE topics SET status='done', report_path=?, script_path=? WHERE id=?",
            (report_path, script_path, topic_id),
        )


def mark_failed(topic_id: int, error: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE topics SET status='failed', notes=? WHERE id=?",
            (error[:4000], topic_id),
        )


def reset_stale_running() -> int:
    """Return 'running' items to 'pending' (e.g. after a crash). Returns count reset."""
    with connect() as conn:
        cur = conn.execute("UPDATE topics SET status='pending' WHERE status='running'")
        return cur.rowcount


# --- episodes ledger ------------------------------------------------------

def get_episode_by_slug(slug: str) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM episodes WHERE slug=?", (slug,)
        ).fetchone()


def upsert_episode(
    slug: str,
    title: str,
    content_hash: str,
    audio_path: str,
    report_path: Optional[str],
    duration_sec: float,
    description: str = "",
    feed: str = "default",
) -> str:
    """Insert or update the episode keyed on its identity (slug), and return its
    stable guid. A brand-new episode takes its content hash as the guid; a
    re-render of an existing slug REUSES that guid (and keeps the original
    created_at, so the feed pub_date is stable) while refreshing the body hash.
    published_at is cleared so the freshly rendered audio is (re)published. `feed`
    is the RSS feed the episode belongs to (defaults to the main feed).
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT guid, created_at FROM episodes WHERE slug=?", (slug,)
        ).fetchone()
        if row is not None:
            guid = row["guid"] or content_hash
            conn.execute(
                """UPDATE episodes SET title=?, guid=?, content_hash=?, audio_path=?,
                       report_path=?, duration_sec=?, description=?, feed=?, published_at=NULL
                   WHERE slug=?""",
                (title, guid, content_hash, audio_path, report_path, duration_sec, description, feed, slug),
            )
            return guid
        conn.execute(
            """INSERT INTO episodes
               (slug, title, guid, content_hash, audio_path, report_path, duration_sec, created_at, description, feed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, title, content_hash, content_hash, audio_path, report_path, duration_sec, now_iso(), description, feed),
        )
        return content_hash


def set_episode_feed(slug: str, feed: str) -> bool:
    """Re-tag an episode's feed without re-rendering. Clears published_at so the
    next publish moves it onto the new feed. Returns True if a row was updated.
    """
    with connect() as conn:
        cur = conn.execute(
            "UPDATE episodes SET feed=?, published_at=NULL WHERE slug=?", (feed, slug)
        )
        return cur.rowcount > 0


def get_episode(guid: str) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM episodes WHERE guid=?", (guid,)
        ).fetchone()


def list_unpublished() -> list[sqlite3.Row]:
    with connect() as conn:
        return list(
            conn.execute(
                "SELECT * FROM episodes WHERE published_at IS NULL ORDER BY id ASC"
            )
        )


def mark_published(guid: str, audio_url: str, transcript_url: Optional[str] = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE episodes SET published_at=?, audio_url=?, transcript_url=? WHERE guid=?",
            (now_iso(), audio_url, transcript_url, guid),
        )
