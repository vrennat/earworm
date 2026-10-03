# Editorial release validation, October 3, 2026

The user authorized completing the fixes, committing, merging, and deploying. This receipt supplements the October 2 archive audit; it records model diagnostics separately from deterministic checks and production verification.

## Changes

The existing five-pass chain remains. The release supplies full-archive novelty coverage, separate recent and upcoming context, projected slate guidance, within-batch semantic screening, an explicit evidence-review PROCEED/HOLD contract, and a duplicate screen on the selected commission before writing. It also aligns feed descriptions with final narration and permits correcting a misleading title. The configured tool-call cap blocks excess calls while allowing the bounded final artifact request; it does not raise request, time, input, or spending limits.

Production model routes, voice, budgets, and scheduling remain unchanged. The deployment replaces only changed source files, prompts, and the reviewed personal interests. Queue changes preserve the redundant cable-repair topic as failed with an editorial deferral note and add four neutral leads: container standards, certificate trust, antibiotic procurement, and overlapping speech. The remaining proposed questions stay in the reviewable topic slate.

## Fixed semantic diagnostics

All 24 proposals matched the predeclared duplicate labels in one run per batch using the current production local judge:

| Fixture | Proposals | Expected duplicates | Result | Seconds | Judge calls |
| --- | ---: | --- | --- | ---: | ---: |
| Original baseline A | 4 | 2, 3 | matched | 27.761 | 3 |
| Original baseline B | 4 | 1, 3 | matched | 6.663 | 3 |
| Original baseline C | 4 | 1, 3 | matched | 6.964 | 3 |
| Full archive recovery | 4 | 1, 2 | matched | 7.319 | 3 |
| Batch overlap | 4 | 2 | matched | 4.496 | 5 |
| Opening slate | 4 | none | matched | 7.787 | 4 |

A later candidate changed the duplicate definition. Its one-run regression matched 23 of 24 labels, missing the cable case, and still failed to stop the reframed reactor commission. That candidate wording was discarded; the final archive prompts retain the definition used for the 24-case table. No extra reruns were used to select a better number.

These are small, deliberately chosen diagnostics, not a general accuracy estimate or a latency benchmark. There is no repeated sample for variance. The initial call includes a cold-model effect that was not isolated experimentally. Raw receipts are retained in the private release workspace on Badlands and the local `.lab` archive.

## Fixed-packet editorial pilots

No web tools were available during these pilots; they evaluated the original source packets and only prior episode excerpts. The first exploratory run accidentally used short case labels as topics. Its writing output remains useful for finding defects, but is not an unconfounded comparison. A corrected run with the original queued topics returned PROCEED for SQLite, HOLD for the unavailable study, and PROCEED for the reactor follow-up.

The reactor reviewer replaced unavailable contract evidence with the previous episode's rights-transfer story. One targeted prompt repair still returned PROCEED by reframing the same event as seller behavior. The separate duplicate shortlist correctly identified the repeated story, but its confirmation model overruled the match based on the changed interpretive framing. Tightening the duplicate definition did not repair that override. The final commissioning policy therefore holds a possible return to one of the last three stories for inspection using one bounded shortlist call; discovery still uses two-pass confirmation across the full archive. This deliberate cooling-off policy may defer a worthwhile follow-up, but does not allow a speculative reframe to overrule detected recent overlap. The final gate held the preserved reactor commission as possible overlap and passed the SQLite commission in one run each. All failed attempts are retained; the gate is not reported as a general improvement in model judgment.

The SQLite writing pilot developed the presentation-file example and avoided retrieval-process narration, but overstated the sufficiency of journal deletion, presented hypothetical autosave latency as realized, and made proposed document versioning sound like a built-in feature. One targeted script-review/revision diagnostic with stronger general criteria restored locking, ordered writes, and flushes; it did not fully repair the other qualifications. No repeated attempts were made to obtain a cleaner result. This is an unresolved model editorial limitation, not a factual-quality pass. These private artifacts were not published.

Recorded conservative budget charges (including reservations for unknown charges, not necessarily billed cost): exploratory three-case review plus SQLite writing $1.064802; original-topic three-case review $0.23630145; targeted reactor review $0.08567645; targeted SQLite editing $0.5439588. Each used the unchanged $2 aggregate cap. Local classification has no API charge. This work did not establish improved listening quality; no audio comparison was performed.

## Verification

The 17 standalone test files, source/wheel build, lockfile check, and Worker typecheck passed before integration. Production-environment tests use the pinned Qwen Python environment without synchronization. The parser fixture uses the deployed web-access package through `EARWORM_TEST_WEB_ACCESS_PATH`; all 22 LLM tests pass there without skips. The commission gate adds tests for fresh and resumed review, possible recent overlap, malformed commissions, judge/schema errors, distinct commissions, and disabled review.

## Deployment

Commit `5de03247ad9b6febe9c5a442551bbfd718d104fe` was fast-forward merged into `main` after fetching the current remote, tested on integrated `main`, and pushed. All 17 standalone suites passed locally and in the pinned production environment. The source distribution/wheel build, lockfile check, and Worker typecheck passed. [GitHub CI for that exact commit](https://github.com/vrennat/earworm/actions/runs/37106768452) passed both jobs.

The Badlands rollout verified the original production hashes before replacing 17 scoped files. A private file backup and SQLite online backup reside at `/opt/stacks/earworm/releases/2026-10-02-editorial/production-backup`. The watcher and daily timer were stopped for the source/prompt and queue transaction, then restarted successfully. Configuration hashes were unchanged. Topic #164 was preserved with an editorial deferral; new topics #165–168 were inserted in the reviewed order. A normal daily-service run was started for #165, container standards.

The normal producer completed research, review, a `new` commission screen, writing, script review, and revision for #165. Before publication, an independent full-text comparison found three overstatements: an absence of industry agreement where the report described partial settlements, an unsupported claim that twist-locks eliminated manual lashing, and an uncertain late-1960s conversion timeline. The watcher was stopped while the episode still had no rendered ledger row. Four narrow replacements corrected narration and description and narrowed the ending to the documented return-route mechanism. The original script was backed up, all replacements were recorded with hashes, an independent recheck confirmed they resolved the findings, and the watcher restarted.

This first production sample therefore includes manual editorial correction. It verifies the deployed runtime path, not fully autonomous factual quality. The original automated output, corrections, and diagnostic failures are preserved in the private release archive. No voice change or audio quality claim is implied.

Narration initially waited for the local Gemma model retained by Ollama for 30 minutes after Earworm's own completed classification. Server logs showed no later inference request, model expiry was unchanged, and the GPU was idle. A one-time native `/api/generate` request with `keep_alive: 0` released that identified completed workload; the response reported `done_reason: unload` and `/api/ps` was empty. This is the [documented native unload operation](https://docs.ollama.com/faq), not a change to fleet retention settings. The deployed Ollama 0.33.2 OpenAI compatibility request [does not carry a keep-alive field](https://github.com/ollama/ollama/blob/v0.33.2/openai/openai.go), so an unverified extra parameter was not added to Pi. Future runs retain the existing conservative GPU wait and retry behavior and may wait for the shared model's idle expiry; automatic eviction was not introduced.

Episode #149, **How the Shipping Container Got Its Size**, published at `2026-10-03T07:57:19Z` with a duration of 453.72 seconds. The daily service reported success. The live feed returned HTTP 200 and contained the episode with its corrected title and description; the audio URL returned HTTP 206, `audio/mpeg`, and a valid MP3 header for bytes 0–1023 of 7,271,975. The 17 deployed file hashes match the release, configuration hashes remain unchanged, and watcher/timer are active. The next daily trigger remains October 3 at 07:00 Pacific. Three pending leads remain (#166–168). The production run's conservative ledger charge was $1.045784528, below the unchanged $2 run cap.

See the [sanitized deployment receipt](2026-10-03-editorial-deployment.json) for hashes and live checks. Publication and audio delivery are verified; improved listening quality and fully automatic factual fidelity remain unproven.
