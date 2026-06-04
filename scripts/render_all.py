"""One-off: render + publish every script currently in inbox/scripts with a
single warm engine.

Rendering is idempotent on episode identity (slug): an unchanged script is
skipped, a changed one REPLACES its episode in place (same stable guid -> same
R2 object + feed row). Do NOT wipe the local ledger — it holds the slug->guid
map that keeps re-renders from duplicating in the feed.

Usage: python scripts/render_all.py
"""
from earworm import render
from earworm.config import paths, voice_config
from earworm.tts import get_engine

p = paths()
p.ensure_dirs()

engine = get_engine(voice_config())
print(f"engine={engine.name}\n")

results = []
for script in sorted(p.inbox_scripts.glob("*.md")):
    r = render.render_script_file(script, engine, publish=True)
    results.append(r)
    dur = r.get("duration_sec", "?")
    url = r.get("audio_url", "(not published)")
    print(f"[{r['status']}] {r.get('title')}  ({dur}s)\n   {url}\n")

print(f"\nrendered {len(results)} episode(s)")
