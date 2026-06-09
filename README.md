# Earworm

Give it a topic; get back a narrated podcast episode. Earworm researches the topic
with the Claude CLI, runs the findings through an adversarial review, rewrites them
into a script written *for the ear*, narrates it with a local neural voice (Kokoro),
masters the audio to broadcast loudness, and tags a ready-to-play mp3. Optionally it
publishes to a private podcast feed you can subscribe to on your phone. Generation
(LLM, occasionally slow) is fully decoupled from rendering (local, fast, deterministic) —
they only ever communicate through a folder of script files.

## 30-second quickstart

Earworm uses [uv](https://docs.astral.sh/uv/). `uv sync` reads `.python-version`
(3.11), provisions the interpreter if needed, and installs the locked deps.

```sh
# Requirements: uv, ffmpeg, and the `claude` CLI (authenticated). uv handles Python.
git clone <your-fork> earworm && cd earworm

uv sync                                   # create .venv + install locked deps (incl. Kokoro + torch)
cp config/voice.example.toml  config/voice.toml
cp config/show.example.toml   config/show.toml
cp config/lexicon.example.toml config/lexicon.toml

uv run earworm init                       # create data dirs + queue db
uv run earworm add "What is the current state of small language models, and why does it matter?"
uv run earworm run                        # research -> review -> script  (writes inbox/scripts/<id>.md)
uv run earworm watch                      # render scripts -> episodes/<id>.mp3  (long-running)
```

The first synthesis downloads the Kokoro model (~few hundred MB) and warms up in ~30s;
after that the watcher stays warm and synthesis runs faster than real time. For better
proper-noun pronunciation, optionally `brew install espeak-ng` (Kokoro's misaki G2P uses
it as an out-of-vocabulary fallback; it degrades gracefully without it).

## Commands

```sh
earworm add "<topic>"        queue a topic
earworm autogen --count 3    propose + queue topics from interests.md
earworm list                 inspect the queue
earworm run [--id N] [--all] drain pending topic(s): research -> review -> script
earworm watch                render new scripts -> mp3 (+ publish), long-running
earworm render <file.md>     one-shot render of a single script (testing)
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

## Publishing (optional)

Local-only use needs none of this — episodes render to `episodes/*.mp3` and carry full
ID3 tags. To subscribe on a phone, deploy the Cloudflare Worker in `worker/`:

1. `cp worker/wrangler.example.jsonc worker/wrangler.jsonc` and fill in your account/D1 IDs.
2. Provision a D1 database (`worker/schema.sql`) and a **public** R2 bucket.
3. Set `FEED_TOKEN` and `INGEST_SECRET` (`wrangler secret put ...`; `.dev.vars` for local).
4. `wrangler deploy`, then set `enabled = true` in `config/feed.toml`.

The Worker serves a token-gated `/<FEED_TOKEN>/feed.xml` (valid podcast RSS 2.0 with the
iTunes namespace). Audio is served directly from the public R2 bucket under an unguessable
key — the Worker never proxies it.

## NOT in v1

- **A hosted/managed service.** This is a local CLI you run yourself.
- **Scheduling / daemonization.** No bundled launchd/systemd/cron units — wrap `earworm run`
  and `earworm watch` with your OS's scheduler if you want hands-off operation.
- **Multi-voice / dialogue.** Single narrator only.
- **A web UI.** CLI only.
- **Music, stingers, or ad insertion.** Voice + mastering only.
- **Windows support.** Developed and tested on macOS (Apple Silicon); Linux should work,
  Windows is untested.

## Layout

```
prompts/        the five LLM prompts — the heart of it
config/         *.example.toml templates (copy to real names; reals are gitignored)
src/earworm/    cli, db, pipeline (stages + executor), runner, claude, render (TTS), normalize, tts/
scripts/        cover generator, voice sampler
worker/         Cloudflare Worker (TypeScript) for the optional private feed
tests/          normalize + idempotency tests (run: uv run python tests/<file>)
```

## License

MIT — see [LICENSE](LICENSE).
