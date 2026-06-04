"""Auto-topic generator (Phase 3). Reads interests.md and recent topics/episodes,
asks Claude Code for fresh topics, and queues them with source='auto'.

One half of the two-producer queue (the other is `earworm add`). The runner drains
the queue without caring where an item came from.
"""
from __future__ import annotations

from datetime import date

from . import claude, db
from .config import paths


def recent_titles(limit: int = 40) -> list[str]:
    """Episode titles + queued topics, to steer the generator away from repeats."""
    seen: list[str] = []
    with db.connect() as conn:
        for r in conn.execute(
            "SELECT title FROM episodes WHERE title IS NOT NULL ORDER BY id DESC LIMIT ?",
            (limit,),
        ):
            seen.append(r["title"])
        for r in conn.execute(
            "SELECT topic FROM topics ORDER BY id DESC LIMIT ?", (limit,)
        ):
            seen.append(r["topic"])
    return seen


def generate(count: int = 3, model: str | None = None) -> list[str]:
    """Propose and queue `count` fresh auto topics. Returns the topics added."""
    db.init()
    p = paths()
    interests = p.interests.read_text() if p.interests.exists() else ""
    recent = recent_titles()

    prompt = claude.render_prompt(
        p.prompts / "autogen.md",
        date=date.today().isoformat(),
        n=str(count),
        interests=interests.strip() or "(no interests file)",
        recent="\n".join(f"- {t}" for t in recent) or "(nothing yet)",
    )
    text = claude.run_text(prompt, cwd=p.root, timeout=300, model=model)

    proposed = [line.strip().lstrip("-*0123456789. \t").strip() for line in text.splitlines()]
    seen = {t.lower() for t in recent}
    added: list[str] = []
    for topic in proposed:
        if not topic or topic.lower() in seen:
            continue
        db.add_topic(topic, source="auto")
        seen.add(topic.lower())
        added.append(topic)
    return added
