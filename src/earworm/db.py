"""SQLite queue + episode ledger. Local source of truth for the runner.

Two tables:
- topics: the producer/consumer queue (manual + auto items).
- episodes: a ledger of rendered episodes, keyed by content hash for idempotency.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .config import paths
from .frontmatter import parse as parse_frontmatter

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual','auto')),
    status      TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done','failed')),
    priority    INTEGER NOT NULL DEFAULT 0,  -- higher runs first; timely paper drops jump the queue
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

# Columns added to `topics` after its initial schema; applied to existing dbs.
_TOPIC_MIGRATIONS = {
    # Run ordering weight. Existing rows backfill to 0 (plain FIFO), so the queue
    # behaves exactly as before until something is queued with a higher priority.
    "priority": "ALTER TABLE topics ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
}

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
        topic_cols = {r["name"] for r in conn.execute("PRAGMA table_info(topics)")}
        for col, ddl in _TOPIC_MIGRATIONS.items():
            if col not in topic_cols:
                conn.execute(ddl)
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

def normalize_topic(topic: str) -> str:
    """Fold a topic to a comparison key: lowercase, strip punctuation, collapse
    whitespace. Catches re-queues of the same question that differ only in casing
    or punctuation (the duplicate 25-30 = 19-21 re-adds were exact copies)."""
    return re.sub(r"[^a-z0-9]+", " ", topic.lower()).strip()


def find_duplicate_topic(topic: str) -> Optional[sqlite3.Row]:
    """An existing queued/finished topic whose normalized form matches `topic`, or
    None. Compared in Python so casing/punctuation differences collapse."""
    key = normalize_topic(topic)
    if not key:
        return None
    with connect() as conn:
        for r in conn.execute("SELECT * FROM topics ORDER BY id ASC"):
            if normalize_topic(r["topic"]) == key:
                return r
    return None


def _staged_topics(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Main-feed scripts waiting in the watcher, excluding private previews."""
    staged: list[sqlite3.Row] = []
    inbox = paths().inbox_scripts.resolve()
    for row in conn.execute(
        "SELECT id, topic, status, priority, script_path FROM topics t "
        "WHERE status='done' AND script_path IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM episodes e WHERE e.slug=t.run_id) ORDER BY script_path"
    ):
        script = Path(row["script_path"])
        if script.parent.resolve() != inbox:
            continue
        try:
            metadata, _ = parse_frontmatter(script.read_text())
        except (OSError, UnicodeError, ValueError):
            continue  # A watcher may have moved the script since the query.
        if metadata.get("feed", "default") == "default":
            staged.append(row)
    return staged


def recent_coverage(limit: int | None = None) -> list[str]:
    """Main-feed novelty archive plus active commitments, newest first.

    Default to the whole archive: an old episode is still covered. Failed leads
    and other feeds are not coverage of this show. Include active queued topics
    without repeating the topic behind each episode. Finished but unrendered
    scripts in the watched inbox are commitments; private previews are excluded.
    This is NOT a playback window; discovery_context supplies that separately.
    The backend's input budget still bounds a call and fails before queue writes.
    """
    lines: list[str] = []
    with connect() as conn:
        for r in conn.execute(
            "SELECT title, description FROM episodes WHERE title IS NOT NULL AND feed='default' "
            "ORDER BY id DESC LIMIT ?",
            (-1 if limit is None else limit,),
        ):
            desc = (r["description"] or "").strip().split("\n", 1)[0].strip()
            lines.append(f"{r['title']} — {desc}" if desc else str(r["title"]))
        for r in _staged_topics(conn):
            lines.append(f"[staged topic #{r['id']}; not rendered] {r['topic']}")
        for r in conn.execute(
            "SELECT id, topic, status FROM topics "
            "WHERE status IN ('pending', 'running') "
            "ORDER BY id DESC LIMIT ?", (-1 if limit is None else limit,)
        ):
            lines.append(f"[{r['status']} topic #{r['id']}; not rendered] {r['topic']}")
    return lines


def discovery_context(window: int = 10) -> dict[str, str]:
    """Separate heard-material proxies from the projected upcoming schedule.

    Rendered main-feed episodes count even if manually ingested into that feed.
    Publication/listening is not inferred. Staged scripts precede running work,
    then pending items use priority/FIFO order. Nothing is re-queued here.
    """
    history: list[str] = []
    upcoming: list[str] = []
    with connect() as conn:
        episodes = list(conn.execute(
            "SELECT e.id, e.title, e.description, e.created_at, "
            "(SELECT t.topic FROM topics t WHERE t.run_id=e.slug LIMIT 1) AS topic "
            "FROM episodes e WHERE e.feed='default' AND e.title IS NOT NULL "
            "ORDER BY e.created_at DESC, e.id DESC LIMIT ?", (window,)
        ))
        for r in reversed(episodes):
            desc = (r["description"] or "").strip().split("\n", 1)[0].strip()
            history.append(f"- {r['created_at'][:10]} episode #{r['id']}: {r['title']} — {desc}"
                           + (f"\n  Original topic: {r['topic']}" if r["topic"] else ""))
        for r in _staged_topics(conn):
            upcoming.append(f"- [staged; awaiting narration; topic #{r['id']}] {r['topic']}")
        for r in conn.execute(
            "SELECT id, topic, status, priority FROM topics "
            "WHERE status IN ('pending', 'running') "
            "ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, priority DESC, id ASC"
        ):
            upcoming.append(f"- [{r['status']}; priority={r['priority']}; topic #{r['id']}] {r['topic']}")
    return {
        "recent_episodes": "\n".join(history) or "(no rendered main-feed episodes)",
        "queued_topics": "\n".join(upcoming) or "(no staged, running, or pending topics)",
    }


def add_topic(topic: str, source: str = "manual", priority: int = 0) -> int:
    """Queue a topic. `priority` weights run order — a higher value is claimed
    before lower ones regardless of age (used to fast-track timely paper drops).
    """
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO topics (topic, source, status, priority, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (topic, source, priority, now_iso()),
        )
        return int(cur.lastrowid)


def list_topics(limit: int = 50) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(
            conn.execute(
                "SELECT * FROM topics ORDER BY id DESC LIMIT ?", (limit,)
            )
        )


# Run order for the queue: highest priority first, then oldest-id (FIFO) within a
# priority band. Kept identical in `next_pending` (peek) and `claim_next_pending`
# (atomic take) so the row a caller peeks is the row it claims.
_QUEUE_ORDER = "ORDER BY priority DESC, id ASC"


def next_pending() -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            f"SELECT * FROM topics WHERE status='pending' {_QUEUE_ORDER} LIMIT 1"
        ).fetchone()


def claim_next_pending() -> Optional[sqlite3.Row]:
    """Atomically claim the highest-priority pending topic (status -> running),
    breaking ties by age.

    A single guarded UPDATE, so two concurrent runners (the daily launchd job
    overlapping a manual run) can never both take the same row. run_id is
    backfilled by mark_running once the caller has derived it from the row."""
    with connect() as conn:
        return conn.execute(
            "UPDATE topics SET status='running', notes=NULL "
            f"WHERE id=(SELECT id FROM topics WHERE status='pending' {_QUEUE_ORDER} LIMIT 1) "
            "RETURNING *"
        ).fetchone()


def claim_topic(topic_id: int) -> bool:
    """Guarded claim of a specific topic. False means it was no longer runnable —
    e.g. a concurrent run took it between the caller's status check and here."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE topics SET status='running', notes=NULL "
            "WHERE id=? AND status IN ('pending','failed')",
            (topic_id,),
        )
        return cur.rowcount == 1


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
