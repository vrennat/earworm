# Earworm editorial pass, October 2, 2026

Earworm needs better selection and firmer decisions about whether its evidence earns an episode. It already has broad interests and an evidence-led five-pass chain. The clearest failures require better selection and enforceable handoffs; style guidance alone is insufficient.

This pass inspected the live Badlands inventory, compared deployed prompts and relevant orchestration with the local checkout, read 15 complete scripts, and prepared local changes. Production source and local source matched before these edits. The local database was stale and was not used as the current editorial inventory.

## What the archive says

The registry records 140 published episodes. Excluding five imported readings and one personal interview-preparation episode leaves 134 original episodes. A manual title/topic/description census classifies 103 as AI-led, including AI infrastructure and power stories. The latest 30 contain 27 AI-led episodes. This is a descriptive census with judgment at category boundaries, not a sampled estimate of quality.

The close-reading sample is 15 complete scripts, including 14 published episodes and one archival alternative. It is deliberately varied and nonrepresentative. No audio listening or external fact-check was performed in this pass.

| Finding | Concrete evidence | Consequence |
| --- | --- | --- |
| Broader labels do not ensure broader listening | AI power, GPU software, and AI policy occupy nominally different lanes while retaining an AI center. | Count AI across lanes and develop the existing non-AI interests on their own terms. |
| The sequence is not planned as a sequence | The old prompt used a mixed archive; discovery proposes a buffer of four for a one-episode shortfall. | Give discovery recent episodes and future commitments separately, then project the entire slate. |
| Old stories disappear from novelty checks | The last-80 archive omitted earlier cable repair and CUDA episodes. | Retain the full main-feed archive rather than allowing age alone to make a topic new. |
| Missing research becomes the episode | The September 21 script says its study's methods and conclusions were unseen, then discusses generic evaluation requirements. | Let evidence review halt a commission before writing. |
| A changed question can still repeat the same episode | September 30 and October 1 revisit the same reactor, Microsoft deal, transmission delay, and rights transfer. | Compare cases and explanations within a proposed slate as well as question wording. |
| Strong detail becomes a literature survey | Recent scripts enumerate models, benchmarks, and exact deltas; SQLite instead explains one familiar object through a causal sequence. | Develop a supported example; keep quantities that change the explanation. |
| A title can survive after its premise disappears | September 25's title promises a $2 trillion shock absent from its body. | Review titles and allow a corrected title during revision. |

See the [full archive audit](2026-10-02-archive-audit.md), [classification ledger](2026-10-02-archive-classification.csv), and [topic audit and 16-question slate](2026-10-02-topic-slate.md) for provenance, examples, and proposed queue dispositions.

## Local changes

The first choice is to keep the five existing passes and their evidence handoffs. Prompt changes alone cannot prevent a writer from proceeding after the reviewer admits it has insufficient evidence, so this pass also adds a small explicit decision at that existing handoff.

- **Discovery context:** a complete default-feed novelty archive, a separate ten-episode rendered history, and staged/running/pending commitments in projected execution order. Failed leads and private previews do not count as heard coverage. Named reading feeds no longer distort the mix. Actual publication and listening are not inferred from rendered rows.
- **Selection guidance:** retain the 2/2/2/4 lanes, aim for at least four genuinely non-AI episodes in ten, vary subdomains, update the projected window after each proposal, and account for paper promotion. No mandatory story-template rotation. The prompt checks its proposals against one another and asks for researchable questions rather than claims already decided.
- **Research and commissioning:** verify the queued premise first; distinguish missing access from a substantive unknown. Review begins with exact `EPISODE: PROCEED` or `EPISODE: HOLD`. Missing/malformed decisions also halt the run. A hold retains the evidence and marks the topic failed; there is no automatic replacement episode or paid retry.
- **Writing and editing:** ask for a developed mechanism or example, reduce inventories of results, keep retrieval logs out of narration, and check that title and ending fit the surviving evidence. Revision may correct a misleading title while preserving other frontmatter values.

The updated personal interests are in the local, gitignored `interests.md`; a [reviewable copy](2026-10-02-interests.md) is included here. Existing untracked experiments were preserved. During the initial audit no production queue, deployed prompt, model route, voice, or feed was changed. The subsequent authorized rollout is documented in [the release receipt](2026-10-03-editorial-release.md).

## Topic decisions worth making

The pending cable-repair topic #164 is too close to the June repair-fleet episode to run unchanged. The failed shipping-container and construction topics are stronger candidates after removing their assumed conclusions. The failed card-settlement topic needs a narrower question and distance from the recent stock-settlement episode. More reactor/data-center power should wait.

The [proposed slate](2026-10-02-topic-slate.md) starts with container standards, certificate trust, antibiotic procurement, and overlapping speech. Later questions cover inflation measurement, reproducible builds, station costs, multilingual sorting, MRI, water-pipe replacement, heat pumps, and deep-space communications. These are research leads, not claims of verified source sufficiency or new queue entries.

## Small fixed pilot before rollout

Use the same source packets for old and revised prompts so new research does not confound the comparison. These are three diagnostic cases, not an estimate of general model quality:

1. **Supported mechanism: SQLite application files.** The revised commission should preserve the support problem and presentation-file example, explain what changes when saving one slide, and retain the qualification that the editor is a proposed design. No new skeptical twist is needed.
2. **Insufficient evidence: September 21's unavailable study.** The revised reviewer should HOLD the supplied packet. Generic observations about how a benchmark ought to work do not supply the unavailable study's results.
3. **Adjacent repeat: October 1's reactor contract.** The commission should recognize that the known event was just covered and that unavailable contract terms cannot earn the proposed allocation-of-risk answer. Proceed only if the corrected packet contains a distinct explanation worth hearing; otherwise HOLD or defer the topic for new evidence.

For a positive pilot, the listener should be able to say what happens, why it happens, and what the evidence cannot establish. Ask Tanner to compare a fixed small set of complete scripts and then audio with the same approved voice. A more balanced topic table or passing tests does not establish that the episodes are more interesting.

## Verification and remaining limits

- All 17 standalone test files pass, including full-pipeline PROCEED, HOLD, malformed decisions, resumed holds, review-disabled operation, complete-archive recovery, queue ordering, and staged-versus-private script distinctions.
- The Python source distribution and wheel build successfully.
- A deterministic replay against the captured production inventory supplies 137 novelty entries, ten recent episodes, and one active queue item. Discovery is 80,478 UTF-8 bytes against the observed 160,000-byte cap; the four-candidate dedup fixture is 58,562 bytes against 100,000. Both older cable and CUDA entries are present. See the [replay receipt](2026-10-02-discovery-replay.json). This is one snapshot-size measurement, not a latency or quality benchmark.
- An independent code review found the initially omitted scripts awaiting narration. The fix includes watched-inbox scripts and tests their ordering, exclusion after rendering, and separation from private previews.
- The initial audit performed no model generation, paid pilot, narration, listening comparison, push, or deployment. The user subsequently authorized completing the fixes and deploying them; the release receipt records that validation and rollout. Behavior checks establish the gate and context contract, not that a model will always choose HOLD correctly or honor diversity guidance.
- Lane caps and non-AI share remain prompt guidance. Semantic screening now compares archive survivors with earlier accepted candidates, retaining order and excluding dropped candidates from future comparisons. It takes at most two calls per candidate through the shared bounded ledger; the archive is sent once. Semantic accuracy still depends on the model. New descriptions summarize finished narration and retain report Sources; legacy episode rows keep their existing research summaries.
- Full-history input is bounded by the existing backend cap. If growth exceeds it, discovery stops before queue writes. A retrieval/indexing redesign is deferred until archive size warrants its added complexity.
- Deployment must update `prompts/review.md` with the gate code. Existing workspaces preserve local prompts during initialization. New prompts invalidate resume fingerprints on explicit rerun; old reviews without a decision fail closed. Disabling research review explicitly disables the evidence gate.
