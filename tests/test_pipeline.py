"""Standalone tests for earworm.pipeline. Run: uv run python tests/test_pipeline.py
(or: PYTHONPATH=src python3.11 tests/test_pipeline.py)

No pytest dependency — plain asserts so it runs anywhere the package imports.
The executor has no heavy deps (no torch/kokoro), so these run fast. The real
`claude` CLI is never invoked: stage attempts are dependency-injected fakes.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm import claude  # noqa: E402
from earworm.pipeline import (  # noqa: E402
    PipelineConfig,
    RunContext,
    StageConfig,
    StageError,
    active_stages,
    resolve_model,
    run_stage,
    stage_by_name,
    with_retry,
)

NOSLEEP = lambda _seconds: None  # noqa: E731 - silence backoff in tests


def test_resolve_model_precedence() -> None:
    # cli flag wins over everything
    assert resolve_model("haiku", "opus", "sonnet") == "haiku"
    # no cli -> per-stage model wins over default
    assert resolve_model(None, "opus", "sonnet") == "opus"
    # no cli, no stage -> global default
    assert resolve_model(None, None, "sonnet") == "sonnet"
    # nothing set -> None (let the claude CLI choose)
    assert resolve_model(None, None, None) is None


def test_with_retry_succeeds_first_try() -> None:
    calls: list = []

    def attempt(model):
        calls.append(model)
        return "ok"

    assert with_retry(attempt, model="A", retries=2, fallback_model=None, sleep=NOSLEEP) == "ok"
    assert calls == ["A"], "success on first try must not retry"


def test_with_retry_exhausts_then_raises() -> None:
    calls: list = []

    def always_fail(model):
        calls.append(model)
        raise claude.ClaudeError("boom")

    raised = False
    try:
        with_retry(always_fail, model="A", retries=2, fallback_model=None, sleep=NOSLEEP)
    except claude.ClaudeError:
        raised = True
    assert raised, "must re-raise after exhausting retries"
    assert calls == ["A", "A", "A"], "retries=2 means 3 total primary attempts"


def test_with_retry_falls_back_after_exhaustion() -> None:
    calls: list = []

    def fail_primary(model):
        calls.append(model)
        if model == "A":
            raise claude.ClaudeError("boom")
        return "fallback-ok"

    result = with_retry(fail_primary, model="A", retries=2, fallback_model="B", sleep=NOSLEEP)
    assert result == "fallback-ok"
    assert calls == ["A", "A", "A", "B"], "fallback is one extra attempt after the primary budget"


def test_with_retry_fallback_with_zero_retries() -> None:
    calls: list = []

    def fail_primary(model):
        calls.append(model)
        if model == "A":
            raise claude.ClaudeError("boom")
        return "fallback-ok"

    # retries=0 still tries the fallback once: fallback is independent of the budget
    result = with_retry(fail_primary, model="A", retries=0, fallback_model="B", sleep=NOSLEEP)
    assert result == "fallback-ok"
    assert calls == ["A", "B"]


def test_pipeline_config_defaults() -> None:
    pc = PipelineConfig.from_toml({})
    assert pc.default_model is None
    assert pc.default_retries == 1
    sc = pc.for_stage("research")
    assert sc == StageConfig()  # all-default
    assert sc.enabled is True


def test_pipeline_config_overrides() -> None:
    pc = PipelineConfig.from_toml(
        {
            "pipeline": {
                "default_model": "sonnet",
                "default_retries": 2,
                "research": {
                    "model": "opus",
                    "timeout": 1800,
                    "retries": 3,
                    "fallback_model": "sonnet",
                },
                "review": {"enabled": False},
            }
        }
    )
    assert pc.default_model == "sonnet"
    assert pc.default_retries == 2
    r = pc.for_stage("research")
    assert r.model == "opus"
    assert r.timeout == 1800
    assert r.retries == 3
    assert r.fallback_model == "sonnet"
    assert pc.for_stage("review").enabled is False
    # an unconfigured stage falls back to all-default
    assert pc.for_stage("script") == StageConfig()


def _names(cfg: PipelineConfig) -> list:
    return [s.name for s in active_stages(cfg)]


def test_active_stages_all_on_by_default() -> None:
    assert _names(PipelineConfig.from_toml({})) == [
        "research",
        "review",
        "script",
        "script_review",
        "revise",
    ]


def test_active_stages_review_off() -> None:
    cfg = PipelineConfig.from_toml({"pipeline": {"review": {"enabled": False}}})
    assert _names(cfg) == ["research", "script", "script_review", "revise"]


def test_active_stages_script_review_off_drops_revise_too() -> None:
    # the script_review + revise loop toggles as a unit
    cfg = PipelineConfig.from_toml({"pipeline": {"script_review": {"enabled": False}}})
    assert _names(cfg) == ["research", "review", "script"]


def test_active_stages_both_quality_passes_off() -> None:
    cfg = PipelineConfig.from_toml(
        {"pipeline": {"review": {"enabled": False}, "script_review": {"enabled": False}}}
    )
    assert _names(cfg) == ["research", "script"]


def _ctx(root: Path) -> RunContext:
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "prompts" / "research.md").write_text("topic={{topic}} out={{report_path}}")
    (root / "runs" / "RID").mkdir(parents=True, exist_ok=True)
    return RunContext(
        root=root,
        prompts=root / "prompts",
        runs=root / "runs",
        inbox_scripts=root / "inbox" / "scripts",
        run_id="RID",
        topic="cool topic",
        date="2026-06-09",
        review_enabled=True,
    )


def test_run_stage_success_writes_expected_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _ctx(Path(tmp))
        stage = stage_by_name("research")
        seen: dict = {}

        def fake_run(prompt, *, cwd, allowed_tools, expect_file, timeout, model):
            # a healthy claude run writes the expected file
            seen["model"] = model
            seen["prompt"] = prompt
            Path(expect_file).write_text("# report")
            return {}

        run_stage(stage, ctx, PipelineConfig.from_toml({}), cli_model=None, _run=fake_run, sleep=NOSLEEP)
        assert ctx.report_path.exists()
        assert "cool topic" in seen["prompt"], "prompt vars must be rendered"


def test_run_stage_failure_raises_stage_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _ctx(Path(tmp))
        stage = stage_by_name("research")

        def fake_run(prompt, *, cwd, allowed_tools, expect_file, timeout, model):
            raise claude.ClaudeError("nope")

        raised = None
        try:
            run_stage(stage, ctx, PipelineConfig.from_toml({}), cli_model=None, _run=fake_run, sleep=NOSLEEP)
        except StageError as e:
            raised = e
        assert raised is not None, "run_stage must wrap failures in StageError"
        assert raised.stage == "research"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
