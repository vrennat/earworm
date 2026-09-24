# Earworm rethink: story, cost, and sound

September 5, 2026. These are proposals and isolated experiments. No production code, models, account settings, schedule, or published episodes were changed.

The target is an engaging, natural-sounding show that works for back-to-back listening and runs without Tanner's Claude account. Keep the research depth, let each subject determine the episode's structure, and use the existing fleet before adding infrastructure. A consistent production process must not impose predictable spoken sections; rotating among templates is insufficient.

| Decision | Recommendation | Evidence and detail |
| --- | --- | --- |
| Storytelling | Choose an editorial focus before drafting; let the material determine structure and allow the final editor to rebuild it. | [Editorial proposal](/Users/tanner/Developer/earworm/docs/specs/2026-09-05-editorial-pipeline-design.md), [full listening pilot](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-api-pilot/README.md). |
| Cost and independence | Keep Tundra as producer; use Pi with explicit OpenRouter/DeepSeek API routes and Badlands for bounded local jobs. No Claude fallback. | [Runtime proposal](/Users/tanner/Developer/earworm/docs/specs/2026-09-05-execution-and-cost-design.md), [one local editorial probe](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/local-editor-assessment.md). |
| Natural voice | Use Voicebox to audition Qwen 1.7B CustomVoice against current Kokoro, then test the promising alternatives. | [Voice and pronunciation proposal](/Users/tanner/Developer/earworm/docs/specs/2026-09-05-narration-design.md). |
| Pronunciation | Keep canonical transcript text separate from an engine-specific, reusable pronunciation record and corrected audio chunks. | [Technical-term fixture](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/pronunciation-audition.txt). |
| Episode boundaries | Test a short original musical cue and a clean gap, starting with option A. | [Cue reel](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-audio-identity/three-cue-audition.mp3), [boundary preview](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-audio-identity/episode-boundary-preview.mp3), [production details](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-audio-identity/README.md). |

There is an immediate reliability reason for the API change: today's scheduled topic generation hit the shared Claude session limit in four attempts. The watcher is running, but no September 5 episode was generated. This was diagnosed, not repaired or retried during the exploration.

The 3090 route is already operational. Our one Gemma test preserved several factual corrections, but its opening was generic. It establishes a usable local route, not a publishable local writer. Current API prices are documented; actual cost per new episode still needs a full measured run.

Three local Kokoro auditions are ready: [current Heart](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/a-current-heart.mp3), [slower Heart](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/b-heart-slower.mp3), and [slower Michael](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/c-michael-slower.mp3). New engines were researched but not installed or auditioned. No generated clip is being claimed as more natural before listening.

The [complete unpublished pilot](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-api-pilot/README.md) exercised API drafting and review plus local narration, with substantial Codex editing and reused, rechecked research. It does not yet prove an unattended editorial pipeline. The next editorial test should compare episodes on different subjects back to back, checking whether their shapes feel dictated by their material. A same-text voice audition using the difficult-term fixture remains separate work before the daily producer changes.
