"""`earworm run` — drain one pending topic through the generation pipeline.

The pipeline shape lives in `pipeline.py` (research -> review -> script ->
script-review -> revise, each a Claude Code pass). This module is pure
orchestration: pick a topic, build the run context, drive the active stages
through the executor (per-stage model + retry + fallback), atomically expose the
finished script to the renderer, and record status in the queue db.
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Optional

from . import db, pipeline
from .config import paths, pipeline_config


def slugify(text: str, maxlen: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:maxlen].strip("-") or "topic"


def _has_content(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def run_one(topic_id: Optional[int] = None, *, model: Optional[str] = None) -> dict:
    """Process one topic. If topic_id is None, take the oldest pending item.

    `model` is the CLI --model override: when set it forces the primary model for
    every stage (per-stage config still supplies fallbacks). When None, each stage
    uses its configured model or the pipeline default.
    """
    db.init()
    if topic_id is not None:
        row = db.get_topic(topic_id)
        if row is None:
            raise RuntimeError(f"topic {topic_id} not found")
        if row["status"] not in ("pending", "failed"):
            raise RuntimeError(f"topic {row['id']} is '{row['status']}', not runnable")
        if not db.claim_topic(int(row["id"])):
            raise RuntimeError(f"topic {row['id']} was claimed by a concurrent run")
    else:
        row = db.claim_next_pending()
        if row is None:
            raise RuntimeError("no pending topics")

    tid = int(row["id"])
    topic = row["topic"]
    today = date.today().isoformat()
    run_id = f"{today}-{tid:04d}-{slugify(topic)}"

    p = paths()
    p.ensure_dirs()
    cfg = pipeline.PipelineConfig.from_toml(pipeline_config())
    stages = pipeline.active_stages(cfg)
    ctx = pipeline.RunContext(
        root=p.root,
        prompts=p.prompts,
        runs=p.runs,
        inbox_scripts=p.inbox_scripts,
        run_id=run_id,
        topic=topic,
        date=today,
        # The script prompt only folds in a review when the review pass is active.
        review_enabled=any(s.name == "review" for s in stages),
    )
    ctx.run_dir.mkdir(parents=True, exist_ok=True)

    # The claim above already flipped status; this backfills the run_id.
    db.mark_running(tid, run_id)
    try:
        for stage in stages:
            # skip_if_exists stages resume from a prior partial run; script + revise
            # always re-run so a re-queued topic gets a fresh script.
            if stage.skip_if_exists and _has_content(stage.expect_file(ctx)):
                continue
            pipeline.run_stage(stage, ctx, cfg, cli_model=model)

        # Atomically expose the finished (revised) script to the watcher. os.replace
        # is an atomic rename within the filesystem, so `earworm watch` never sees a
        # half-written or pre-revision file.
        os.replace(ctx.staged_script, ctx.script_path)
    except Exception as exc:  # noqa: BLE001 - record failure, re-raise for CLI
        db.mark_failed(tid, f"{type(exc).__name__}: {exc}")
        raise

    db.mark_done(tid, str(ctx.report_path), str(ctx.script_path))
    return {
        "topic_id": tid,
        "topic": topic,
        "run_id": run_id,
        "report_path": str(ctx.report_path),
        "script_path": str(ctx.script_path),
    }
