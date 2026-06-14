-- D1 schema for the earworm podcast feed.
-- One row per published episode. `guid` is stable (the content hash of the
-- script body) so re-registering the same episode is an idempotent upsert.
CREATE TABLE IF NOT EXISTS episodes (
    guid         TEXT PRIMARY KEY,
    slug         TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    audio_url    TEXT NOT NULL,
    audio_bytes  INTEGER NOT NULL,
    duration_sec INTEGER NOT NULL,
    pub_date       TEXT NOT NULL,      -- ISO 8601 UTC; converted to RFC 822 in the feed
    created_at     TEXT NOT NULL,
    transcript_url TEXT,               -- optional WebVTT URL (podcast:transcript)
    feed           TEXT NOT NULL DEFAULT 'default'  -- which RSS feed this episode belongs to
);

CREATE INDEX IF NOT EXISTS idx_episodes_pub_date ON episodes (pub_date DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_feed ON episodes (feed, pub_date DESC);
