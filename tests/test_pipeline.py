"""Artifact handoff tests; no model or network calls. Run with Python directly."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from earworm import config, db, pipeline, runner


def context(root):
    (root / "prompts").mkdir()
    source = Path(__file__).resolve().parent.parent / "prompts"
    for p in source.glob("*.md"):
        (root / "prompts" / p.name).write_text(p.read_text())
    ctx = pipeline.RunContext(root, root / "prompts", root / "runs", root / "inbox/scripts",
                              "2026-09-05-0001-test", "a test topic", "2026-09-05", True)
    ctx.run_dir.mkdir(parents=True)
    return ctx


def script(ctx):
    return f"---\ntitle: A test\ndate: {ctx.date}\nreport_path: {ctx.report_path}\n---\n\n" + "A complete spoken sentence. " * 40


def test_toggles_and_model_precedence():
    cfg = pipeline.PipelineConfig.from_toml({"pipeline": {"review": {"enabled": False}, "script_review": {"enabled": False}}})
    assert [s.name for s in pipeline.active_stages(cfg)] == ["research", "script"]
    assert pipeline.resolve_model("override", "stage", "default") == "override"
    assert pipeline.resolve_model(None, "stage", "default") == "stage"
    try:
        pipeline.PipelineConfig.from_toml({"pipeline": {"default_retries": 2}})
    except ValueError as e:
        assert "llm.toml" in str(e)
    else:
        raise AssertionError("Legacy retry multiplication must require migration")


def test_corrected_evidence_reaches_all_writing_stages():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = context(Path(tmp))
        ctx.report_path.write_text("Original report with source anchors")
        ctx.review_path.write_text("Correction: Node Six differs from Node Ten. Editorial commission follows.")
        ctx.staged_script.write_text(script(ctx))
        ctx.script_review_path.write_text("A structural defect")
        for name in ("script", "script_review", "revise"):
            stage = pipeline.stage_by_name(name)
            values = stage.build_vars(ctx)
            rendered = pipeline.llm.render_prompt(ctx.prompts / stage.prompt_file, **values)
            assert "Original report with source anchors" in rendered
            assert "Correction: Node Six differs from Node Ten" in rendered
            assert not stage.allowed_tools
        assert pipeline.stage_by_name("script_review").build_vars(ctx)["word_count"] == "160"
        disabled = pipeline.RunContext(**{**ctx.__dict__, "review_enabled": False})
        assert pipeline.stage_by_name("script").build_vars(disabled)["review_content"] == ""


def test_resume_requires_matching_inputs_and_unedited_artifact():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = context(Path(tmp))
        stage = pipeline.stage_by_name("research")
        cfg = pipeline.PipelineConfig()
        def fake(prompt, **kwargs):
            kwargs["expect_file"].write_text("A complete report")
        pipeline.run_stage(stage, ctx, cfg, _run=fake)
        assert pipeline.can_resume(stage, ctx, cfg)
        ctx.report_path.write_text("A manually corrected report")
        assert not pipeline.can_resume(stage, ctx, cfg)
        pipeline.run_stage(stage, ctx, cfg, _run=fake)
        (ctx.prompts / "research.md").write_text("Changed commission {{topic}}")
        assert not pipeline.can_resume(stage, ctx, cfg)
        assert not pipeline.can_resume(pipeline.stage_by_name("script_review"), ctx, cfg)


def test_research_retry_reuses_retained_sources_with_coverage():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = context(Path(tmp))
        with patch.object(pipeline.llm, "retained_evidence", return_value="Source: https://example.com\nCharacters 0-80 of 160."):
            stage = pipeline.stage_by_name("research")
            prompt = pipeline.llm.render_prompt(ctx.prompts / stage.prompt_file, **stage.build_vars(ctx))
        assert "Reuse this evidence rather than fetching the same pages again" in prompt
        assert "Source: https://example.com\nCharacters 0-80 of 160." in prompt


def test_writer_allowance_changes_do_not_invalidate_completed_research():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = context(Path(tmp))
        (ctx.root / "config").mkdir()
        config_file = ctx.root / "config/llm.toml"
        config_file.write_text('[llm]\nmodel="research-model"\n[llm.stages.script]\nmax_output_tokens=3000\n')
        stage = pipeline.stage_by_name("research")
        cfg = pipeline.PipelineConfig()
        pipeline.run_stage(stage, ctx, cfg, _run=lambda prompt, **kw: kw["expect_file"].write_text("Report"))
        config_file.write_text(config_file.read_text().replace('3000', '8000'))
        assert pipeline.can_resume(stage, ctx, cfg)
        config_file.write_text(config_file.read_text().replace('research-model', 'another-research-model'))
        assert not pipeline.can_resume(stage, ctx, cfg)


def test_invalid_script_stops_before_handoff_and_empty_review_succeeds():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = context(Path(tmp))
        cfg = pipeline.PipelineConfig()
        def invalid(prompt, **kwargs):
            kwargs["expect_file"].write_text("I have written the script.")
        try:
            pipeline.run_stage(pipeline.stage_by_name("script"), ctx, cfg, _run=invalid)
        except pipeline.StageError as e:
            assert e.stage == "script"
        else:
            raise AssertionError("Non-script model response accepted")
        assert not ctx.script_path.exists()
        ctx.staged_script.write_text(script(ctx))
        def clean_review(prompt, **kwargs):
            kwargs["expect_file"].write_text("")
        pipeline.run_stage(pipeline.stage_by_name("script_review"), ctx, cfg, _run=clean_review)
        assert ctx.script_review_path.exists()
        assert not ctx.script_review_path.read_text()


def test_private_run_never_enters_watched_inbox_and_failures_stay_failed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        context(root)
        with patch.dict(os.environ, {"EARWORM_HOME": str(root)}):
            config.paths.cache_clear()
            db.init()
            tid = db.add_topic("Private episode")
            def fake(stage, ctx, cfg, **kwargs):
                stage.expect_file(ctx).write_text(script(ctx) if stage.name in {"script", "revise"} else "Evidence")
            with patch.object(pipeline, "run_stage", fake):
                result = runner.run_one(tid, stage_for_render=False)
            assert Path(result["script_path"]).parent.parent == root / "runs"
            assert not list((root / "inbox/scripts").glob("*.md"))
            assert db.get_topic(tid)["status"] == "done"
            fail_id = db.add_topic("Failure episode")
            def failed(stage, ctx, cfg, **kwargs):
                if stage.name == "revise":
                    raise RuntimeError("API rejected this request")
                fake(stage, ctx, cfg, **kwargs)
            with patch.object(pipeline, "run_stage", failed):
                try:
                    runner.run_one(fail_id)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Failed revision escaped")
            assert db.get_topic(fail_id)["status"] == "failed"
            assert not list((root / "inbox/scripts").glob("*.md"))
        config.paths.cache_clear()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"{len(tests)} passed")
