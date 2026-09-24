# Earworm: choose the story before writing the script

Proposal, September 5, 2026. No production changes made.

Earworm should make episodes Tanner wants to finish. The immediate work is to prove a better editorial approach on existing research, then carry the successful approach into the five current passes.

## What is going wrong

The current scripts already contain hooks, opinions, jokes, and surprising facts. Their recurring weakness is what happens between the opening and closing: a succession of findings and caveats, sometimes followed by a late announcement that another subject was the real story. More energetic prose alone would preserve that experience.

This assessment covers six completed scripts from August 22 through September 4, 2026, plus current prompts and orchestration. It is a text audit, not an assessment of the recordings or a statistical study of the feed.

| Current behavior | Evidence | Editorial consequence |
| --- | --- | --- |
| Research returns a thesis and three to six surprising findings. | [research.md](/Users/tanner/Developer/earworm/prompts/research.md:21) | The writer inherits the organization of a briefing. Documented events, decisions, chronology, and consequences are optional discoveries. |
| Episode ID determines one of five structures. | [pipeline.py](/Users/tanner/Developer/earworm/src/earworm/pipeline.py:229) | A structure is assigned without asking whether its necessary material exists. |
| Research review finds neglected threads but leaves the writer to choose among all criticisms. | [review.md](/Users/tanner/Developer/earworm/prompts/review.md:5) | Useful editorial discoveries do not become a committed story. |
| Nearly every sentence must add information; restatement and emphasis are broadly prohibited. | [_voice.md](/Users/tanner/Developer/earworm/prompts/_voice.md:23) | The rules can remove orientation, callbacks, and changes of pace along with filler. |
| Revision must use line edits and avoid wholesale rewriting. | [script_revise.md](/Users/tanner/Developer/earworm/prompts/script_revise.md:7) | A weak middle can receive clean sentences without getting a better structure. |

Specific examples make the problem visible. The protein episode opens with protein binders, reaches the file-format problem much later, and ends by calling itself a file-format story. The Claude usage episode announces its larger story late. The silent-corruption episode leaves a strong hardware experiment to begin another tour through mislabeled datasets and benchmark contamination. These topics are related, but their relationship alone does not make the second topic a necessary development in the first story.

Sources: [protein script](/Users/tanner/Developer/earworm/done/scripts/2026-08-25-0124-protein-design-meets-wet-lab-workflow-what-changes-when-clau.md:23), [Claude usage script](/Users/tanner/Developer/earworm/done/scripts/2026-09-04-0134-external-research-access-to-claudes-real-world-usage-pattern.md:25), [silent-corruption script](/Users/tanner/Developer/earworm/done/scripts/2026-09-03-0133-silent-data-corruption-in-training-pipelines-if-corrupt-trai.md:21).

## Direction

Use ColdFusion as a reference when the evidence supports a story through causes and consequences. An explanation or comparison does not need an investigation wrapped around it. Borrow compression and changes of pace where they serve the material. Earworm still needs its own voice and an approach that works without a screen.

Tanner's central requirement is that episodes should not feel formulaic. A consistent production process can support this, but a rotation of outlines will not establish it. Even the [full pilot](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-api-pilot/script.md) remains easy to describe as incident, definition, study, results, caveat, practical takeaway. Its substantive prose edit does not by itself demonstrate a less predictable show.

Keep the evidence checks and editorial standards consistent. Let the material determine the episode's order, pace, length, and ending. Before drafting, choose what is worth following and why the listener would want the next development. That might involve a decision, an investigation, a technical idea, or a supported argument; these are examples of material, not formats to rotate through. A question, surprise, callback, joke, or neatly resolved conclusion is useful only when this episode earns it. None should be a required slot.

Review recent episodes together for recurring moves: always defining the subject just after the hook, interrupting each result with a caveat paragraph, announcing a reversal at the same point, or closing on the same sort of lesson. Shared structure is not automatically a defect. Flag the repetition when it makes the next section feel inevitable or makes different subjects sound interchangeable. Repair the underlying selection and ordering of material; do not manufacture novelty through random reordering, withheld context, invented suspense, or cosmetic variation in phrases.

| Reference | Useful technique | Earworm application |
| --- | --- | --- |
| [ColdFusion, WorldCom](https://www.youtube.com/watch?v=u_rfIboPyYs) | The caption sequence moves from collapse to origins, growth pressure, accounting decisions, and discovery. | Explain a mechanism when it becomes necessary to understand a decision or result. Return to an earlier detail after its meaning changes. |
| [Fireship, Git Explained in 100 Seconds](https://www.youtube.com/watch?v=hwP7WQkmECE) | Chapters give a narrow explanation a sequence of actions and a firm boundary. | Give each technical explanation one job. Finish it and return to the story. |
| [TechLinked, Oh, Snap](https://www.youtube.com/watch?v=nHr2aSFV_A4) | A sustained lead package gives way to a run of brief items. | Let developments earn different amounts of attention. Use audible transitions and occasional dry observations to vary pace. |

These are editorial inferences from creator descriptions, chapters, and [reproduced ColdFusion captions](https://rosetta.to/u/coldfusion/when-greed-goes-too-far-the-worldcom-fraud), not a viewing or listening study. The caption mirror warns about errors; its generated timestamps were not used. Music, visual jokes, and human banter require separate listening experiments.

## First change: give existing passes editorial responsibility

Keep the current five-pass architecture. Change the handoffs and the editing authority.

1. **Research gathers evidence that can support a story.** Keep the research depth and source checks. Add documented events, decisions, constraints, results, and unresolved causal questions where they exist. An experiment can supply the action in a technical episode; a person, villain, or dramatic scene is never mandatory. Seek useful chronology and context without forcing every topic into history or a debunk.
2. **Research review checks the facts and commissions an episode.** Preserve the full actionable factual review. End it with a clearly separated editorial brief: what is worth following, why this subject merits attention, how the supported material can develop, source anchors, and material to omit. Name a question or intended payoff when the material supports one; do not force every episode into a mystery followed by an answer. The brief is an internal planning aid, not a sequence of required spoken sections. Use existing research tools to resolve a specific missing fact when possible. The brief must follow the corrected evidence. Remove ID-based structure assignment.
3. **The writer follows that brief.** Each major section must contribute to the chosen episode: develop an event or argument, explain something the listener now needs, or change the meaning of an earlier detail. Related findings may stay in the report without entering the episode. Use recent episodes during story selection as well as writing, so repeated premises, pacing, and endings can be noticed before prose is drafted. Do not assign a different format merely to fill a rotation.
4. **Script review edits the story before the sentences.** Ask where the episode loses what made it worth following, explains something too early, changes subjects without a reason, or fails to develop its central material. Check for recurring structural moves across recent episodes, with specific examples rather than a novelty score. Give this pass the report and research review so suggested changes have an evidence basis. Then check spoken clarity and factual fidelity.
5. **Revision may rebuild the affected sections.** Allow reordering, cutting a subplot, replacing an opening, and rewriting a middle. Preserve claim qualifications and source support. Check the revised artifact for resolved review findings and factual drift before it enters the existing atomic handoff.

The commission can initially live inside `review.md`; a new agent, database, or service is unnecessary. The separate brief in the example is a review aid. For older packets or runs with research review disabled, the writer should first derive an explicit brief from the available evidence, with no claim that it has been independently checked. Preserve those existing configuration options.

## Voice changes

Replace the requirement for constantly climbing excitement and the arbitrary density percentage with purposeful variation. Permit a brief restatement when it reconnects the listener to the main question. Permit a callback when a later fact changes an earlier detail's meaning. Keep humor when the observation earns it, without a joke quota.

Keep the specific protections against invented experience, fabricated suspense, unsupported claims, repeated stock phrases, and pronunciation mistakes. The evidence can support curiosity, admiration, tension, frustration, or a satisfying explanation. Uncertainty belongs beside the claim it limits; it need not become the ending of every episode.

Distinguish an attributed account of what a company said or did from independent proof that its claimed outcome is true. A documentary can use the former as an event while still demanding stronger evidence for the latter. Do not upgrade vendor claims to established outcomes.

## Prove it with a listening pilot

Start with the September 3 silent-corruption research packet. Its experiment provides a concrete sequence, and keeping the episode about that experiment gives us a clear editorial change to assess. The [example brief and opening](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/silent-corruption-example.md) make that proposal tangible; they are not a finished replacement episode.

For the first full pilot, use the same research packet, narrator, speed, and mastering as the original. Keep a comparable duration where the material supports it; log any substantial shortening as a second change that could affect preference. Put all draft and rendered outputs in the experiment directory, outside the watched inbox. The existing regeneration helper writes into that inbox and is unsuitable for an unpublished comparison.

Tanner's listening response decides whether this is better: where attention drops, what makes the next development worth hearing, whether the ending feels earned, and whether he wants another episode. Also ask whether he starts anticipating the script's moves. An automated quality score cannot establish that. Once one pilot works, try the approach on the protein-workflow episode and listen to them back to back to check that the process has not simply produced another hardware-mystery template. Two examples are a taste check, not evidence of a measured retention gain.

## Acceptance and boundaries

- A brief chooses what the episode follows and a supported way to develop it before prose is drafted; a question-and-answer structure is optional.
- Each major development has an evidence anchor and a reason to appear at that point; decorative scenes and invented causality fail review.
- The revised episode develops its chosen material through the middle and ends for a reason grounded in that material, without a mandatory moral or recap.
- Consecutive pilots are reviewed for recurring openings, section order, pacing, and endings. A repeated move needs a reason in the material; superficial variation does not resolve an interchangeable outline.
- Editorial review can request structural repairs, and revision actually makes them without adding unsupported details.
- The pilot works with the existing solo voice; changes to music, multiple hosts, or TTS are separate experiments if listening points there.
- Before a production rollout, test corrected-evidence handoffs, legacy/disabled-review behavior, resume behavior, and the existing atomic staging boundary. Verify final scripts by complete readback and appropriate format checks.

Hold narration and research material constant for the story comparison. The separate [execution proposal](/Users/tanner/Developer/earworm/docs/specs/2026-09-05-execution-and-cost-design.md) removes all dependence on the Claude account, and the [narration proposal](/Users/tanner/Developer/earworm/docs/specs/2026-09-05-narration-design.md) covers voice and pronunciation auditions. [Musical boundaries](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-audio-identity/README.md) address back-to-back listening.

Discovery currently favors recent papers and bare topic strings, which may also constrain story variety. Revisit topic selection after a successful pilot identifies the kinds of material the new editorial process actually needs. Keep changes to publishing cadence and source-author ingest wording outside the editorial redesign. Editorial implementation scope is prompts plus the context plumbing and checks those handoffs require.

The first decision is whether this produces an episode Tanner wants to finish. That result should guide the pipeline changes.
