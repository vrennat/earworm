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

from mutagen.id3 import COMM, ID3, TALB, TCON, TDRC, TIT2, TLEN, TPE1
from mutagen.mp3 import MP3

from . import db, feed, shownotes, transcript
from .config import paths, show_config, voice_config
from .frontmatter import parse
from .tts import TTSEngine, get_engine


def content_hash(body: str) -> str:
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()[:16]


def _tag(mp3_path: Path, *, title: str, date: str, notes: str, duration_sec: float) -> None:
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
    chash = content_hash(body)
    audio_path = p.episodes / f"{slug}.mp3"

    # Idempotent on episode identity (the slug), not the body hash. An identical
    # re-drop whose audio still exists is skipped. A *changed* re-render of the
    # same slug falls through and REPLACES the episode in place (reusing the
    # stable guid -> same R2 key + feed row), so it never produces a duplicate.
    existing = db.get_episode_by_slug(slug)
    if existing and existing["content_hash"] == chash and audio_path.exists():
        dest = p.done_scripts / script_path.name
        if script_path.resolve() != dest.resolve():
            shutil.move(str(script_path), str(dest))
        return {"status": "skipped_duplicate", "slug": slug, "title": title}

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
            )
            db.mark_published(guid, audio_url, transcript_url)
            published += 1
            log(f"[publish] {r['slug']} -> {audio_url}")
        except Exception as exc:  # noqa: BLE001
            log(f"[publish] FAILED {r['slug']}: {type(exc).__name__}: {exc}")
    return published


def watch(poll_seconds: float = 2.0, log=print) -> None:
    """Poll inbox/scripts for *.md and render each. Loads the engine once (warm)."""
    p = paths()
    p.ensure_dirs()
    engine = get_engine(voice_config())
    log(f"[watch] engine={engine.name}  watching {p.inbox_scripts}")
    seen_failures: set[str] = set()
    while True:
        for script in sorted(p.inbox_scripts.glob("*.md")):
            key = f"{script.name}"
            try:
                result = render_script_file(script, engine, log=log)
                log(f"[watch] {result['status']}: {result.get('title')} "
                    f"({result.get('duration_sec', '?')}s)")
                seen_failures.discard(key)
            except Exception as exc:  # noqa: BLE001 - keep the watcher alive
                if key not in seen_failures:
                    log(f"[watch] ERROR rendering {script.name}: {type(exc).__name__}: {exc}")
                    seen_failures.add(key)
        time.sleep(poll_seconds)
