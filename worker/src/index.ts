// earworm-feed Worker.
//   GET  /:token/feed.xml   -> private RSS feed (token-gated, unguessable path)
//   POST /episodes          -> register/update an episode (Bearer INGEST_SECRET)
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
}

const show = (env: Env): Show => ({
  title: env.SHOW_TITLE,
  author: env.SHOW_AUTHOR,
  description: env.SHOW_DESCRIPTION,
  email: env.SHOW_EMAIL,
  image: env.SHOW_IMAGE,
  language: env.SHOW_LANGUAGE,
  category: env.SHOW_CATEGORY,
  link: env.SHOW_LINK,
});

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

async function handleFeed(env: Env, token: string, selfUrl: string): Promise<Response> {
  if (!env.FEED_TOKEN || !safeEqual(token, env.FEED_TOKEN)) {
    return new Response("Not found", { status: 404 });
  }
  const { results } = await env.DB.prepare(
    `SELECT guid, slug, title, description, audio_url, audio_bytes, duration_sec, pub_date, transcript_url
     FROM episodes ORDER BY pub_date DESC LIMIT 500`
  ).all<Episode>();
  const xml = buildFeed(show(env), results ?? [], selfUrl);
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

  await env.DB.prepare(
    `INSERT INTO episodes (guid, slug, title, description, audio_url, audio_bytes, duration_sec, pub_date, created_at, transcript_url)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(guid) DO UPDATE SET
       slug=excluded.slug, title=excluded.title, description=excluded.description,
       audio_url=excluded.audio_url, audio_bytes=excluded.audio_bytes,
       duration_sec=excluded.duration_sec, pub_date=excluded.pub_date,
       transcript_url=excluded.transcript_url`
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
      body.transcript_url ?? null
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

    // GET /feed.xml?token=...  (query-param form, friendlier for some apps)
    if (req.method === "GET" && path === "/feed.xml") {
      return handleFeed(env, url.searchParams.get("token") ?? "", url.toString());
    }

    // GET /:token/feed.xml  (path form)
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
