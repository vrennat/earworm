"""Auto-topic generator. Reads interests.md and what the show has already
covered, asks an API/local model for fresh topics — consulting live sources for timely
paper drops — screens them against past coverage, and queues the survivors.

One half of the two-producer queue (the other is `earworm add`). The runner drains
the queue without caring where an item came from.

Screening runs in two layers, because the failure that shipped a duplicate episode
slipped past a lexical-only check:
  1. lexical — `db.find_duplicate_topic` catches exact / casing / punctuation re-adds.
  2. semantic — `dedup.filter_new` catches the same idea worded differently.
Incomplete or malformed screening stops generation, as do provider, authorization,
and spending errors. Unscreened proposals must not enter the queue.
"""
from __future__ import annotations

import re
import sys
import time
from datetime import date

from . import llm, db, dedup, pipeline
from .config import paths, pipeline_config

# Live sources the discovery pass may consult so it can catch and fast-track a
# major paper the day it drops instead of proposing from a stale knowledge cutoff.
DISCOVERY_TOOLS = ("web_search", "web_fetch")

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
# The lane-rotation prompt (2026-09-21) makes the model tally recent coverage
# before proposing, and its first live run returned that working-out ahead of the
# topics. Filtering could not tell the notes from topics, so the `count` cap
# queued five lines of reasoning (#151-155) and the real topics, at the end of
# the response, never reached the queue. The prompt now asks for a `TOPIC:`
# marker on every topic line; when any line carries it, the parser selects the
# marked lines wherever they sit and ignores everything else. Responses without
# the marker keep the older filter-based path.
_TOPIC_TAG = re.compile(r"TOPIC\s*:\s*", re.IGNORECASE)


def _parse_proposals(text: str, count: int | None = None) -> list[tuple[str, int]]:
    """Turn the model's one-per-line output into (topic, priority) pairs, dropping
    the preamble/heading/citation lines the model wraps them in. When any line
    carries a `TOPIC:` marker, only marked lines are read. A line prefixed
    `PAPER:` (after the marker, if any) marks a timely paper drop worth fast-tracking; the marker is stripped
    and the topic gets `PAPER_PRIORITY`. `count` caps the result, as a backstop for
    commentary that slips past the filters above."""
    out: list[tuple[str, int]] = []
    lines = text.splitlines()
    marked = [m for m in (_TOPIC_TAG.search(line) for line in lines) if m]
    if marked:
        lines = [m.string[m.end():] for m in marked]
    for line in lines:
        raw = line.strip().lstrip("-*0123456789. \t").strip().strip("*").strip()
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
    `use_sources` lets the discovery pass consult the web for timely drops; a failed sourced pass stops so unsupported current-event
    guesses cannot enter the queue. Explicit --no-sources still permits ideation.
    """
    db.init()
    p = paths()
    interests = p.interests.read_text() if p.interests.exists() else ""
    coverage = db.recent_coverage()
    pool = count + _CANDIDATE_MARGIN

    prompt = llm.render_prompt(
        p.prompts / "autogen.md",
        date=date.today().isoformat(),
        n=str(pool),
        interests=interests.strip() or "(no interests file)",
        recent="\n".join(f"- {t}" for t in coverage) or "(nothing yet)",
    )

    # The backend owns the discovery route and any bounded transport fallback.
    cfg = pipeline.PipelineConfig.from_toml(pipeline_config())
    sc = cfg.for_stage("autogen")
    chosen = pipeline.resolve_model(model, sc.model, cfg.default_model)
    timeout = 300 if sc.timeout is None else sc.timeout
    ledger = p.runs / f"autogen-{time.time_ns()}" / "usage.jsonl"
    text = llm.run_text(
        prompt, cwd=p.root, timeout=timeout, model=chosen,
        allowed_tools=DISCOVERY_TOOLS if use_sources else None,
        stage="autogen", ledger_path=ledger,
    )

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
    # A separately configured route allows this bounded classification to run locally.
    candidates = list(priority_of)
    dedup_stage = cfg.for_stage("dedup")
    dedup_timeout = 180 if dedup_stage.timeout is None else dedup_stage.timeout
    judge = lambda prompt_text: llm.run_text(  # noqa: E731 - small closure, model fixed
        prompt_text, cwd=p.root, timeout=dedup_timeout, stage="dedup", ledger_path=ledger
    )
    try:
        kept, dropped = dedup.filter_new(
            candidates, coverage, judge=judge, prompt_path=p.prompts / "dedup.md"
        )
    except ValueError as exc:
        raise llm.LLMError("Incomplete duplicate screening; no proposals queued.") from exc
    for d in dropped:
        print(f"[autogen] skipped (semantic dup of {d.matches!r}): {d.candidate}", file=sys.stderr)

    added: list[str] = []
    for topic in kept:
        db.add_topic(topic, source="auto", priority=priority_of[topic])
        added.append(topic)
    return added
