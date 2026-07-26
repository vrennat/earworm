"""One-off: regenerate a single episode script from its existing report.md using
the current prompts/script.md — without paying for another research pass. Handy
after you tune the script prompt and want to re-roll the writing on a report you
already have.

Reuses earworm's headless-claude wrapper and the `script` stage's tool allowlist,
so the call matches what `earworm run` does for that pass.

Usage: uv run python scripts/regen_script.py <slug> <report_path> [--date YYYY-MM-DD] [--model NAME]
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from earworm import claude
from earworm.config import paths
from earworm.pipeline import RunContext, stage_by_name


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate one script from its report.")
    ap.add_argument("slug", help="episode slug (the inbox/scripts/<slug>.md stem)")
    ap.add_argument("report_path", help="path to the existing report.md")
    ap.add_argument("--date", default=date.today().isoformat(), help="episode date for front-matter")
    ap.add_argument("--model", default=None, help="override the Claude model")
    args = ap.parse_args()

    p = paths()
    p.ensure_dirs()
    report = Path(args.report_path).expanduser().resolve()
    if not report.exists():
        ap.error(f"no such report: {report}")
    script_path = p.inbox_scripts / f"{args.slug}.md"

    # Fold in an adjacent review.md if one sits next to the report.
    review = report.parent / "review.md"
    review_section = (
        f"If a review exists at {review}, read that too — it flags weak spots and "
        "missed angles. Address them where you can; acknowledge uncertainty where you can't."
        if review.exists()
        else ""
    )

    # Build the stage's own vars (voice rules, assigned macro structure, the
    # cross-episode AVOID block) rather than hand-listing them here — a prompt
    # variable added to script.md must not silently render as literal braces.
    # The slug carries the topic id, so the macro structure matches what the
    # original run would have been assigned.
    stage = stage_by_name("script")
    ctx = RunContext(
        root=p.root,
        prompts=p.prompts,
        runs=p.runs,
        inbox_scripts=p.inbox_scripts,
        run_id=args.slug,
        topic=args.slug,
        date=args.date,
        review_enabled=review.exists(),
    )
    prompt_vars = stage.build_vars(ctx)
    # This run's report and output live outside the usual run_dir layout.
    prompt_vars["report_path"] = str(report)
    prompt_vars["review_section"] = review_section
    prompt_vars["script_path"] = str(script_path)

    prompt = claude.render_prompt(p.prompts / stage.prompt_file, **prompt_vars)
    claude.run(
        prompt,
        cwd=p.root,
        allowed_tools=stage.allowed_tools,
        expect_file=script_path,
        timeout=900,
        model=args.model,
    )
    print(f"wrote {script_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
