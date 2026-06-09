"""The generation pipeline: a declarative list of Claude Code passes plus an
executor that adds per-stage model control, retry, and model fallback.

The *shape* of the pipeline (order, prompts, tools, variable wiring) lives here in
type-checked code and cannot be broken from a config file. The *operational knobs*
(model, timeout, retries, fallback, enabled) come from `config/pipeline.toml` via
`PipelineConfig`. `runner.py` orchestrates; this module owns every `claude` call.

Earworm is coupled to Claude Code by design — `claude.py` is the only backend, and
these stages drive it. There is no vendor abstraction.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from . import claude

# Failures the executor treats as retryable: a non-zero/`is_error`/missing-file run
# (ClaudeError) or a hard timeout.
RETRYABLE = (claude.ClaudeError, subprocess.TimeoutExpired)


class StageError(RuntimeError):
    """A stage that exhausted its retries (and fallback). Carries the stage name so
    the runner can record which pass failed."""

    def __init__(self, stage: str, cause: BaseException) -> None:
        super().__init__(f"stage {stage!r} failed: {type(cause).__name__}: {cause}")
        self.stage = stage
        self.cause = cause


# --- configuration ---------------------------------------------------------

@dataclass(frozen=True)
class StageConfig:
    """Per-stage operational knobs from `[pipeline.<stage>]`. None means "unset —
    use the stage's built-in default (or the pipeline default for retries)."""

    model: Optional[str] = None
    timeout: Optional[int] = None
    retries: Optional[int] = None
    fallback_model: Optional[str] = None
    enabled: bool = True


@dataclass(frozen=True)
class PipelineConfig:
    default_model: Optional[str] = None
    default_retries: int = 1
    stages: dict[str, StageConfig] = field(default_factory=dict)

    def for_stage(self, name: str) -> StageConfig:
        return self.stages.get(name, StageConfig())

    @classmethod
    def from_toml(cls, data: dict) -> "PipelineConfig":
        """Parse a raw `config/pipeline.toml` dict. Scalar keys under `[pipeline]`
        set the defaults; every sub-table is a per-stage override."""
        pl = data.get("pipeline", {})
        stages: dict[str, StageConfig] = {}
        for key, val in pl.items():
            if isinstance(val, dict):
                stages[key] = StageConfig(
                    model=val.get("model"),
                    timeout=val.get("timeout"),
                    retries=val.get("retries"),
                    fallback_model=val.get("fallback_model"),
                    enabled=bool(val.get("enabled", True)),
                )
        return cls(
            default_model=pl.get("default_model"),
            default_retries=int(pl.get("default_retries", 1)),
            stages=stages,
        )


# --- model resolution + retry ---------------------------------------------

def resolve_model(
    cli_model: Optional[str], stage_model: Optional[str], default_model: Optional[str]
) -> Optional[str]:
    """Precedence: explicit CLI --model > per-stage config > global default > None
    (let the claude CLI pick). The CLI flag is a blunt global override."""
    return cli_model or stage_model or default_model


def with_retry(
    attempt: Callable[[Optional[str]], Any],
    *,
    model: Optional[str],
    retries: int,
    fallback_model: Optional[str],
    sleep: Callable[[float], None] = time.sleep,
    backoff: float = 2.0,
) -> Any:
    """Run `attempt(model)` up to `retries + 1` times. If every primary attempt
    raises a retryable error and `fallback_model` is set (and differs), make ONE
    final attempt with the fallback before re-raising the last error. Fallback is a
    distinct safety net, not part of the retry budget."""
    last: Optional[BaseException] = None
    for i in range(retries + 1):
        try:
            return attempt(model)
        except RETRYABLE as exc:
            last = exc
            if i < retries:
                sleep(backoff)
    if fallback_model and fallback_model != model:
        try:
            return attempt(fallback_model)
        except RETRYABLE as exc:
            last = exc
    assert last is not None
    raise last


# --- run context + stages --------------------------------------------------

@dataclass(frozen=True)
class RunContext:
    """Everything a stage needs to render its prompt and locate its output for a
    single topic run. Built by the runner from the topic row and `config.paths()`."""

    root: Path
    prompts: Path
    runs: Path
    inbox_scripts: Path
    run_id: str
    topic: str
    date: str
    review_enabled: bool

    @property
    def run_dir(self) -> Path:
        return self.runs / self.run_id

    @property
    def report_path(self) -> Path:
        return self.run_dir / "report.md"

    @property
    def review_path(self) -> Path:
        return self.run_dir / "review.md"

    @property
    def script_review_path(self) -> Path:
        return self.run_dir / "script_review.md"

    @property
    def staged_script(self) -> Path:
        # Generated + revised in the run dir, then os.replace'd into inbox by the runner.
        return self.run_dir / "script.md"

    @property
    def script_path(self) -> Path:
        return self.inbox_scripts / f"{self.run_id}.md"


def _review_section(ctx: RunContext) -> str:
    """The script prompt's review instruction — populated when the review pass is
    enabled, empty when it is toggled off (so the prompt never points at a file that
    was never written)."""
    if not ctx.review_enabled:
        return ""
    return (
        f"If a review exists at {ctx.review_path}, read that too — it flags weak "
        "spots and missed angles. Address them where you can; acknowledge "
        "uncertainty where you can't."
    )


@dataclass(frozen=True)
class Stage:
    name: str
    prompt_file: str
    allowed_tools: Sequence[str]
    build_vars: Callable[[RunContext], dict]
    expect_file: Callable[[RunContext], Path]
    skip_if_exists: bool = False
    # The `[pipeline.<toggle>].enabled` key that gates this stage. None = always on.
    # `revise` points at `script_review` so the review+revise loop toggles as a unit.
    toggle: Optional[str] = None
    default_timeout: int = 900


_RW = ("Read", "Write", "Edit")

STAGES: list[Stage] = [
    Stage(
        name="research",
        prompt_file="research.md",
        allowed_tools=("WebSearch", "WebFetch", "Read", "Write", "Edit"),
        build_vars=lambda c: {
            "topic": c.topic,
            "date": c.date,
            "report_path": str(c.report_path),
        },
        expect_file=lambda c: c.report_path,
        skip_if_exists=True,
        default_timeout=1800,
    ),
    Stage(
        name="review",
        prompt_file="review.md",
        allowed_tools=_RW,
        build_vars=lambda c: {
            "report_path": str(c.report_path),
            "review_path": str(c.review_path),
        },
        expect_file=lambda c: c.review_path,
        skip_if_exists=True,
        toggle="review",
    ),
    Stage(
        name="script",
        prompt_file="script.md",
        allowed_tools=_RW,
        build_vars=lambda c: {
            "date": c.date,
            "report_path": str(c.report_path),
            "review_section": _review_section(c),
            "script_path": str(c.staged_script),
            "slug": c.run_id,
        },
        expect_file=lambda c: c.staged_script,
    ),
    Stage(
        name="script_review",
        prompt_file="script_review.md",
        allowed_tools=_RW,
        build_vars=lambda c: {
            "script_path": str(c.staged_script),
            "script_review_path": str(c.script_review_path),
        },
        expect_file=lambda c: c.script_review_path,
        skip_if_exists=True,
        toggle="script_review",
    ),
    Stage(
        name="revise",
        prompt_file="script_revise.md",
        allowed_tools=_RW,
        build_vars=lambda c: {
            "script_path": str(c.staged_script),
            "script_review_path": str(c.script_review_path),
        },
        expect_file=lambda c: c.staged_script,
        # Bound to the script_review toggle (its only input). Skipped with it.
        toggle="script_review",
    ),
]

_BY_NAME = {s.name: s for s in STAGES}


def stage_by_name(name: str) -> Stage:
    return _BY_NAME[name]


def active_stages(cfg: PipelineConfig) -> list[Stage]:
    """The stages to run given the config toggles. Order is fixed (data dependency);
    a stage is dropped only when its controlling `[pipeline.<toggle>]` is disabled."""
    return [s for s in STAGES if s.toggle is None or cfg.for_stage(s.toggle).enabled]


# --- executor --------------------------------------------------------------

def run_stage(
    stage: Stage,
    ctx: RunContext,
    cfg: PipelineConfig,
    *,
    cli_model: Optional[str] = None,
    _run: Callable[..., Any] = claude.run,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Render the stage prompt and drive `claude.run` with retry + fallback. Raises
    `StageError(stage.name, ...)` if every attempt fails."""
    sc = cfg.for_stage(stage.name)
    prompt = claude.render_prompt(ctx.prompts / stage.prompt_file, **stage.build_vars(ctx))
    expect = stage.expect_file(ctx)
    timeout = stage.default_timeout if sc.timeout is None else sc.timeout
    retries = cfg.default_retries if sc.retries is None else sc.retries
    model = resolve_model(cli_model, sc.model, cfg.default_model)

    def attempt(m: Optional[str]) -> None:
        _run(
            prompt,
            cwd=ctx.root,
            allowed_tools=stage.allowed_tools,
            expect_file=expect,
            timeout=timeout,
            model=m,
        )

    try:
        with_retry(
            attempt,
            model=model,
            retries=retries,
            fallback_model=sc.fallback_model,
            sleep=sleep,
        )
    except RETRYABLE as exc:
        raise StageError(stage.name, exc) from exc
