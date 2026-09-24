# Earworm: API and local execution without a Claude account

Proposal, September 5, 2026. No production routing, credentials, or schedules changed.

The replacement pipeline must have no dependency on Tanner's Claude account, including its fallback routes. Keep the producer and files on Tundra. Use the existing Badlands 3090 for suitable local jobs and explicit API models through Pi for research and editorial work.

## Current state, checked live

- Earworm's producer still invokes the real Claude Code executable. Research, evidence review, drafting, and revision use Sonnet; topic generation and script review use Haiku. The installed daily job runs at 07:00 Pacific without a model override.
- All four September 5 topic-generation attempts hit the shared Claude Max session limit. The failure message stated a 07:20 reset. Authentication was still present. The latest completed episode was September 4; the Kokoro watcher remained running. No generation retry or quota reset was performed.
- The useful error is lost in the application's nonzero-exit handling because it prints stderr and discards the structured error in stdout. Repairing that error reporting belongs in the backend change.
- Badlands has a reachable, healthy Ollama 0.33.2 service and an RTX 3090 with 24 GB VRAM. Installed models are `gemma4:26b`, `qwen3.8:27b`, and `gpt-oss:20b`. Before our probe, no model was resident and GPU utilization was zero. This is a point-in-time observation.
- Tundra's Pi 0.85.0 already configures `badlands/gemma4:26b` at a 32k context window. The local model completed one bounded editorial probe. It followed corrections but produced an abstract-like opening, so this does not qualify it as the show's final editor. [Probe assessment](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/local-editor-assessment.md).

Evidence: [Claude backend](/Users/tanner/Developer/earworm/src/earworm/claude.py:77), [daily log](/Users/tanner/Developer/earworm/logs/daily.log:948), [pipeline config](/Users/tanner/Developer/earworm/config/pipeline.toml:13), [Badlands model decision](/Users/tanner/Developer/manabase/decisions/0019-local-open-models-on-badlands.md), and live tailnet, SSH, HTTP, GPU, and launchctl checks. The GPU decision contains older single-sample performance figures; no throughput claim is made here.

## Recommended first routing

Use a small runner interface with explicit backend, provider, model, timeout, and fallback for each stage. Preserve the current files and atomic staging boundary. Pi is the model/tool harness; it does not make a hosted call free.

| Work | First route | Why |
| --- | --- | --- |
| Topic discovery and research | Pi, OpenRouter `deepseek/deepseek-v4-flash-0731` | Test a low-cost API research agent with the actual search/fetch tools and source checks. |
| Evidence review and story commission | Pi, OpenRouter `deepseek/deepseek-v4-pro-0813` | This pass verifies claims and selects the story; both are consequential. |
| Draft, structural review, necessary revision | Pi, the same pinned Pro model | Preserve editorial capacity while testing the new storytelling approach. |
| Semantic deduplication and bounded classification | Pi, `badlands/gemma4:26b` | Existing local route; bounded inputs and explicit outputs are a better initial fit. |
| Word counts, syntax checks, required files | Python | Deterministic checks do not need model calls. |
| Narration | Local engine selected by the separate audition | Kokoro already runs on Tundra CPU; reserve GPU placement for a voice that needs it. |

These are initial trial assignments, not claims of proven podcast quality. If Flash cannot meet the existing research standard on a compared packet, promote research to the Pro API route within the budget. If the Pro draft still sounds generic, compare another explicitly priced API model through Pi before adopting it. Do not treat cheaper calls as success when they require more repairs or produce worse episodes.

The suffixes matter. Direct DeepSeek's `deepseek-v4-pro` and `deepseek-v4-flash` currently point to its 0813 and 0731 releases. OpenRouter's unsuffixed V4 names still identify older 0423 releases. Use the pinned OpenRouter IDs above. [Direct model table](https://api-docs.deepseek.com/quick_start/pricing/), [OpenRouter Pro](https://openrouter.ai/deepseek/deepseek-v4-pro-0813), [OpenRouter Flash](https://openrouter.ai/deepseek/deepseek-v4-flash-0731).

## Bounded fallback and spending

First allow OpenRouter provider failover for the same pinned model, requiring supported parameters and explicit token-price ceilings. Then permit at most one application-level alternate attempt through direct DeepSeek of the same tier for a transport outage, persistent 429, or 5xx, if that API route is configured. Keep attempts inside one stage deadline and the remaining episode budget. Do not silently downgrade editorial work to the local model. Stop on authentication failure, exhausted funds, an invalid request, or the spend cap. Preserve the unfinished packet for a later run. [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [limits](https://openrouter.ai/docs/api_reference/limits).

Avoid nested retry multiplication across Earworm, Pi, the SDK, and the provider router. Account for guard canaries as well as the actual task. The existing [Manabase Pi wrapper](/Users/tanner/Developer/manabase/scripts/pi-run.sh) guards explicit OpenRouter calls only; do not route local or direct DeepSeek calls through it or remove its checks to make another route work.

Use an Earworm-specific API key limit plus an application budget per episode. A token-price ceiling alone does not cap a long research run. Choose the initial dollar cap from the measured pilot before unattended activation; no key was created or budget imposed in this exploration. DeepSeek/OpenRouter fallback credentials must be checked for readiness without printing secrets.

September 5 reference prices, USD per million tokens:

| Route | Uncached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| OpenRouter Flash 0731, catalog snapshot | 0.065 | 0.016 | 0.18 |
| OpenRouter Pro 0813, catalog snapshot | 0.57948 | 0.019316 | 1.73844 |
| Direct DeepSeek Flash, off-peak | 0.22 | 0.007 | 0.66 |
| Direct DeepSeek Pro, off-peak | 0.66 | 0.022 | 1.98 |

OpenRouter catalog prices are advertised rates, not guaranteed selected-provider prices; actual routing and promotions may differ. Direct DeepSeek peak prices are twice these off-peak prices. Its published peak windows are weekdays 01:00–04:00 and 06:00–10:00 UTC; the current 07:00 Pacific schedule falls outside them. Recheck before activation. Sources: [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/), [OpenRouter live catalog](https://openrouter.ai/api/v1/models).

## Keep the context and tools small

Use a task-specific system prompt, explicit model/provider, an explicit tool allowlist, and only the required Pi extensions. Do not inherit every coding skill, project context file, or interactive extension into each production pass. Research needs real search and source retrieval; other stages can operate on bounded local artifacts.

The installed `pi-web-access` extension offers `web_search`, `fetch_content`, and stored source retrieval. Pin and test those capabilities rather than assuming Claude's `WebSearch`/`WebFetch` names transfer. Its default search workflow can generate additional summary-model calls and traverse provider fallbacks. Configure a named search route, disable unneeded summary generation, retain actual source text, and include search charges in the ledger. Existing tool availability does not prove equivalent research quality. [Installed extension documentation](/Users/tanner/.pi/agent/npm/node_modules/pi-web-access/README.md:21).

Pass corrected evidence and the editorial commission to the writer and both editing passes. A short packet should retain source anchors and important uncertainty. Cutting those to save tokens would undermine the part of Earworm Tanner wants to keep.

## Measure complete episodes

Earworm currently discards structured LLM results and has no per-stage cost ledger. Record each attempt's requested and actual model/provider, input/cache/reasoning/output tokens, reported cost, wall time, error class, retries, and artifact outcome. Unknown cost stays unknown. Add totals for failed discovery, search, fallback attempts, and TTS wall time. Playback duration is not generation time. OpenRouter provides usage and cost information that can be reconciled by generation ID. [Usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting).

Report local inference as zero API fees, with GPU time separately recorded. Electricity and contention remain costs; they were not measured by our single probe. The 3090 also serves image generation. Schedule voice/LLM trials sequentially, use the existing GPU coordination policy, and check full GPU residency at the requested context. Do not assume two individually fitting models fit together.

## Trial and activation checks

First compare an API-generated draft on the same corrected packet used in the editorial pilot. Then run one complete API/local pipeline in an isolated directory. Check source fidelity, story quality, narration, actual total cost, and behavior when a provider is unavailable. No comparison with the existing Claude account is required to produce the new episode.

Before unattended activation, verify: all stages including autogen, dedup, ingest adaptation, and fallback routes use explicit permitted backends; no Claude binary/auth is needed; errors retain their useful cause; retries and caps stop as intended; resumes use the intended current artifacts; and a failed stage cannot enter the watched inbox. Preserve source-author wording on the separate ingest path. Keep a single producer on Tundra and verify the next scheduled episode end to end after the routing change.

A full-pipeline run without Claude is the acceptance test. Merely adding Pi as an option would not satisfy the requirement.
