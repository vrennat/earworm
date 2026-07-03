"""`earworm watch` / `earworm render` — the dumb, deterministic renderer.

For each new inbox/scripts/*.md: synthesize audio, tag it with metadata + show
notes derived from the report, record it in the episodes ledger, and move the
processed script to done/. No LLM. Idempotent on the script body's content hash.

Produces a tagged local mp3; if the feed is configured, also uploads to R2 and
registers the episode with the Worker.
"""
from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Optional

from . import db, feed, shownotes, transcript
from .config import paths, show_config, voice_config
from .frontmatter import parse
from .tts import TTSEngine, get_engine


def content_hash(body: str) -> str:
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()[:16]


def _tag(mp3_path: Path, *, title: str, date: str, notes: str, duration_sec: float) -> None:
    # mutagen imported lazily so non-render commands (and the watch-policy tests)
    # don't pull the audio stack.
    from mutagen.id3 import COMM, TALB, TCON, TDRC, TIT2, TLEN, TPE1
    from mutagen.mp3 import MP3

    show = show_config()
    audio = MP3(str(mp3_path))
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags.setall("TIT2", [TIT2(encoding=3, text=title)])
    tags.setall("TPE1", [TPE1(encoding=3, text=show.get("author", "Earworm"))])
    tags.setall("TALB", [TALB(encoding=3, text=show.get("title", "Earworm"))])
    tags.setall("TCON", [TCON(encoding=3, text="Podcast")])
    if date:
        tags.setall("TDRC", [TDRC(encoding=3, text=date)])
    tags.setall("TLEN", [TLEN(encoding=3, text=str(int(duration_sec * 1000)))])
    if notes:
        tags.setall("COMM", [COMM(encoding=3, lang="eng", desc="", text=notes)])
    audio.save()


def render_script_file(
    script_path: Path,
    engine: Optional[TTSEngine] = None,
    publish: bool = True,
    log=print,
) -> dict:
    """Render one script file to a tagged mp3. Returns a result dict.

    Idempotent: a script whose body hash is already in the ledger is skipped and
    its file is moved to done/ without producing a duplicate episode. If `publish`
    is set and the feed is configured, the episode is uploaded + registered;
    publish failures are logged (not raised) and retryable via `earworm publish`.
    """
    p = paths()
    p.ensure_dirs()
    db.init()

    text = script_path.read_text()
    meta, body = parse(text)
    slug = script_path.stem
    title = meta.get("title") or slug
    date = meta.get("date", "")
    report_path = meta.get("report_path")
    feed_name = (meta.get("feed") or feed.DEFAULT_FEED).strip() or feed.DEFAULT_FEED
    chash = content_hash(body)
    audio_path = p.episodes / f"{slug}.mp3"

    # Idempotent on episode identity (the slug), not the body hash. An identical
    # re-drop on the same feed whose audio still exists is skipped. A *changed*
    # re-render — or the same body re-tagged to a different feed — falls through
    # and REPLACES the episode in place (reusing the stable guid -> same R2 key +
    # feed row), so it never produces a duplicate.
    existing = db.get_episode_by_slug(slug)
    if (
        existing
        and existing["content_hash"] == chash
        and existing["feed"] == feed_name
        and audio_path.exists()
    ):
        dest = p.done_scripts / script_path.name
        if script_path.resolve() != dest.resolve():
            shutil.move(str(script_path), str(dest))
        return {"status": "skipped_duplicate", "slug": slug, "title": title, "feed": feed_name}

    if engine is None:
        engine = get_engine(voice_config())

    if hasattr(engine, "synthesize_with_segments"):
        mp3_bytes, segments = engine.synthesize_with_segments(body)
    else:
        mp3_bytes, segments = engine.synthesize(body), []
    audio_path.write_bytes(mp3_bytes)

    transcript_path: Optional[Path] = None
    if segments:
        transcript_path = p.episodes / f"{slug}.vtt"
        transcript_path.write_text(transcript.build_vtt(segments))

    from mutagen.mp3 import MP3

    duration_sec = MP3(str(audio_path)).info.length
    summary, sources = shownotes.extract(Path(report_path) if report_path else None)
    notes = shownotes.format_notes(summary, sources)
    _tag(audio_path, title=title, date=date, notes=notes, duration_sec=duration_sec)

    guid = db.upsert_episode(
        slug=slug,
        title=title,
        content_hash=chash,
        audio_path=str(audio_path),
        report_path=report_path,
        duration_sec=duration_sec,
        description=notes,
        feed=feed_name,
    )

    # Move processed script + copy report into done/ for archive. Skip the copy
    # when the report already lives at the archive path (re-rendered episodes whose
    # frontmatter report_path points into done/reports/) — copy2 would SameFileError.
    shutil.move(str(script_path), str(p.done_scripts / script_path.name))
    if report_path and Path(report_path).exists():
        report_dest = p.done_reports / f"{slug}.report.md"
        if Path(report_path).resolve() != report_dest.resolve():
            shutil.copy2(report_path, report_dest)

    result = {
        "status": "rendered",
        "slug": slug,
        "title": title,
        "feed": feed_name,
        "audio_path": str(audio_path),
        "duration_sec": round(duration_sec, 1),
        "engine": engine.name,
    }

    if publish:
        ok, reason = feed.is_configured()
        if not ok:
            log(f"[publish] skipped: {reason}")
        else:
            try:
                ep = db.get_episode(guid)
                audio_url, transcript_url = feed.publish(
                    guid=guid,
                    slug=slug,
                    title=title,
                    description=notes,
                    audio_path=audio_path,
                    duration_sec=duration_sec,
                    transcript_path=transcript_path,
                    pub_date=ep["created_at"] if ep else None,
                    feed=feed_name,
                )
                db.mark_published(guid, audio_url, transcript_url)
                result["audio_url"] = audio_url
                if transcript_url:
                    result["transcript_url"] = transcript_url
                log(f"[publish] {audio_url}" + (f"  + transcript" if transcript_url else ""))
            except Exception as exc:  # noqa: BLE001 - rendered episode is safe; retry later
                log(f"[publish] FAILED (retry with `earworm publish`): {type(exc).__name__}: {exc}")

    return result


def publish_unpublished(log=print) -> int:
    """Backfill: upload + register every episode lacking a published_at. Returns count."""
    db.init()
    ok, reason = feed.is_configured()
    if not ok:
        raise RuntimeError(f"feed not configured: {reason}")
    rows = db.list_unpublished()
    published = 0
    for r in rows:
        audio_path = Path(r["audio_path"]) if r["audio_path"] else None
        if not audio_path or not audio_path.exists():
            log(f"[publish] skip {r['slug']}: audio file missing")
            continue
        vtt = audio_path.with_suffix(".vtt")
        try:
            guid = r["guid"] or r["content_hash"]
            audio_url, transcript_url = feed.publish(
                guid=guid,
                slug=r["slug"],
                title=r["title"] or r["slug"],
                description=r["description"] or "",
                audio_path=audio_path,
                duration_sec=r["duration_sec"] or 0.0,
                transcript_path=vtt if vtt.exists() else None,
                pub_date=r["created_at"],
                feed=r["feed"] or feed.DEFAULT_FEED,
            )
            db.mark_published(guid, audio_url, transcript_url)
            published += 1
            log(f"[publish] {r['slug']} -> {audio_url}")
        except Exception as exc:  # noqa: BLE001
            log(f"[publish] FAILED {r['slug']}: {type(exc).__name__}: {exc}")
    return published


# A script that keeps throwing is retried with exponential backoff (not every
# poll), so one broken file can't pin the CPU re-running synthesis every 2s. The
# backoff resets the moment the file is edited (mtime changes), so fixing a script
# gets it picked up on the next poll instead of waiting out the delay.
_RETRY_BASE_SECONDS = 30.0
_RETRY_MAX_SECONDS = 3600.0

# A failure record: (mtime when it failed, consecutive failure count, monotonic
# time of the next allowed attempt).
_Failure = tuple[float, int, float]


def _retry_backoff(count: int) -> float:
    """Exponential backoff for the `count`-th consecutive failure, capped."""
    return min(_RETRY_BASE_SECONDS * 2 ** (count - 1), _RETRY_MAX_SECONDS)


def _is_due(prev: Optional[_Failure], mtime: float, now: float) -> bool:
    """Whether a script should be (re)attempted now: never failed, edited since it
    failed (mtime changed), or its backoff window has elapsed."""
    if prev is None:
        return True
    fail_mtime, _count, next_try = prev
    return mtime != fail_mtime or now >= next_try


def watch(poll_seconds: float = 2.0, log=print) -> None:
    """Poll inbox/scripts for *.md and render each. Loads the engine once (warm)."""
    p = paths()
    p.ensure_dirs()
    engine = get_engine(voice_config())
    log(f"[watch] engine={engine.name}  watching {p.inbox_scripts}")
    failures: dict[str, _Failure] = {}
    while True:
        now = time.monotonic()
        for script in sorted(p.inbox_scripts.glob("*.md")):
            key = script.name
            try:
                mtime = script.stat().st_mtime
            except OSError:
                continue  # vanished between glob and stat (moved/deleted); skip
            prev = failures.get(key)
            if not _is_due(prev, mtime, now):
                continue  # unchanged since it failed and still inside its backoff window
            try:
                result = render_script_file(script, engine, log=log)
                log(f"[watch] {result['status']}: {result.get('title')} "
                    f"({result.get('duration_sec', '?')}s)")
                failures.pop(key, None)
            except Exception as exc:  # noqa: BLE001 - keep the watcher alive
                count = prev[1] + 1 if prev and prev[0] == mtime else 1
                backoff = _retry_backoff(count)
                failures[key] = (mtime, count, time.monotonic() + backoff)
                if count == 1:  # log once per failure streak, not every retry
                    log(f"[watch] ERROR rendering {script.name}: {type(exc).__name__}: {exc}"
                        f"  (retrying in {int(backoff)}s unless edited)")
        time.sleep(poll_seconds)
