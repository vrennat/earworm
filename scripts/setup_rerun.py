"""One-off: queue the 6 overhaul topics and pre-seed reports for the 4 reuse ones.

For reuse topics we copy an existing report into the new run dir so run_one()
skips research and goes straight to review -> script. Full-pipeline topics get
no seed (research runs fresh). Prints a topic_id -> run_id map.

Usage: python scripts/setup_rerun.py
"""
import shutil
from datetime import date

from earworm import db
from earworm.config import paths
from earworm.runner import slugify

TODAY = "2026-06-01"  # pin run_id date for consistency with the other 2026-06-01 runs
p = paths()
p.ensure_dirs()
db.init()

# (topic, reuse_report_path or None for full pipeline)
TOPICS = [
    ("The Science of Societal Collapse",
     p.done_reports / "2026-05-31-ep01-the-science-of-societal-collapse.report.md"),
    ("AI, Labor Displacement, and the Risk of US Destabilization",
     p.done_reports / "2026-05-31-ep02-ai-labor-destabilization.report.md"),
    ("The Commander Bracket System, One Year In",
     p.done_reports / "2026-06-01-0004-the-commander-bracket-system-one-year-in-did-wotcs-official.report.md"),
    ("Cloudflare Durable Objects in 2026",
     p.done_reports / "2026-06-01-0003-cloudflare-durable-objects-in-2026-has-the-sqlite-backed-sto.report.md"),
    ("What's happening in MTG Standard heading into summer 2026", None),
    ("Agent orchestration patterns after the hype", None),
]

for topic, reuse in TOPICS:
    tid = db.add_topic(topic, source="manual")
    slug = slugify(topic)
    run_id = f"{TODAY}-{tid:04d}-{slug}"
    run_dir = p.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    kind = "FULL"
    if reuse is not None:
        if not reuse.exists():
            raise SystemExit(f"reuse report missing: {reuse}")
        shutil.copy2(reuse, run_dir / "report.md")
        kind = "REUSE"
    print(f"#{tid:>3} [{kind:5}] run_id={run_id}")
