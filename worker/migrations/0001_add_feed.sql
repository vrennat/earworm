-- Multi-feed support: tag every episode with the RSS feed it belongs to.
-- Run once against an existing deployment (fresh deploys get this from schema.sql):
--   bunx wrangler d1 execute brief --remote --file migrations/0001_add_feed.sql
-- Existing rows backfill to 'default' (the main feed), so nothing moves until an
-- episode is re-published with a new feed tag.
ALTER TABLE episodes ADD COLUMN feed TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_episodes_feed ON episodes (feed, pub_date DESC);
