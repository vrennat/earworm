# Earworm

[![PyPI](https://img.shields.io/pypi/v/earworm.svg)](https://pypi.org/project/earworm/)
[![Python](https://img.shields.io/pypi/pyversions/earworm.svg)](https://pypi.org/project/earworm/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Give it a topic; get back a narrated podcast episode. Earworm researches the topic
with the Claude CLI, runs the findings through an adversarial review, rewrites them
into a script written *for the ear*, narrates it with a local neural voice (Kokoro),
masters the audio to broadcast loudness, and tags a ready-to-play mp3. Optionally it
publishes to a private podcast feed you can subscribe to on your phone. Generation
(LLM, occasionally slow) is fully decoupled from rendering (local, fast, deterministic) —
they only ever communicate through a folder of script files.

## Install

Earworm needs **Python 3.11+**, [`ffmpeg`](https://ffmpeg.org/), and — for the research
and scripting passes — the authenticated [`claude`](https://docs.claude.com/en/docs/claude-code/overview)
CLI on your `PATH`. Narration is fully local; no API key needed for the voice.

**From PyPI:**

```sh
pip install earworm            # or: uv tool install earworm
earworm download-models        # one-time: fetch the Kokoro voice model + G2P data (~few hundred MB)
```

**From source** (to tune the prompts — they're the product):

```sh
git clone https://github.com/tannervass/earworm && cd earworm
uv sync                        # .venv + locked deps (incl. Kokoro + torch)
uv run earworm download-models
```

Recommended for proper-noun pronunciation: `brew install espeak-ng` (Linux:
`apt install espeak-ng`). Kokoro's misaki G2P uses it as an out-of-vocabulary fallback
and degrades gracefully without it.

## Quickstart

```sh
earworm init                   # scaffold prompts/ + config templates + queue db here
cp config/show.example.toml config/show.toml     # set your podcast title/author (optional)

earworm add "What is the current state of small language models, and why does it matter?"
earworm run                    # research -> review -> script  (writes inbox/scripts/<id>.md)
earworm watch                  # render scripts -> episodes/<id>.mp3  (long-running)
```

From a source checkout, prefix commands with `uv run` (e.g. `uv run earworm init`). The
first synthesis warms up in ~30s; after that the watcher stays warm and renders faster
than real time. With no config files at all, narration uses a sensible default voice —
customize it in `config/voice.toml`.

## Commands

```sh
earworm add "<topic>"        queue a topic
earworm autogen --count 3    propose + queue topics from interests.md
earworm list                 inspect the queue
earworm run [--id N] [--all] drain pending topic(s): research -> review -> script
earworm reset-stale          requeue topics stuck 'running' after a crash
earworm watch                render new scripts -> mp3 (+ publish), long-running
earworm render <file.md>     one-shot render of a single script (testing)
earworm download-models      pre-fetch the Kokoro model + voices (warm the cache)
earworm publish              retry upload + register for any unpublished episodes
```

`run` accepts `--model` to force one model across every stage (e.g. `--model sonnet`).
For finer control — a different model per pass, retries, fallback, or skipping a
quality pass — use `config/pipeline.toml` (see [Pipeline configuration](#pipeline-configuration)).

## Architecture

Two halves that share nothing but a folder. The producer is the LLM-driven generator;
the consumer is a dumb, deterministic renderer. Either can run, crash, or be restarted
independently.

```
                 PRODUCE (Claude CLI, slow)                CONSUME (local, fast, no LLM)
  earworm add ─┐
               ├─► [ queue: earworm.db ] ─► earworm run                earworm watch (polls inbox/)
  earworm      │      topics, episodes        │                              │
  autogen ─────┘                              │ 1. research  (web)           │ read script.md
                                              │ 2. review    (adversarial)   │ normalize for speech
                                              │ 3. script    (write for ear) │ apply lexicon (IPA)
                                              │ 4. script-review             │ Kokoro TTS -> wav
                                              │ 5. revise in place           │ ffmpeg master + mp3
                                              ▼                              │ ID3 tags + show notes
                                    inbox/scripts/<id>.md ──────────────────►│ episodes/<id>.mp3
                                                                             ▼
                                                          (optional) upload to R2 + register
                                                          with Cloudflare Worker ─► RSS feed ─► phone
```

- **Queue:** local SQLite (`earworm.db`), tables `topics` and `episodes`. The runner is
  offline-capable; the local queue is its source of truth.
- **Prompts** (`prompts/*.md`) are the product. The research → review → script →
  script-review → revise chain is five LLM passes; tune the prompts constantly.
- **Idempotency:** the renderer keys each episode on a hash of the script body, so
  re-processing the same script never produces a duplicate (`tests/test_idempotency.py`).
- **Atomic handoff:** scripts are generated/revised in a staging dir and `os.replace`d
  into `inbox/scripts/` only when finished, so the watcher never renders a half-written file.

## Backends

**Research + scripting** run through the Claude CLI — `claude -p` headless with a tool
allowlist, web search in the research pass. Earworm is coupled to Claude Code by design:
the agentic web-research-and-write loop is the whole quality story, so there is no
pluggable LLM backend. `claude.py` is the thin CLI wrapper; `pipeline.py` declares the
five passes and the executor (per-stage model, retry, fallback); `runner.py` orchestrates.
Authenticate with `claude login` or `ANTHROPIC_API_KEY`.

**Narration (TTS)** is [Kokoro](https://github.com/hexgrad/kokoro) — a local neural voice
model. 54 voices, runs on-device, no API key, free. Selected by `engine` in
`config/voice.toml`; the engine is loaded behind a small interface
(`src/earworm/tts/base.py`) so another backend can be dropped in later.

## Cost per episode

Honest caveat: these are **rough, unmeasured order-of-magnitude estimates**, not a
benchmark. Real cost depends on the model, topic depth, and how much the research pass
fetches. Measure your own before trusting a number.

- **Narration (Kokoro):** $0. Runs locally on CPU/GPU.
- **Research + scripting (Claude CLI):**
  - On a **Claude Pro/Max subscription**: ~$0 marginal — the five passes count against
    your subscription usage limits, not a per-call bill.
  - On a **pay-as-you-go API key**: the five passes (research with web search is the
    heaviest) are the cost driver. Ballpark **a few cents to ~$1 per episode** with
    Sonnet; more with Opus, less with Haiku. Treat this as a starting guess, not a quote.
- **Publishing (Cloudflare R2 + Worker), if enabled:** effectively $0 at personal volume
  (well within free tiers).

## Configuration

Every setting is documented in one place in **`config/earworm.example.toml`**. At runtime
the pipeline reads these as separate files — copy each `*.example.toml` to its real name:

| File                  | Required?            | Purpose                                            |
| --------------------- | -------------------- | -------------------------------------------------- |
| `config/pipeline.toml`| optional             | Per-stage model, retries, fallback, stage toggles  |
| `config/voice.toml`   | for rendering        | TTS engine, voice/blend, audio + mastering chain   |
| `config/show.toml`    | for rendering        | Podcast title/author/description/cover (ID3 + RSS) |
| `config/lexicon.toml` | optional (recommended) | Pronunciation overrides (IPA) for proper nouns   |
| `config/feed.toml`    | only if publishing   | Cloudflare account, R2 bucket, Worker URL          |
| `config/secrets.toml` | only if publishing   | API token + feed secrets (or use env vars)         |
| `.env`                | optional             | `ANTHROPIC_API_KEY` and other secrets via env      |
| `interests.md`        | only for `autogen`   | Free-form interests that steer auto-topic proposals |

**Voices.** 54 Kokoro voices download on first use. Set `voice` (and a matching
`lang_code`: `a` American, `b` British) in `config/voice.toml`, or set a weighted `blend`.
Naming is `<lang><gender>_<name>` — e.g. `af_sky` (American female), `am_michael`
(American male), `bf_emma` (British female). Audition them with
`uv run python scripts/voice_sampler.py`.

**Pronunciation.** Kokoro mispronounces some proper nouns and acronyms. `config/lexicon.toml`
maps a word to misaki modified-IPA; the renderer rewrites it inline so Kokoro honors it.
The shipped example covers common AI/tech/networking terms — extend it for your subject.

### Pipeline configuration

Each topic runs five Claude Code passes: `research → review → script → script_review →
revise`. With no `config/pipeline.toml` they all run on the `claude` CLI's default model
with one retry. Copy `config/pipeline.example.toml` to tune per stage:

- **Per-stage model** — spend where it matters. `[pipeline.research] model = "opus"` for
  the web-research pass, cheaper models elsewhere. `earworm run --model <m>` still forces
  one model across every stage when you want a blunt override.
- **Retry + fallback** — `retries` adds attempts on the primary model; `fallback_model`
  makes one final attempt on a different model after the primary budget is exhausted
  (independent of `retries`, so it fires even at `retries = 0`).
- **Toggle quality passes** — `[pipeline.review] enabled = false` writes the script
  straight from the report; `[pipeline.script_review] enabled = false` skips the
  script-review *and* revise loop (revise exists only to fold the review back in). The
  three load-bearing passes (research, script, and revise-when-reviewing) can't be toggled,
  and stages can't be reordered — the order is a data dependency, not a preference.

## Publishing — a private podcast feed (optional)

Local-only use needs none of this: episodes render to `episodes/*.mp3` with full ID3 tags
that any player reads. To subscribe on your phone, deploy the bundled Cloudflare Worker
(`worker/`) — a token-gated RSS feed backed by D1, with audio served from a public R2
bucket. Everything is free-tier at personal volume. Uses [bun](https://bun.sh).

```sh
cd worker
bun install                                        # pins wrangler + types (commit-tracked lockfile)
cp wrangler.example.jsonc wrangler.jsonc           # fill in account_id, D1 id, show vars

# Provision Cloudflare resources
bunx wrangler d1 create earworm                     # paste the printed database_id into wrangler.jsonc
bunx wrangler d1 execute earworm --remote --file schema.sql
# create a PUBLIC R2 bucket in the dashboard; note its pub-*.r2.dev base URL

# Secrets (token-gates the feed + the ingest endpoint)
bunx wrangler secret put FEED_TOKEN
bunx wrangler secret put INGEST_SECRET

bunx wrangler deploy
```

Then point the Python side at it — in `config/feed.toml` set `enabled = true`, the
`worker_url`, R2 `bucket`, and `public_audio_base`; put `FEED_TOKEN`/`INGEST_SECRET` in
`config/secrets.toml` (or the matching env vars). After that, `earworm watch` uploads each
new episode to R2 and registers it with the Worker; `earworm publish` backfills any that
failed.

The Worker serves a token-gated `/<FEED_TOKEN>/feed.xml` (valid podcast RSS 2.0 with the
iTunes namespace) — also reachable as `/feed.xml?token=…` for finicky apps. Audio is served
directly from the public R2 bucket under an unguessable per-episode key; the Worker never
proxies bytes. A bad token returns 404 (not 401), so the feed's existence never leaks.

## Scheduling (macOS)

For hands-off operation, `launchd/` ships three agents — a `watch` daemon (renders +
publishes continuously), a weekday `run` (drains one topic at 07:30), and a Monday
`autogen` (proposes 3 fresh topics from `interests.md`):

```sh
bash launchd/install.sh        # substitutes paths, loads the agents, starts the watcher
bash launchd/uninstall.sh      # unload + remove them
```

Logs land in `logs/`. On Linux, adapt the three `.plist` files to systemd timers.

## Docker

The painful part to install is the renderer — CPU PyTorch, Kokoro, espeak-ng, ffmpeg.
The bundled image owns all of that and bakes in a pre-warmed Kokoro model, so rendering
works out of the box. It is **CPU-only** (the default Linux torch wheel bundles CUDA at
~2GB; the build selects the CPU PyTorch index via `UV_TORCH_BACKEND=cpu`).

```sh
docker build -t earworm .                          # ~minutes; downloads torch + model

# Render: mount your working dir (config/*.toml, inbox/, episodes/, earworm.db) at /data
docker run --rm -v "$PWD":/data earworm watch        # render scripts as they appear
docker run --rm -v "$PWD":/data earworm render inbox/scripts/<id>.md   # one-shot
```

Earworm's two halves share only a folder, so the natural split is **generate on the host,
render in the container** — they meet at `inbox/scripts/`. Generation (`earworm run`) needs
the authenticated `claude` CLI, which isn't in the image. To also generate in-container,
install the CLI and pass a key:

```sh
docker run --rm -v "$PWD":/data -e ANTHROPIC_API_KEY=sk-... earworm run
```

(That still requires the `claude` CLI on `PATH` inside the image — add it to the Dockerfile
with a Node layer if you want a single do-everything container. The default image keeps
generation on the host.)

The model is downloaded at **build** time (`earworm download-models` runs in the build and
smoke-tests a synth), so first render is instant and a broken stack fails the build, not you.

## NOT in v1

- **A hosted/managed service.** This is a local CLI you run yourself.
- **Multi-voice / dialogue.** Single narrator only.
- **A web UI.** CLI only.
- **Music, stingers, or ad insertion.** Voice + mastering only.
- **Windows support.** Developed and tested on macOS (Apple Silicon); Linux should work,
  Windows is untested.

## Layout

```
prompts/        the five LLM prompts — the heart of it (bundled into the wheel too)
config/         *.example.toml templates (copy to real names; reals are gitignored)
src/earworm/    cli, db, pipeline (stages + executor), runner, claude, render (TTS), normalize, tts/
scripts/        cover generator, voice sampler, regen/render/rerender helpers
launchd/        macOS agents: watch daemon + weekday run + Monday autogen
worker/         Cloudflare Worker (TypeScript, bun) — token-gated RSS feed over D1 + R2
tests/          pipeline + config + normalize + idempotency tests (run: uv run python tests/<file>)
Dockerfile      CPU-only renderer image (Kokoro + ffmpeg, pre-warmed model)
```

## License

MIT — see [LICENSE](LICENSE).
