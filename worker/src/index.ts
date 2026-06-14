// earworm-feed Worker. Serves multiple token-gated RSS feeds from one D1 table;
// every episode carries a `feed` tag and each feed is published at its own path.
//   GET  /:token/feed.xml          -> the main feed (token-gated, unguessable path)
//   GET  /:token/:feed/feed.xml    -> a named feed (e.g. /:token/dario-amodei/feed.xml)
//   POST /episodes                 -> register/update an episode (Bearer INGEST_SECRET)
// Audio is served directly from a public R2 bucket; the Worker never proxies it.

import { buildFeed, xmlEscape, type Episode, type Show } from "./rss";

interface Env {
  DB: D1Database;
  FEED_TOKEN: string;
  INGEST_SECRET: string;
  SHOW_TITLE: string;
  SHOW_AUTHOR: string;
  SHOW_DESCRIPTION: string;
  SHOW_EMAIL: string;
  SHOW_IMAGE: string;
  SHOW_LANGUAGE: string;
  SHOW_CATEGORY: string;
  SHOW_LINK: string;
  // Optional. JSON map of feed slug -> partial Show, overriding the SHOW_* defaults
  // for a named feed (so e.g. the "dario-amodei" feed gets its own title/author).
  FEED_META?: string;
  // Optional. When "true", the main feed (/:token/feed.xml) aggregates every
  // episode across all feeds; otherwise it shows only the default-feed episodes.
  MAIN_FEED_INCLUDES_ALL?: string;
}

// The implicit feed for episodes with no explicit tag. Mirrors feed.DEFAULT_FEED
// on the Python side. The main feed serves this feed.
const DEFAULT_FEED = "default";

// A feed slug must be URL-safe and unambiguous in the path (no slashes, lowercase).
const FEED_SLUG = /^[a-z0-9][a-z0-9-]*$/;

const SHOW_COLUMNS =
  "guid, slug, title, description, audio_url, audio_bytes, duration_sec, pub_date, transcript_url, feed";

function feedMeta(env: Env): Record<string, Partial<Show>> {
  try {
    return env.FEED_META ? (JSON.parse(env.FEED_META) as Record<string, Partial<Show>>) : {};
  } catch {
    return {}; // malformed config: fall back to the show defaults rather than 500
  }
}

// Channel metadata for a feed: the SHOW_* defaults, overlaid with any per-feed
// overrides from FEED_META. A feed with no override inherits the show metadata.
const show = (env: Env, feedName: string): Show => ({
  title: env.SHOW_TITLE,
  author: env.SHOW_AUTHOR,
  description: env.SHOW_DESCRIPTION,
  email: env.SHOW_EMAIL,
  image: env.SHOW_IMAGE,
  language: env.SHOW_LANGUAGE,
  category: env.SHOW_CATEGORY,
  link: env.SHOW_LINK,
  ...feedMeta(env)[feedName],
});

const mainFeedIncludesAll = (env: Env): boolean =>
  (env.MAIN_FEED_INCLUDES_ALL ?? "").trim().toLowerCase() === "true";

// Constant-time-ish string compare to avoid leaking secrets via timing.
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

const json = (data: unknown, status = 200): Response =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });

// `feedName` selects a named feed; when omitted this is the main feed, which
// serves either every episode (MAIN_FEED_INCLUDES_ALL) or just the default feed.
async function handleFeed(
  env: Env,
  token: string,
  selfUrl: string,
  feedName?: string
): Promise<Response> {
  if (!env.FEED_TOKEN || !safeEqual(token, env.FEED_TOKEN)) {
    return new Response("Not found", { status: 404 });
  }

  const order = "ORDER BY pub_date DESC LIMIT 500";
  let stmt: D1PreparedStatement;
  if (feedName) {
    stmt = env.DB.prepare(`SELECT ${SHOW_COLUMNS} FROM episodes WHERE feed = ? ${order}`).bind(feedName);
  } else if (mainFeedIncludesAll(env)) {
    stmt = env.DB.prepare(`SELECT ${SHOW_COLUMNS} FROM episodes ${order}`);
  } else {
    stmt = env.DB.prepare(`SELECT ${SHOW_COLUMNS} FROM episodes WHERE feed = ? ${order}`).bind(DEFAULT_FEED);
  }

  const { results } = await stmt.all<Episode>();
  const xml = buildFeed(show(env, feedName ?? DEFAULT_FEED), results ?? [], selfUrl);
  return new Response(xml, {
    headers: {
      "content-type": "application/rss+xml; charset=utf-8",
      "cache-control": "no-cache",
    },
  });
}

async function handleIngest(env: Env, req: Request): Promise<Response> {
  const auth = req.headers.get("authorization") ?? "";
  const token = auth.replace(/^Bearer\s+/i, "");
  if (!env.INGEST_SECRET || !safeEqual(token, env.INGEST_SECRET)) {
    return json({ error: "unauthorized" }, 401);
  }

  let body: Partial<Episode>;
  try {
    body = (await req.json()) as Partial<Episode>;
  } catch {
    return json({ error: "invalid json" }, 400);
  }

  const required = ["guid", "slug", "title", "audio_url", "audio_bytes", "duration_sec"] as const;
  for (const f of required) {
    if (body[f] === undefined || body[f] === null || body[f] === "") {
      return json({ error: `missing field: ${f}` }, 400);
    }
  }

  const pubDate = body.pub_date || new Date().toISOString();
  const createdAt = new Date().toISOString();
  const feed = typeof body.feed === "string" && body.feed.trim() ? body.feed.trim() : DEFAULT_FEED;

  await env.DB.prepare(
    `INSERT INTO episodes (guid, slug, title, description, audio_url, audio_bytes, duration_sec, pub_date, created_at, transcript_url, feed)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(guid) DO UPDATE SET
       slug=excluded.slug, title=excluded.title, description=excluded.description,
       audio_url=excluded.audio_url, audio_bytes=excluded.audio_bytes,
       duration_sec=excluded.duration_sec, pub_date=excluded.pub_date,
       transcript_url=excluded.transcript_url, feed=excluded.feed`
  )
    .bind(
      body.guid,
      body.slug,
      body.title,
      body.description ?? "",
      body.audio_url,
      Math.round(Number(body.audio_bytes)),
      Math.round(Number(body.duration_sec)),
      pubDate,
      createdAt,
      body.transcript_url ?? null,
      feed
    )
    .run();

  return json({ ok: true, guid: body.guid });
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const path = url.pathname;

    if (req.method === "POST" && path === "/episodes") {
      return handleIngest(env, req);
    }

    // GET /feed.xml?token=...[&feed=...]  (query-param form, friendlier for some apps)
    if (req.method === "GET" && path === "/feed.xml") {
      const feedParam = url.searchParams.get("feed") ?? "";
      if (feedParam && !FEED_SLUG.test(feedParam)) {
        return new Response("Not found", { status: 404 });
      }
      return handleFeed(
        env,
        url.searchParams.get("token") ?? "",
        url.toString(),
        feedParam || undefined
      );
    }

    // GET /:token/:feed/feed.xml  (named-feed path form)
    const namedMatch = path.match(/^\/([^/]+)\/([^/]+)\/feed\.xml$/);
    if (req.method === "GET" && namedMatch) {
      const feedName = decodeURIComponent(namedMatch[2]);
      if (!FEED_SLUG.test(feedName)) {
        return new Response("Not found", { status: 404 });
      }
      return handleFeed(env, decodeURIComponent(namedMatch[1]), url.toString(), feedName);
    }

    // GET /:token/feed.xml  (main-feed path form)
    const feedMatch = path.match(/^\/([^/]+)\/feed\.xml$/);
    if (req.method === "GET" && feedMatch) {
      return handleFeed(env, decodeURIComponent(feedMatch[1]), url.toString());
    }

    // Root: a reachable landing page so the channel <link> resolves (200), no info leak.
    if (req.method === "GET" && path === "/") {
      const title = xmlEscape(env.SHOW_TITLE);
      return new Response(`<!doctype html><title>${title}</title><h1>${title}</h1>`, {
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }

    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
