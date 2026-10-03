# Voice liveliness and episode bookends, October 3, 2026

Tanner found narration "slightly boring" and episode starts and endings abrupt. The shipping-container episode (#149) stopped on a mid-argument mechanism sentence.

## Why #149 ended abruptly

The automated draft did end with a synthesis paragraph. The manual factual repair on October 3 deleted it, because it repeated an uncertain late-1960s conversion timeline. No replacement ending was written. The prompts also allowed this outcome: they banned morals and sign-offs and said only "end where the material reaches a meaningful stopping point." Separately, production audio had a 0.3 s lead, a 0.6 s tail, a 0.1 s fade and no show identity.

## Changes

- Prompts now require a deliberate ending that resolves the opening in the episode's own specifics. Generic morals and sign-offs remain banned. Script review flags endings that merely stop. Revision must write a new ending when a correction cuts the old one.
- `[bookends]` in `voice.toml` adds an original synthesized cue (the September 5 option A, "rising"), a spoken "Earworm. <title>." line, and a closing cue ("falling", option C). Captions shift by the inserted audio. Without the section, rendering is unchanged.
- `qwen.seed_per_paragraph` offsets the fixed seed by each paragraph's text hash. Delivery can vary between paragraphs while renders and the cache stay deterministic. The default keeps the old behavior.
- Mastering adds high-pass, warmth and presence EQ, a de-esser and gentle compression before loudnorm. Paragraph and section gaps are longer.

## Audition

`audition.py` ran once on Badlands (RTX 3090) and wrote only to `/home/tanner/earworm-audition/2026-10-03-voice`. One fixed three-paragraph passage was rendered four ways:

| Clip | Reference | Seed | Gaps | Mastering |
| --- | --- | --- | --- | --- |
| 0-baseline | approved | 42 every paragraph | 350 ms | loudnorm only (production) |
| 1-seed-mastering | approved | 42 + paragraph index | 550 ms | EQ, de-ess, compression, loudnorm |
| 2-new-ref-same | new: original description, livelier text | as 1 | as 1 | as 1 |
| 3-new-ref-lively | new: more animated description, livelier text | as 1 | as 1 | as 1 |

Measured integrated loudness was -16.1 to -16.4 LUFS. Clips 2 and 3 use new VoiceDesign references, so timbre may differ from the approved voice. The audition used an index-based seed offset, and production would use a text-hash offset; both give each paragraph a different seed. The audition mastering ran EQ before compression, and the production chain runs compression first.

Only one render was made per variant. No speech-to-text tool was available, so omissions and repetitions were not checked automatically. No listening verdict is recorded here. Tanner's choice decides adoption.

The full-episode preview combines the approved reference, the per-paragraph seed, the new mastering and bookends, and a hand-written replacement ending built only from facts already in the corrected script. It is unpublished.
