"""Regenerate an unpublished script from a checked report using current prompts.

The output remains in its run directory unless --stage explicitly exposes it to
Earworm's watcher. No research is rerun and no Claude account is used.
"""
from __future__ import annotations

import argparse
import os
import shutil
from datetime import date
from pathlib import Path

from earworm.config import paths, pipeline_config
from earworm.pipeline import PipelineConfig, RunContext, run_stage, stage_by_name


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate one script from its report.")
    ap.add_argument("slug", help="episode slug")
    ap.add_argument("report_path", help="path to the existing report.md")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--model", default=None, help="override the configured API/local model")
    ap.add_argument("--stage", action="store_true", help="expose the result to the live renderer")
    args = ap.parse_args()
    if Path(args.slug).name != args.slug or args.slug in {".", ".."}:
        ap.error("slug must be a single filename stem")
    p = paths()
    p.ensure_dirs()
    report = Path(args.report_path).expanduser().resolve()
    if not report.is_file():
        ap.error(f"no such report: {report}")
    review = report.parent / "review.md"
    ctx = RunContext(root=p.root, prompts=p.prompts, runs=p.runs,
                     inbox_scripts=p.inbox_scripts, run_id=args.slug, topic=args.slug,
                     date=args.date, review_enabled=review.exists())
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    if report != ctx.report_path.resolve():
        shutil.copy2(report, ctx.report_path)
    if review.exists() and review.resolve() != ctx.review_path.resolve():
        shutil.copy2(review, ctx.review_path)
    cfg = PipelineConfig.from_toml(pipeline_config())
    for name in ("script", "script_review", "revise"):
        if name != "script" and not cfg.for_stage("script_review").enabled:
            continue
        run_stage(stage_by_name(name), ctx, cfg, cli_model=args.model)
    output = ctx.staged_script
    if args.stage:
        os.replace(output, ctx.script_path)
        output = ctx.script_path
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
