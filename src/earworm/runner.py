"""`earworm run` — drain one pending topic through research -> review -> script via Claude Code.

Research call (web search) writes runs/<run_id>/report.md.
Review call reads the report and writes runs/<run_id>/review.md (adversarial pass).
Script call reads report + review and writes inbox/scripts/<slug>.md.
Script-review call reads the script and writes runs/<run_id>/script_review.md
(adversarial pass on audio/flow); a revision call then folds that feedback back
into the script in place. The renderer (earworm watch) picks up the script independently.
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Optional

from . import claude, db
from .config import paths

RESEARCH_TOOLS = ("WebSearch", "WebFetch", "Read", "Write", "Edit")
REVIEW_TOOLS = ("Read", "Write", "Edit")
SCRIPT_TOOLS = ("Read", "Write", "Edit")
SCRIPT_REVIEW_TOOLS = ("Read", "Write", "Edit")
SCRIPT_REVISE_TOOLS = ("Read", "Write", "Edit")


def slugify(text: str, maxlen: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:maxlen].strip("-") or "topic"


def run_one(topic_id: Optional[int] = None, *, model: Optional[str] = None) -> dict:
    """Process one topic. If topic_id is None, take the oldest pending item."""
    db.init()
    row = db.get_topic(topic_id) if topic_id is not None else db.next_pending()
    if row is None:
        raise RuntimeError(
            "no pending topics" if topic_id is None else f"topic {topic_id} not found"
        )
    if row["status"] not in ("pending", "failed"):
        raise RuntimeError(f"topic {row['id']} is '{row['status']}', not runnable")

    tid = int(row["id"])
    topic = row["topic"]
    today = date.today().isoformat()
    slug = slugify(topic)
    run_id = f"{today}-{tid:04d}-{slug}"

    p = paths()
    p.ensure_dirs()
    run_dir = p.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.md"
    review_path = run_dir / "review.md"
    script_review_path = run_dir / "script_review.md"
    # The script is generated and revised in the run dir (staging), then moved
    # into inbox/scripts/ atomically at the very end. Writing it to inbox before
    # the revision pass finished let a concurrent `earworm watch` render the
    # intermediate version, then render the revised version as a second episode.
    staged_script = run_dir / "script.md"
    script_path = p.inbox_scripts / f"{run_id}.md"

    def _has_content(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    db.mark_running(tid, run_id)
    try:
        # 1. Research -> report.md (skip if a prior run already produced it)
        if _has_content(report_path):
            pass
        else:
            research_prompt = claude.render_prompt(
                p.prompts / "research.md",
                topic=topic,
                date=today,
                report_path=str(report_path),
            )
            claude.run(
                research_prompt,
                cwd=p.root,
                allowed_tools=RESEARCH_TOOLS,
                expect_file=report_path,
                timeout=1800,
                model=model,
            )

        # 2. Adversarial review -> review.md (skip if a prior run already produced it).
        #    Makes the report smarter/more honest; handed to the script-writer as context.
        if not _has_content(review_path):
            review_prompt = claude.render_prompt(
                p.prompts / "review.md",
                report_path=str(report_path),
                review_path=str(review_path),
            )
            claude.run(
                review_prompt,
                cwd=p.root,
                allowed_tools=REVIEW_TOOLS,
                expect_file=review_path,
                timeout=900,
                model=model,
            )

        # 3. Script -> runs/<run_id>/script.md (reads report + review)
        script_prompt = claude.render_prompt(
            p.prompts / "script.md",
            date=today,
            report_path=str(report_path),
            review_path=str(review_path),
            script_path=str(staged_script),
            slug=run_id,
        )
        claude.run(
            script_prompt,
            cwd=p.root,
            allowed_tools=SCRIPT_TOOLS,
            expect_file=staged_script,
            timeout=900,
            model=model,
        )

        # 4. Script review -> runs/<run_id>/script_review.md (adversarial pass on
        #    how the script will SOUND). Skip if a prior run already produced it.
        if not _has_content(script_review_path):
            script_review_prompt = claude.render_prompt(
                p.prompts / "script_review.md",
                script_path=str(staged_script),
                script_review_path=str(script_review_path),
            )
            claude.run(
                script_review_prompt,
                cwd=p.root,
                allowed_tools=SCRIPT_REVIEW_TOOLS,
                expect_file=script_review_path,
                timeout=900,
                model=model,
            )

        # 5. Revision pass -> rewrites the staged script in place, folding in the
        #    script-review feedback. Only after this completes is the script moved
        #    into inbox/scripts/ (step 6), so the watcher renders it exactly once.
        script_revise_prompt = claude.render_prompt(
            p.prompts / "script_revise.md",
            script_path=str(staged_script),
            script_review_path=str(script_review_path),
        )
        claude.run(
            script_revise_prompt,
            cwd=p.root,
            allowed_tools=SCRIPT_REVISE_TOOLS,
            expect_file=staged_script,
            timeout=900,
            model=model,
        )

        # 6. Atomically expose the finished script to the watcher. os.replace is
        #    an atomic rename within the same filesystem, so `earworm watch` never
        #    observes a half-written or pre-revision file.
        os.replace(staged_script, script_path)
    except Exception as exc:  # noqa: BLE001 - record failure, re-raise for CLI
        db.mark_failed(tid, f"{type(exc).__name__}: {exc}")
        raise

    db.mark_done(tid, str(report_path), str(script_path))
    return {
        "topic_id": tid,
        "topic": topic,
        "run_id": run_id,
        "report_path": str(report_path),
        "script_path": str(script_path),
    }
