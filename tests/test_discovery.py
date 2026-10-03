"""Discovery history/schedule contracts; temporary DBs and no model calls."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from earworm import autogen, config, db, llm


def episode(slug, title, *, feed="default", description="A distinct mechanism."):
    db.upsert_episode(slug=slug, title=title, content_hash=slug, audio_path="/preview.mp3",
                      report_path=None, duration_sec=600, description=description, feed=feed)


def test_archive_keeps_old_episodes_but_not_failed_private_or_other_feed():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
        config.paths.cache_clear()
        db.init()
        episode("old-cables", "Cable repair fleet", description="Repair ships and shared physical corridors.")
        for n in range(85):
            episode(f"new-{n}", f"Later episode {n}")
        episode("import", "An unrelated guest feed", feed="essays")
        failed = db.add_topic("An unheard failed lead")
        db.mark_failed(failed, "research failed")
        private = db.add_topic("An unheard private preview")
        db.mark_running(private, "private-run")
        db.mark_done(private, "/private/report.md", "/private/script.md")
        db.add_topic("A future commitment")
        coverage = "\n".join(db.recent_coverage())
        assert "Cable repair fleet — Repair ships and shared physical corridors." in coverage
        assert "An unrelated guest feed" not in coverage
        assert "An unheard failed lead" not in coverage
        assert "An unheard private preview" not in coverage
        assert "A future commitment" in coverage
        assert "pending" in coverage and "not rendered" in coverage
    config.paths.cache_clear()


def test_recent_window_and_queue_are_separate_and_in_actual_order():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
        config.paths.cache_clear()
        db.init()
        for n in range(12):
            episode(f"run-{n}", f"Rendered {n}")
        with db.connect() as conn:
            for n in range(12):
                conn.execute("UPDATE episodes SET created_at=? WHERE slug=?", (f"2026-09-{n+1:02d}T12:00:00Z", f"run-{n}"))
        episode("other", "Ignore other feed", feed="guest")
        source = db.add_topic("Anthropic paper behind an opaque title")
        db.mark_running(source, "run-11")
        db.mark_done(source, "/report.md", "/script.md")
        db.add_topic("Older ordinary topic")
        db.add_topic("Urgent topic", priority=1)
        db.add_topic("Newer ordinary topic")
        running = db.add_topic("Work already running")
        db.mark_running(running, "running")
        failed = db.add_topic("Failure is not an episode")
        db.mark_failed(failed, "failed")
        context = db.discovery_context()
        history = context["recent_episodes"]
        queue = context["queued_topics"]
        assert "Rendered 0 —" not in history and "Rendered 1 —" not in history
        assert history.index("Rendered 2 —") < history.index("Rendered 11 —")
        assert history.count("episode #") == 10
        assert "Anthropic paper behind an opaque title" in history
        assert "Ignore other feed" not in history
        assert "Older ordinary topic" not in history
        assert queue.index("Work already running") < queue.index("Urgent topic") < queue.index("Older ordinary topic") < queue.index("Newer ordinary topic")
        assert "Failure is not an episode" not in history + queue
    config.paths.cache_clear()


def test_watched_scripts_are_upcoming_but_private_or_rendered_scripts_are_not():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
        config.paths.cache_clear()
        db.init()
        p = config.paths()
        for slug, title, folder, feed in (
            ("b-staged", "Second staged", p.inbox_scripts, "default"),
            ("a-staged", "First staged", p.inbox_scripts, "default"),
            ("private", "Private preview", p.runs, "default"),
            ("guest", "Guest reading", p.inbox_scripts, "guest"),
            ("rendered", "Already rendered", p.inbox_scripts, "default"),
        ):
            tid = db.add_topic(title)
            script_path = folder / f"{slug}.md"
            script_path.write_text(f"---\ntitle: {title}\nfeed: {feed}\n---\n\nSpoken prose.")
            db.mark_running(tid, slug)
            db.mark_done(tid, "/report.md", str(script_path))
        episode("rendered", "Already rendered")
        running = db.add_topic("Running work")
        db.mark_running(running, "running")
        db.add_topic("Urgent pending", priority=3)
        coverage = "\n".join(db.recent_coverage())
        queue = db.discovery_context()["queued_topics"]
        assert "First staged" in coverage and "Second staged" in coverage
        assert "Private preview" not in coverage + queue
        assert "Guest reading" not in coverage + queue
        assert "Already rendered" not in queue
        assert coverage.count("Already rendered") == 1
        assert queue.index("First staged") < queue.index("Second staged") < queue.index("Running work") < queue.index("Urgent pending")
    config.paths.cache_clear()


def test_discovery_receives_schedule_while_dedup_receives_full_archive():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
        config.paths.cache_clear()
        db.init()
        p = config.paths()
        (p.root / "prompts").mkdir(exist_ok=True)
        source = Path(__file__).resolve().parent.parent / "prompts"
        for name in ("autogen.md", "dedup.md", "dedup_confirm.md"):
            (p.prompts / name).write_text((source / name).read_text())
        episode("old", "An archived explanation")
        db.add_topic("Queued explanation", priority=1)
        calls = []
        def fake(prompt, **kwargs):
            calls.append((kwargs["stage"], prompt))
            if kwargs["stage"] == "autogen":
                assert "{{" not in prompt
                assert "priority=1" in prompt
                assert "Recent main-feed episodes — oldest to newest" in prompt
                assert "An archived explanation" in prompt
                return "TOPIC: A different phenomenon"
            assert "An archived explanation" in prompt
            assert "Queued explanation" in prompt
            assert "Recent main-feed episodes" not in prompt
            return '{"decisions":[{"n":1,"matches":[],"reason":"Distinct phenomenon"}]}'
        with patch.object(llm, "run_text", fake):
            assert autogen.generate(count=1) == ["A different phenomenon"]
        assert [stage for stage, _ in calls] == ["autogen", "dedup"]
    config.paths.cache_clear()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"{len(tests)} passed")
