# Pipeline Robustness — Phase 1 Design

Status: approved (design), pending spec review
Date: 2026-06-09
Scope: Earworm open-source launch, Phase 1

## Context

Phase 0 created the `earworm` repo as a renamed, pruned copy of the private `brief`
pipeline (5 commits: extraction, uv migration, cross-platform cover art, stale-code
cull). Measuring the original Phase 1 plan against what Phase 0 actually left:

| Original Phase 1 item            | Reality after Phase 0                                     |
| -------------------------------- | --------------------------------------------------------- |
| Make it pip installable          | Already done — hatchling, wheel target on `src/earworm`   |
| Build the `earworm` CLI          | Already done — `earworm = "earworm.cli:main"`, full CLI   |
| TTS interface/abstraction        | Already done — `tts/base.py` Protocol + `get_engine()`    |
| LLM interface/abstraction        | Not done — `claude.py` imported directly by runner/autogen |

The original LLM-abstraction goal existed to make the *vendor* swappable
(OpenAI/Ollama as experimental text-only backends). That goal is **dropped**.
Decision: Earworm stays coupled to Claude Code (`claude -p`) permanently. The
`claude` CLI is already a hard dependency in the README, and the agentic web-search
flow is the entire quality story — text-only backends would ship visibly worse
episodes behind an "experimental" asterisk. We are not building a `LLMBackend`
Protocol/factory and we are not adding OpenAI/Ollama.

"Robust options," for a Claude-Code-only tool, means investing one layer up — in the
**pipeline orchestration**, not in vendor portability.

## Goals

Three robustness investments, all within the Claude Code commitment:

1. **Per-stage model control** — choose the model per pass from config (research=opus,
   review/script=sonnet, autogen=haiku), not just a single global `--model`.
2. **Retry + model fallback** — on a stage failure or timeout, auto-retry; optionally
   make a final attempt with a configured fallback model before giving up.
3. **Configurable pipeline** — the five-pass flow becomes data-driven: the two
   adversarial quality passes can be toggled off, and per-stage model/timeout/retries
   are tuned from config instead of hardcoded in `runner.py`.

## Non-goals (explicit)

- **No `LLMBackend` interface, factory, or vendor abstraction.** `claude.py` stays a
  thin `claude -p` wrapper, called directly by the pipeline executor.
- **No OpenAI/Ollama backends.** Removed from intent entirely.
- **No stage reordering.** Order is a hard data dependency (review reads the report;
  script reads both), not a user preference. Users get *toggle* and *tune*, not *reorder*.
- **No fully TOML-defined pipeline.** Stage shape (prompts, tools, variable wiring)
  stays in type-checked code; only operational knobs are config-driven.
- **No changes to the TTS side.** It is already cleanly abstracted; we mirror its
  spirit, not its code.

## Design

### Approach

Declarative stages in code; operational knobs in config. The *shape* of the pipeline
(order, prompt files, allowed tools, inter-stage data wiring) lives in code where it is
type-checked and cannot be broken from a TOML file. The *tunable knobs* (model, timeout,
retries, fallback, enabled) are config-overridable per stage. This delivers all three
goals without a fragile TOML DSL and without under-delivering the "configurable" goal.

### New module: `src/earworm/pipeline.py`

The heart of the change. Three pieces:

**`Stage` dataclass** — one declarative pass:
- `name: str` — stable key used in config (`research`, `review`, `script`,
  `script_review`, `revise`, `autogen`).
- `prompt_file: str` — template under `prompts/`.
- `allowed_tools: tuple[str, ...]` — passed to `claude.run` as `--allowedTools`.
- `build_vars: Callable[[RunContext], dict[str, str]]` — assembles the prompt
  template variables from the run context.
- `expect_file: Callable[[RunContext], Path]` — the file whose existence signals
  success.
- `skip_if_exists: bool` — research/review/script_review skip when their output already
  has content (cross-run resume, unchanged from today). script/revise always run.
- `optional: bool` — review and the script_review+revise loop can be toggled off.

**`STAGES: list[Stage]`** — declares the five passes in dependency order. This is the
single source of truth for the pipeline shape; `runner.py` no longer hardcodes it.

**`run_stage(stage, ctx, cfg) -> None`** — the executor:
- Resolves the model (precedence below).
- Runs the retry loop and the optional fallback attempt.
- Enforces the per-stage timeout.
- On final failure raises `StageError(stage.name, last_exc)`.

The model-resolution + retry/fallback loop is factored into a reusable helper (e.g.
`with_retry(fn, cfg)`) so it works for both call shapes: `run_stage` wraps the
file-producing `claude.run` (success = `expect_file` written), while the autogen path
(below) wraps the text-returning `claude.run_text` (success = non-empty text). Only the
success predicate differs; model resolution, retry counting, fallback, and backoff are
shared.

### Model resolution precedence

Highest wins:
1. CLI `--model` (explicit, ad-hoc — forces the primary model for *all* stages; preserves
   today's behavior).
2. `[pipeline.<stage>].model` (per-stage config).
3. `[pipeline].default_model` (global config default).
4. Unset → omit `--model`, let the `claude` CLI use its own default.

`fallback_model` is independent of selection: it still applies on failure even when
`--model` forced the primary, because it is a resilience knob, not a selection knob.

### Retry + fallback semantics

- A stage attempts its primary model `retries + 1` times.
- If all primary attempts fail **and** `fallback_model` is set, it makes **one** final
  attempt with the fallback model before giving up. (Fallback is a distinct safety net,
  not part of the retry budget — so `retries = 0` + a fallback still tries the fallback once.)
- A small fixed backoff (a couple seconds) sits between attempts. No exponential backoff —
  Claude calls already run for minutes, so backoff is negligible.
- **Failure** = nonzero exit / `is_error` in the result / expected file not written /
  `subprocess.TimeoutExpired`. All are caught by the executor and counted as an attempt.
- Cross-run idempotency is unchanged: `skip_if_exists` stages that already produced their
  output on a prior run are skipped entirely (no attempt, no retry).

### Config — new `config/pipeline.toml`

A new real file (`config/pipeline.toml` ← `config/pipeline.example.toml`), read by a new
`pipeline_config()` loader in `config.py`, mirroring the existing per-domain config files
(`voice.toml`, `show.toml`, ...). The file is optional; every key has a sane default.
The consolidated `config/earworm.example.toml` reference gains the same block.

```toml
[pipeline]
default_model   = "sonnet"     # global default; CLI --model overrides this everywhere
default_retries = 1            # retries (beyond the first attempt) for every stage

[pipeline.research]
model          = "opus"        # research is the pass worth the spend
timeout        = 1800
retries        = 2
fallback_model = "sonnet"      # final attempt drops to sonnet if opus keeps failing

[pipeline.review]
enabled = true                 # adversarial report review; toggle off to skip

[pipeline.script]
model = "sonnet"

[pipeline.script_review]
enabled = true                 # toggles the script_review + revise loop as a unit

[pipeline.autogen]
model   = "haiku"
retries = 1
```

### Optional-stage wiring

Two toggles, each with a defined degradation:

- **`[pipeline.review].enabled = false`** — the `review.md` pass is skipped, so the
  script stage receives no review. The script prompt's review reference becomes a
  *computed block variable*: a populated instruction block when a review exists, an empty
  string when it does not. `render_prompt` stays a dumb string-replace; the conditionality
  lives in `build_vars`, not in the template engine. This keeps the enabled (default) path
  byte-identical to today and only changes behavior when explicitly disabled.
- **`[pipeline.script_review].enabled = false`** — skips *both* `script_review` and
  `revise` (revise exists only to fold the script review back in; with no review there is
  nothing to fold). They are one adversarial loop and toggle together.

`research`, `script`, and (when its review exists) `revise` are not toggleable — they are
load-bearing.

### `runner.py` slims to orchestration

`run_one` becomes: load topic → build `RunContext` (paths, slug, run_id, topic, date) →
iterate the enabled `STAGES` through `run_stage` → atomically move the staged script into
`inbox/scripts/` → update db. All per-stage plumbing (prompt rendering, tool lists,
timeouts, the `claude.run`/`run_text` calls) moves into `pipeline.py`. The atomic
staged-script `os.replace` and the db status transitions stay in `runner.py`. Net effect:
`runner.py` drops to roughly half its current size and stops importing `claude` directly.

### `autogen.py`

Reuses the same model-resolution + retry helper (it is effectively a one-stage
`run_text` generate keyed `[pipeline.autogen]`). No structural change beyond routing its
`claude.run_text` call through the shared retry/model logic.

## Files touched

- **New:** `src/earworm/pipeline.py`, `config/pipeline.example.toml`,
  `docs/superpowers/specs/2026-06-09-pipeline-robustness-design.md`,
  `tests/test_pipeline.py`.
- **Modified:** `src/earworm/runner.py` (slimmed), `src/earworm/autogen.py` (routed
  through shared logic), `src/earworm/config.py` (add `pipeline_config()`),
  `config/earworm.example.toml` (document the new block), `prompts/script.md` (+ revise
  prompt if needed) for the computed review block, `README.md` (new "Pipeline
  configuration" section).
- **Unchanged:** `claude.py`, all of `tts/`, `db.py`, `render.py`, `normalize.py`,
  `feed.py`, the `.env` story.

## Testing (TDD)

Unit-test the executor in `tests/test_pipeline.py` against a fake `claude.run` /
`run_text` (no real CLI calls):
- Model resolution precedence (CLI > stage > default > unset).
- Retry exhaustion (primary fails `retries + 1` times → `StageError`).
- Fallback-on-final-attempt (primary exhausts, fallback model is tried once, success).
- Fallback with `retries = 0` (primary once, fallback once).
- Optional-stage skip wiring (disabled stage produces no attempt; downstream block var
  is empty).

Existing `tests/test_normalize.py` and `tests/test_idempotency.py` stay green untouched.

## Open questions resolved during brainstorming

- LLM vendor abstraction → **dropped**; permanent Claude Code coupling.
- "Robust" → per-stage models + retry/fallback + configurable (toggle/tune) pipeline.
- Config home → new `config/pipeline.toml`, consistent with existing per-domain files.
- Stage reordering → out of scope (data dependency, not preference).
