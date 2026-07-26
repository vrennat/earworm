"""Auto-topic generator. Reads interests.md and what the show has already
covered, asks Claude Code for fresh topics — consulting live sources for timely
paper drops — screens them against past coverage, and queues the survivors.

One half of the two-producer queue (the other is `earworm add`). The runner drains
the queue without caring where an item came from.

Screening runs in two layers, because the failure that shipped a duplicate episode
slipped past a lexical-only check:
  1. lexical — `db.find_duplicate_topic` catches exact / casing / punctuation re-adds.
  2. semantic — `dedup.filter_new` catches the same idea worded differently.
The semantic pass fails open (a rare duplicate beats dropping every topic when the
judge misbehaves); the enriched generation context is the first line of defence.
"""
from __future__ import annotations

import re
import sys
from datetime import date

from . import claude, db, dedup, pipeline
from .config import paths, pipeline_config

# Live sources the discovery pass may consult so it can catch and fast-track a
# major paper the day it drops instead of proposing from a stale knowledge cutoff.
DISCOVERY_TOOLS = ("WebSearch", "WebFetch")

# Run-order weight for a timely, high-impact paper the discovery pass flags with a
# leading `PAPER:` marker, so it jumps ahead of evergreen topics. Manual queues can
# still outrank it with a higher `earworm add --priority`.
PAPER_PRIORITY = 1
_PAPER_TAG = re.compile(r"^paper\s*:\s*", re.IGNORECASE)

# Extra candidates requested beyond the caller's `count`, because the semantic
# dedup gate below is a lossy filter and asking for exactly N regularly yielded
# fewer than N — sometimes zero. With ~90 episodes covered, whole batches came
# back as "all overlapped recent", which left the queue dry and stalled the daily
# job for two days (every `earworm run` failing with "no pending topics"). A
# margin means normal attrition still clears the day's quota, and any surplus
# survivor is queued rather than discarded: it banks as a buffer that carries the
# next day when the judge rejects everything. Growth stays bounded because
# launchd/daily.sh only autogens the shortfall when the queue is below quota.
_CANDIDATE_MARGIN = 3

# The prompt asks for bare topics and nothing else, but the model still wraps them
# in chat furniture — a "here are 3 topics:" preamble, a trailing "Sources:" heading,
# a citation list. Those lines used to parse as topics and reach the queue, where a
# research agent handed "Sources:" would invent a subject rather than fail, and the
# invention shipped as a real episode. Anything the prompt can't reliably suppress
# has to be dropped here instead.
#
# A heading or preamble announces what follows and ends in a colon; a self-contained
# topic never does.
_COMMENTARY = re.compile(r":\s*$")
# A line that is nothing but a markdown link is a citation from the sources list,
# not a topic — even when its title text reads like one.
_BARE_LINK = re.compile(r"^\[[^\]]*\]\([^)]*\)$")


def _parse_proposals(text: str, count: int | None = None) -> list[tuple[str, int]]:
    """Turn the model's one-per-line output into (topic, priority) pairs, dropping
    the preamble/heading/citation lines the model wraps them in. A line prefixed
    `PAPER:` marks a timely paper drop worth fast-tracking; the marker is stripped
    and the topic gets `PAPER_PRIORITY`. `count` caps the result, as a backstop for
    commentary that slips past the filters above."""
    out: list[tuple[str, int]] = []
    for line in text.splitlines():
        raw = line.strip().lstrip("-*0123456789. \t").strip()
        if not raw:
            continue
        priority = 0
        m = _PAPER_TAG.match(raw)
        if m:
            raw = raw[m.end():].strip()
            priority = PAPER_PRIORITY
        if not raw or _COMMENTARY.search(raw) or _BARE_LINK.match(raw):
            continue
        out.append((raw, priority))
    return out[:count] if count else out


def generate(count: int = 3, model: str | None = None, *, use_sources: bool = True) -> list[str]:
    """Propose, screen, and queue fresh auto topics for a quota of `count`.

    Asks the model for `count + _CANDIDATE_MARGIN` candidates so the lossy dedup
    gate still clears the quota, and queues every survivor — so the result can
    exceed `count`, banking the surplus for a later day when the judge rejects
    everything. Returns the topics actually added (after lexical + semantic dedup).
    `use_sources` lets the discovery pass consult the web for timely drops; it
    falls back to pure ideation if the sourced pass fails, so autogen still
    produces topics offline.
    """
    db.init()
    p = paths()
    interests = p.interests.read_text() if p.interests.exists() else ""
    coverage = db.recent_coverage()
    pool = count + _CANDIDATE_MARGIN

    prompt = claude.render_prompt(
        p.prompts / "autogen.md",
        date=date.today().isoformat(),
        n=str(pool),
        interests=interests.strip() or "(no interests file)",
        recent="\n".join(f"- {t}" for t in coverage) or "(nothing yet)",
    )

    # autogen is one-shot generation, but it gets the same model + retry treatment
    # as the pipeline stages, keyed `[pipeline.autogen]`.
    cfg = pipeline.PipelineConfig.from_toml(pipeline_config())
    sc = cfg.for_stage("autogen")
    chosen = pipeline.resolve_model(model, sc.model, cfg.default_model)
    retries = cfg.default_retries if sc.retries is None else sc.retries
    timeout = 300 if sc.timeout is None else sc.timeout

    def _discover(tools: tuple[str, ...] | None) -> str:
        return pipeline.with_retry(
            lambda m: claude.run_text(
                prompt, cwd=p.root, timeout=timeout, model=m, allowed_tools=tools
            ),
            model=chosen,
            retries=retries,
            fallback_model=sc.fallback_model,
        )

    try:
        text = _discover(DISCOVERY_TOOLS if use_sources else None)
    except pipeline.RETRYABLE:
        if not use_sources:
            raise
        print(
            "[autogen] source-aware discovery failed; falling back to ideation",
            file=sys.stderr,
        )
        text = _discover(None)

    proposals = _parse_proposals(text, pool)

    # Layer 1 — lexical: drop exact / punctuation / casing re-adds of anything
    # already queued, and collapse duplicates within this batch.
    priority_of: dict[str, int] = {}
    seen_keys: set[str] = set()
    for topic, priority in proposals:
        key = db.normalize_topic(topic)
        if not key or key in seen_keys or db.find_duplicate_topic(topic) is not None:
            continue
        seen_keys.add(key)
        priority_of[topic] = priority

    # Layer 2 — semantic: drop topics that repeat past coverage in different words.
    # Reuses the autogen model as the judge; fails open so a flaky judge never
    # blocks the queue (the lexical pass + enriched context still apply).
    candidates = list(priority_of)
    judge = lambda prompt_text: claude.run_text(  # noqa: E731 - small closure, model fixed
        prompt_text, cwd=p.root, timeout=timeout, model=chosen
    )
    try:
        kept, dropped = dedup.filter_new(
            candidates, coverage, judge=judge, prompt_path=p.prompts / "dedup.md"
        )
    except pipeline.RETRYABLE + (ValueError,):
        print(
            "[autogen] semantic dedup unavailable; keeping lexically-clean topics",
            file=sys.stderr,
        )
        kept, dropped = candidates, []
    for d in dropped:
        print(f"[autogen] skipped (semantic dup of {d.matches!r}): {d.candidate}", file=sys.stderr)

    added: list[str] = []
    for topic in kept:
        db.add_topic(topic, source="auto", priority=priority_of[topic])
        added.append(topic)
    return added
