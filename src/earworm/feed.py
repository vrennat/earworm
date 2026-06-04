"""Publish side of the renderer: upload audio to R2, register the episode with
the feed Worker. Deterministic, no LLM. Idempotent — re-publishing the same
episode overwrites the same R2 object and upserts the same Worker row (keyed on
the episode's stable guid, which is reused across re-renders).

Auth model (per project decisions): audio lives in a public R2 bucket under an
unguessable key; the app fetches it directly. Uploads go through `wrangler r2
object put` (wrangler OAuth). Episode metadata is POSTed to the Worker with a
shared secret.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .config import feed_config, paths, secrets


class PublishError(RuntimeError):
    pass


def is_configured() -> tuple[bool, str]:
    """Return (ok, reason). Publishing is skipped (not failed) when not configured."""
    cfg = feed_config()
    if not cfg.get("enabled"):
        return False, "feed disabled (config/feed.toml: enabled=false)"
    for key in ("worker_url", "public_audio_base", "bucket", "account_id"):
        if not cfg.get(key):
            return False, f"feed config missing '{key}'"
    if not secrets().get("ingest_secret"):
        return False, "missing ingest_secret (config/secrets.toml or EARWORM_INGEST_SECRET)"
    return True, "ok"


def _object_key(slug: str, guid: str, ext: str) -> str:
    """Unguessable but stable key: derived from the episode's stable guid salted
    with the feed token, so re-renders of the same episode overwrite the same
    object (no orphans) while the path stays unguessable without the secret.
    Audio and transcript share the token dir.
    """
    cfg = feed_config()
    prefix = cfg.get("audio_key_prefix", "audio").strip("/")
    salt = secrets().get("feed_token", "")
    token = hashlib.sha256(f"{guid}:{salt}".encode()).hexdigest()[:24]
    return f"{prefix}/{token}/{slug}.{ext}"


def _wrangler() -> list[str]:
    """Prefer the worker's pinned wrangler binary; fall back to bunx. Re-resolving
    via bunx on every call is slow and has caused transient connectivity errors.
    """
    local = paths().root / "worker" / "node_modules" / ".bin" / "wrangler"
    return [str(local)] if local.exists() else ["bunx", "wrangler"]


def _r2_put(local_path: Path, key: str, content_type: str, attempts: int = 3) -> str:
    """Upload a file to R2 via wrangler, retrying transient errors. Returns the public URL."""
    cfg = feed_config()
    env = {**os.environ, "CLOUDFLARE_ACCOUNT_ID": cfg["account_id"]}
    cf_token = secrets().get("cf_api_token")
    if cf_token:
        env["CLOUDFLARE_API_TOKEN"] = cf_token

    cmd = [
        *_wrangler(), "r2", "object", "put",
        f"{cfg['bucket']}/{key}",
        "--file", str(local_path),
        "--content-type", content_type,
        "--remote",
    ]
    last = ""
    for i in range(attempts):
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            return f"{cfg['public_audio_base'].rstrip('/')}/{key}"
        last = (proc.stderr or proc.stdout)[-1000:]
        if i < attempts - 1:
            time.sleep(2 * (i + 1))
    raise PublishError(f"r2 upload failed after {attempts} attempts: {last}")


def register_episode(payload: dict) -> dict:
    """POST episode metadata to the Worker's /episodes endpoint."""
    cfg = feed_config()
    secret = secrets()["ingest_secret"]
    url = cfg["worker_url"].rstrip("/") + "/episodes"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {secret}",
            # Cloudflare's edge blocks the default Python-urllib UA (error 1010).
            "user-agent": "earworm-renderer/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise PublishError(f"register failed ({e.code}): {e.read().decode()[:500]}")
    except urllib.error.URLError as e:
        raise PublishError(f"register failed: {e.reason}")


def publish(
    *,
    guid: str,
    slug: str,
    title: str,
    description: str,
    audio_path: Path,
    duration_sec: float,
    transcript_path: Optional[Path] = None,
    pub_date: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Upload audio (+ transcript) and register the episode. Returns (audio_url, transcript_url).

    `guid` is the episode's stable feed identity, so this is safe to retry and a
    re-render overwrites the same object + upserts the same feed row (no dupes).
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise PublishError(f"audio file missing: {audio_path}")

    audio_url = _r2_put(audio_path, _object_key(slug, guid, "mp3"), "audio/mpeg")

    transcript_url: Optional[str] = None
    if transcript_path and Path(transcript_path).exists():
        transcript_url = _r2_put(
            Path(transcript_path), _object_key(slug, guid, "vtt"), "text/vtt"
        )

    register_episode(
        {
            "guid": guid,
            "slug": slug,
            "title": title,
            "description": description or "",
            "audio_url": audio_url,
            "audio_bytes": audio_path.stat().st_size,
            "duration_sec": int(round(duration_sec)),
            "transcript_url": transcript_url,
            "pub_date": pub_date,  # Worker defaults to now() if null
        }
    )
    return audio_url, transcript_url
