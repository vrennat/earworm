"""Regression checks for batch failures and per-ingestion spend boundaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from earworm import cli, config, db, ingest, llm, render, runner


def _fetch_result(kwargs, url, text, **overrides):
    artifacts = kwargs["ledger_path"].parent / "llm-artifacts" / "ingest-fetch-test"
    cache = artifacts / "source-cache"
    cache.mkdir(parents=True, exist_ok=True)
    record = {"kind": "fetch", "url": url, "extraction_complete": True, "text": text}
    record.update(overrides)
    (cache / "source.json").write_text(json.dumps(record))
    kwargs["expect_file"].write_text("The source was retrieved.")
    return {"artifacts_path": str(artifacts), "result": "The source was retrieved."}


def _ingest_prompts(p):
    (p.root / "prompts").mkdir(parents=True)
    source = Path(__file__).resolve().parent.parent / "prompts"
    for name in ("ingest.md", "ingest_fetch.md"):
        (p.prompts / name).write_text((source / name).read_text())


def test_batch_config_failure_stops_without_reclaiming():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
        config.paths.cache_clear()
        db.init()
        topic_id = db.add_topic("pending")
        args = argparse.Namespace(all=True, model=None, no_stage=True)
        with patch.object(runner, "run_one", side_effect=ValueError("invalid config")) as run:
            assert cli._cmd_run(args) == 1
            assert run.call_count == 1
        assert db.get_topic(topic_id)["status"] == "pending"
    config.paths.cache_clear()


def test_fetch_and_adapt_share_one_ledger_but_other_ingests_do_not():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
        config.paths.cache_clear()
        p = config.paths()
        _ingest_prompts(p)
        calls = []
        def fake(prompt, **kwargs):
            calls.append((kwargs["stage"], kwargs["ledger_path"]))
            if kwargs["stage"] == "ingest_fetch":
                url = next(url for url in ("https://example.com/first", "https://example.com/second") if url in prompt)
                return _fetch_result(kwargs, url, "# An essay\n\nThe author's original text.")
            else:
                assert "The author's original text." in prompt
                kwargs["expect_file"].write_text("The author's original text.")
        with patch.object(llm, "run", fake):
            first = ingest.ingest_source("https://example.com/first")
            second = ingest.ingest_source("https://example.com/second")
        assert [c[0] for c in calls] == ["ingest_fetch", "ingest", "ingest_fetch", "ingest"]
        assert calls[0][1] == calls[1][1]
        assert calls[2][1] == calls[3][1]
        assert calls[0][1] != calls[2][1]
        assert first["usage_path"] != second["usage_path"]
        assert all(c[1] != p.runs / "usage.jsonl" for c in calls)
    config.paths.cache_clear()


def test_url_ingest_uses_complete_cached_text_when_model_response_is_shortened():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
        config.paths.cache_clear()
        p = config.paths()
        _ingest_prompts(p)
        original = "The author's opening.\n\n" + "An essential middle paragraph.\n\n" * 2000 + "The author's final words."
        def fake(prompt, **kwargs):
            assert kwargs["stage"] == "ingest_fetch"
            assert kwargs["allowed_tools"] == ("web_fetch",)
            result = _fetch_result(kwargs, "https://example.com/", original)
            kwargs["expect_file"].write_text("# Invented title\n\nA short summary of the opening.")
            return result
        def adapt(source, output, model, author):
            assert source.read_text() == original
            return original
        with patch.object(llm, "run", fake):
            result = ingest.ingest_source("https://EXAMPLE.com:443#introduction", _adapt=adapt)
        assert result["source_words"] == len(original.split())
        assert Path(result["script_path"]).read_text().endswith(original + "\n")
        assert result["title"] == "The author's opening."
        assert "Invented title" not in Path(result["script_path"]).read_text()
    config.paths.cache_clear()


def test_url_ingest_rejects_missing_or_incomplete_cache_before_adapt_and_staging():
    cases = (
        {"url": "https://example.com/other"},
        {"url": "https://example.com/article?version=other"},
        {"extraction_complete": False},
        {"kind": "search"},
        {"text": "  "},
        {"text": None},
        {"missing_artifacts": True},
    )
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
            config.paths.cache_clear()
            p = config.paths()
            _ingest_prompts(p)
            def fake(prompt, **kwargs):
                if case.get("missing_artifacts"):
                    kwargs["expect_file"].write_text("A plausible but unverified essay.")
                    return {}
                record = {"url": "https://example.com/article", "text": "The complete source."}
                record.update(case)
                return _fetch_result(kwargs, **record)
            with patch.object(llm, "run", fake), patch.object(ingest, "_model_adapt") as adapt:
                try:
                    ingest.ingest_source("https://example.com/article")
                except ValueError as exc:
                    assert "refusing to stage a partial essay" in str(exc), case
                else:
                    raise AssertionError(f"Accepted unverified source: {case}")
                adapt.assert_not_called()
            assert not list(p.inbox_scripts.glob("*.md")), case
    config.paths.cache_clear()


def test_url_ingest_rejects_source_cache_paths_outside_the_attempt():
    for directory_link in (False, True):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
            config.paths.cache_clear()
            p = config.paths()
            _ingest_prompts(p)
            external = p.root / "outside"
            external.mkdir()
            (external / "source.json").write_text(json.dumps({
                "kind": "fetch", "url": "https://example.com/article",
                "extraction_complete": True, "text": "Outside the attempt cache.",
            }))
            def fake(prompt, **kwargs):
                artifacts = kwargs["ledger_path"].parent / "llm-artifacts" / "ingest-fetch-test"
                artifacts.mkdir(parents=True)
                cache = artifacts / "source-cache"
                if directory_link:
                    cache.symlink_to(external, target_is_directory=True)
                else:
                    cache.mkdir()
                    (cache / "source.json").symlink_to(external / "source.json")
                kwargs["expect_file"].write_text(str(external / "source.json"))
                return {"artifacts_path": str(artifacts)}
            with patch.object(llm, "run", fake), patch.object(ingest, "_model_adapt") as adapt:
                try:
                    ingest.ingest_source("https://example.com/article")
                except ValueError:
                    pass
                else:
                    raise AssertionError("Accepted a source cache outside the attempt")
                adapt.assert_not_called()
            assert not list(p.inbox_scripts.glob("*.md"))
    config.paths.cache_clear()


def test_private_render_hashes_spoken_input_and_removes_stale_captions():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = root / "script.md"
        original = b"---\ntitle: Original\n---\n\nOriginal spoken words."
        script.write_bytes(original)
        output = root / "preview"
        output.mkdir()
        (output / "episode.vtt").write_text("Old captions for another recording")
        def synthesize(body, engine, settings):
            assert body.strip() == "Original spoken words."
            script.write_text("Edited while rendering")
            return b"audio bytes", [], {"canonical_captions": True, "engine": "fake"}
        fake_mp3 = ModuleType("mutagen.mp3")
        fake_mp3.MP3 = lambda path: SimpleNamespace(info=SimpleNamespace(length=12.0))
        with patch.dict(sys.modules, {"mutagen.mp3": fake_mp3}), \
             patch.object(render, "_synthesize", synthesize), \
             patch.object(render, "_tag"), patch.object(render, "voice_config", return_value={}), \
             patch.object(db, "upsert_episode") as register:
            result = render.render_preview(script, output, engine=object())
        assert result["script_sha256"] == hashlib.sha256(original).hexdigest()
        assert result["published"] is False
        assert not (output / "episode.vtt").exists()
        assert script.exists()
        register.assert_not_called()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"{len(tests)} passed")
