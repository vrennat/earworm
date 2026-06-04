"""One-off: regenerate a single episode script from its existing report.md using
the current prompts/script.md (the --script-only path the CLI doesn't expose).
Reuses earworm's headless-claude wrapper so the call is identical to `earworm run`.

Usage: python scripts/regen_script.py <slug> <report_path>
"""
import sys
from datetime import date
from pathlib import Path

from earworm import claude
from earworm.config import paths
from earworm.runner import SCRIPT_TOOLS

slug, report_path = sys.argv[1], sys.argv[2]
p = paths()
p.ensure_dirs()
script_path = p.inbox_scripts / f"{slug}.md"

prompt = claude.render_prompt(
    p.prompts / "script.md",
    date="2026-05-31",  # preserve original episode date for ID3 consistency
    report_path=str(Path(report_path).resolve()),
    script_path=str(script_path),
    slug=slug,
)
claude.run(
    prompt,
    cwd=p.root,
    allowed_tools=SCRIPT_TOOLS,
    expect_file=script_path,
    timeout=900,
)
print(f"wrote {script_path}")
