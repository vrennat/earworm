# Earworm

[![PyPI](https://img.shields.io/pypi/v/earworm-pod.svg)](https://pypi.org/project/earworm-pod/)
[![Python](https://img.shields.io/pypi/pyversions/earworm-pod.svg)](https://pypi.org/project/earworm-pod/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Give it a topic; get back a narrated podcast episode. Earworm researches the topic
through explicit API/local models in Pi, checks the evidence, commissions an episode,
and writes a script *for the ear*, narrates it with a local neural voice (Kokoro),
masters the audio to broadcast loudness, and tags a ready-to-play mp3. Optionally it
publishes to a private podcast feed you can subscribe to on your phone. Generation
(LLM, occasionally slow) is fully decoupled from rendering (local, fast, deterministic) —
they only ever communicate through a folder of script files.

## Install

Earworm needs **Python 3.11+**, [`ffmpeg`](https://ffmpeg.org/), and — for the research
and scripting passes — Pi with configured API credentials or a local model. OpenRouter
calls use the configured dispatch guard. Narration is local; no API key is needed for Kokoro.

**From PyPI:**

```sh
pip install earworm-pod        # or: uv tool install earworm-pod  (the CLI is still `earworm`)
earworm download-models        # one-time: fetch the Kokoro voice model + G2P data (~few hundred MB)
```

**From source** (to tune the prompts — they're the product):

```sh
git clone https://github.com/vrennat/earworm && cd earworm
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
cp config/llm.example.toml config/llm.toml        # configure Pi paths, models, and spend caps
cp config/pipeline.example.toml config/pipeline.toml

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
earworm ingest <src>         stage a pre-written script (file, URL, or stdin) to render
earworm list                 inspect the queue
earworm run [--id N] [--all] drain pending topic(s): research -> review -> script
earworm reset-stale          requeue topics stuck 'running' after a crash
earworm watch                render new scripts -> mp3 (+ publish), long-running
earworm render <file.md>     one-shot render of a single script (testing)
earworm download-models      pre-fetch the Kokoro model + voices (warm the cache)
earworm publish              retry upload + register for any unpublished episodes
```

`run --model <provider-model-id>` overrides the model on each stage's configured provider.
Use `config/llm.toml` for routes and budgets, and `config/pipeline.toml` for timing and
review toggles. To listen privately, run with `--no-stage`, then export with
`earworm render runs/<run-id>/script.md --output-dir previews/<run-id>`. This path never
enters the watched inbox, moves the script, updates the episode ledger, or publishes.

### Ingesting pre-written scripts

When the text already exists — an essay, a blog post, a talk transcript — you don't
need the research and script-generation passes. `earworm ingest` is a second intake
path: it takes ready prose and stages it straight into `inbox/scripts/`, where the same
`earworm watch` renderer turns it into an episode. It never touches the topics queue.

```sh
earworm ingest essay.md                          # a local markdown/text file
earworm ingest https://example.com/some-essay    # fetch + extract the article through the configured API
pbpaste | earworm ingest -                        # stdin
earworm ingest essay.md --title "My Title" --date 2026-06-14
earworm ingest essay.md --author "Dario Amodei" --feed dario-amodei  # route to a separate feed
```

By default a light API/local pass adapts the text **for the ear**: it strips reading-only
artifacts (markdown, footnote markers, "see the figure below", inline links), spells
out numbers, and adds pronunciation hints — without summarizing or rewriting the
author's argument. Pass `--raw` to skip that pass and read the text verbatim (markdown
is still stripped deterministically). If the adapt pass looks like it condensed a long
essay, `ingest` warns you and suggests `--raw`. Configure `ingest` and `ingest_fetch`
routes in `config/llm.toml`; optional timeouts live in `config/pipeline.toml`.

`--feed <name>` routes the episode to a separate named RSS feed instead of the main one
(see [Multiple feeds](#multiple-feeds) below) — handy for curated content like a guest
author's essays that you want to subscribe to and share on its own.

## Architecture

Two halves that share nothing but a folder. The producer is the LLM-driven generator;
the consumer is a dumb, deterministic renderer. Either can run, crash, or be restarted
independently.

```
                 PRODUCE (Pi, API/local)                CONSUME (local, fast, no LLM)
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

- **Queue:** local SQLite (`earworm.db`), tables `topics` and `episodes`. The queue
  remains available when a provider is offline; generation records its failure there.
- **Prompts** (`prompts/*.md`) are the product. The research → review → script →
  script-review → revise chain is five LLM passes; tune the prompts constantly.
- **Idempotency:** the renderer keys each episode on a hash of the script body, so
  re-processing the same script never produces a duplicate (`tests/test_idempotency.py`).
- **Atomic handoff:** scripts are generated/revised in a staging dir and `os.replace`d
  into `inbox/scripts/` only when finished, so the watcher never renders a half-written file.

## Backends

**Research + scripting** use `llm.py`, which starts an isolated Pi process with an explicit
provider/model, bounded web tools, shared deadlines, and a run cost ledger. Coding tools,
interactive skills, automatic compaction, and hidden provider retries are disabled.
OpenRouter dispatch goes through the configured Manabase guard. A single configured
alternate route is allowed after a transport failure; authentication, credit, budget,
and output-limit failures stop. No Claude executable, login, or account is used.

Research gathers evidence; its review also commissions the episode. The writer and both
editing passes receive the full report, corrected review, and bounded excerpts from
recent episodes, including their middles and endings. There is no outline rotation.
Resume records check input and artifact hashes before reusing research or review.
They include the stage's effective route and backend code; changing only the writer's
allowance does not invalidate completed research. Research retries reuse retained sources.
Retrieval preserves table headers, caches full extracted sources, and has a total text
allowance. The final permitted request writes the artifact with tools disabled.

URL ingestion uses the complete cached extraction as its source, rather than a model's
restatement of the article. Missing or incomplete extraction stops before adaptation.

**Narration** defaults to local [Kokoro](https://github.com/hexgrad/kokoro). The optional
Voicebox adapter supports the first Qwen CustomVoice audition. Clean transcript text,
speech aliases, and delivery settings are separate. Unsupported controls fail explicitly.
Canonical caption times include the mastering lead pad once.

## Cost per episode

Every model attempt records its requested route, tokens, response IDs, timing, outcome,
and cost in the run's `usage.jsonl`. OpenRouter charges are reconciled by response ID.
Unknown charges remain unknown and retain a conservative budget reservation. The guard's
canaries are also bounded and reserved. Do not confuse catalog estimates with billed cost.

Set both `stage_budget_usd` and `run_budget_usd` in `llm.toml`. OpenRouter price ceilings
are dollars per million tokens. Local inference has no API charge, but local compute,
GPU contention, and electricity are separate costs. Narration records its own elapsed time.

## Configuration

Copy the relevant `*.example.toml` templates to their runtime names. The model route
and narration templates document their supported controls:

| File                  | Required?            | Purpose                                            |
| --------------------- | -------------------- | -------------------------------------------------- |
| `config/pipeline.toml`| optional             | Stage timing, optional model overrides, review toggles |
| `config/llm.toml` | for generation | Pi paths, API/local routes, tools, fallback, spending caps |
| `config/voice.toml`   | for rendering        | TTS engine, voice/blend, audio + mastering chain   |
| `config/show.toml`    | for rendering        | Podcast title/author/description/cover (ID3 + RSS) |
| `config/lexicon.toml` | optional (recommended) | Pronunciation overrides (IPA) for proper nouns   |
| `config/feed.toml`    | only if publishing   | Cloudflare account, R2 bucket, Worker URL          |
| `config/secrets.toml` | only if publishing   | API token + feed secrets (or use env vars)         |
| `.env`                | optional             | Provider keys and publishing secrets via env      |
| `interests.md`        | only for `autogen`   | Free-form interests that steer auto-topic proposals |

**Voices.** 54 Kokoro voices download on first use. Set `voice` (and a matching
`lang_code`: `a` American, `b` British) in `config/voice.toml`, or set a weighted `blend`.
Naming is `<lang><gender>_<name>` — e.g. `af_heart` (American female, the default
and Kokoro's top-graded voice), `am_michael` (American male), `bf_emma` (British
female). Audition them with
`uv run python scripts/voice_sampler.py`.

**Pronunciation.** Kokoro mispronounces some proper nouns and acronyms. `config/lexicon.toml`
maps a word to misaki modified-IPA; the renderer rewrites it inline so Kokoro honors it.
The shipped example covers common AI/tech/networking terms — extend it for your subject.

### Pipeline configuration

Each topic runs `research → review → script → script_review → revise`. The order reflects
artifact dependencies; it does not dictate the episode's spoken structure.

- Configure providers, model IDs, thinking, token limits, price ceilings, stage/run budgets,
  and optional transport fallback in `config/llm.toml` under `[llm.stages.<stage>]`.
- Configure timeouts and review toggles in `config/pipeline.toml`. Disabling research review
  lets the writer derive a brief from the report. Disabling script review also skips revision.
- Old `default_retries`, nonzero `retries`, and `fallback_model` settings in pipeline.toml
  require migration to the backend configuration. This prevents nested retry multiplication.
- Legacy Sonnet/Haiku/Opus aliases are not API model IDs. Copy the new templates and select
  explicit routes. The current example tests DeepSeek research and Gemini editorial passes;
  model assignments remain a quality decision, not a claim that cheaper output is adequate.

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

### Multiple feeds

One deployment can serve several feeds from the same database, so curated content can live
on its own feed you subscribe to and share independently of the main briefing. Every
episode carries a `feed` tag (default `default`); set it with `feed: <name>` in a script's
front-matter, or `earworm ingest … --feed <name>` (the name is slugified to be URL-safe).
Auto-generated briefings need no tag — they ride the default feed.

Each feed has its own URL, gated by the same token:

```
/<FEED_TOKEN>/feed.xml                 # the main feed
/<FEED_TOKEN>/dario-amodei/feed.xml    # a named feed   (also /feed.xml?token=…&feed=dario-amodei)
```

Two Worker `vars` (in `wrangler.jsonc`) tune the behavior:

- **`MAIN_FEED_INCLUDES_ALL`** — `"false"` (default) keeps the main feed to default-feed
  episodes only, so named feeds stay separate; `"true"` makes it aggregate every episode.
- **`FEED_META`** — an optional JSON string mapping a feed slug to channel-metadata
  overrides (`title`, `author`, `description`, `image`, `link`, …). A feed with no entry
  inherits the show metadata, so e.g. the `dario-amodei` feed can carry its own title and
  author instead of the show's.

Deploying multi-feed onto an existing feed needs the one-time column migration
`bunx wrangler d1 execute <db> --remote --file migrations/0001_add_feed.sql` before
`bunx wrangler deploy`; fresh deploys get the column from `schema.sql`. Re-tag an
already-published episode by editing its `feed:` front-matter (or the local ledger) and
running `earworm publish` — no re-render needed; the episode moves to its new feed in place.

## Scheduling (macOS)

For hands-off operation, `launchd/` ships two agents — a `watch` daemon that renders and
publishes continuously, and a daily producer that tops up the queue and drains one topic
at 07:00:

```sh
bash launchd/install.sh        # substitutes paths, loads the agents, starts the watcher
bash launchd/uninstall.sh      # unload + remove them
```

Logs land in `logs/`. On Linux, adapt the two `.plist` files to systemd timers.

Both jobs enter through `uv run --locked` rather than the generated
`.venv/bin/earworm` shebang. This matters on Homebrew-managed Macs: removing an old
Python formula otherwise leaves the shebang pointing at a nonexistent interpreter.
The installer runs `uv sync --locked` up front, and `uv run` recreates that broken
environment from `uv.lock` if it happens again.

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

The normal split is generation on the host with Pi and rendering in the container;
they meet at `inbox/scripts/`. The renderer image does not install Pi or the required
OpenRouter dispatch guard. Configure those explicitly if you build a combined image;
never copy a personal interactive agent environment into the image.

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
src/earworm/    cli, db, pipeline (stages + executor), runner, llm, render (TTS), normalize, tts/
scripts/        cover generator, voice sampler, regen/render/rerender helpers
launchd/        macOS agents: watch daemon + weekday run + Monday autogen
worker/         Cloudflare Worker (TypeScript, bun) — token-gated RSS feed over D1 + R2
tests/          pipeline + config + normalize + idempotency tests (run: uv run python tests/<file>)
Dockerfile      CPU-only renderer image (Kokoro + ffmpeg, pre-warmed model)
```

## Acknowledgments

The script-specificity and anti-template checks draw on Lauren Tan's
[`unslop`](https://github.com/cursor/plugins/blob/main/pstack/skills/unslop/SKILL.md)
skill.

## License

MIT — see [LICENSE](LICENSE). The Kokoro model and weights are Apache-2.0
(hexgrad/Kokoro-82M).

Issues and PRs welcome.
