"""One-off: re-render every episode in the ledger so an updated normalizer or
lexicon (new pronunciations, say-as rules, pacing tweaks) lands in the audio. The
script BODIES are unchanged, so content-hash idempotency would skip them; we delete
the stale mp3/vtt first to force a fresh render.

Each render reuses the episode's stable guid, so publishing overwrites the same R2
object + feed row — no duplicates. Requires the archived scripts in done/scripts/.

Usage: uv run python scripts/rerender_canonical.py
"""
import shutil
import sqlite3
import warnings
from pathlib import Path

warnings.simplefilter("ignore")

from earworm import render
from earworm.config import paths, voice_config
from earworm.tts import get_engine

p = paths()
p.ensure_dirs()

con = sqlite3.connect(p.db)
con.row_factory = sqlite3.Row
slugs = [r["slug"] for r in con.execute("SELECT slug FROM episodes ORDER BY slug")]
con.close()

engine = get_engine(voice_config())
print(f"engine={engine.name}  episodes={len(slugs)}\n", flush=True)

ok = fail = 0
for i, slug in enumerate(slugs, 1):
    src = p.done_scripts / f"{slug}.md"
    if not src.exists():
        print(f"[{i}/{len(slugs)}] MISSING script: {slug}", flush=True)
        fail += 1
        continue
    staged = p.inbox_scripts / f"{slug}.md"
    shutil.copy2(src, staged)
    # force a fresh render: drop the stale audio so the idempotency check falls through
    (p.episodes / f"{slug}.mp3").unlink(missing_ok=True)
    (p.episodes / f"{slug}.vtt").unlink(missing_ok=True)
    try:
        r = render.render_script_file(staged, engine, publish=True)
        url = r.get("audio_url", "(not published)")
        print(f"[{i}/{len(slugs)}] {r['status']}  {r.get('duration_sec','?')}s  {slug[:45]}\n      {url}", flush=True)
        ok += 1
    except Exception as exc:  # noqa: BLE001
        print(f"[{i}/{len(slugs)}] FAILED {slug}: {type(exc).__name__}: {exc}", flush=True)
        fail += 1

print(f"\ndone: {ok} rendered, {fail} failed", flush=True)
