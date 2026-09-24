# Earworm narration: test delivery before choosing a new voice

Proposal, September 5, 2026. The three Kokoro samples below are generated local experiments. No model installation, deployment, or production setting change is part of this proposal.

A different voice can change how Earworm feels, but it cannot repair an episode that loses its story. The target is more natural delivery with correct proper names and technical terms. Test those separately from the editorial rewrite and music experiments. Use local models or an explicit speech API; narration must have no Claude dependency.

## Listen to the existing-engine comparison first

Earworm currently uses local Kokoro **0.9.4**, voice **`af_heart`**, speed **1.05**. These clips use the same [audition text](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/voice-audition-text.txt). Their [settings record](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/voice-audition-settings.json) records the renders.

| Sample | Voice | Speed | What it tests |
| --- | --- | --- | --- |
| [A: current Heart](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/a-current-heart.mp3) | `af_heart` | 1.05 | Current voice and speed on the new passage. |
| [B: slower Heart](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/b-heart-slower.mp3) | `af_heart` | 0.98 | Compare with A to judge the speed setting. |
| [C: slower Michael](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/c-michael-slower.mp3) | `am_michael` | 0.98 | Compare with B to judge the voice at the same speed setting. |

These are roughly one-minute passages, not completed episodes. The author of this proposal has not listened to them. Generated files and successful renders establish availability, not a quality improvement. C versus A changes both voice and speed, so that comparison cannot isolate either choice.

## What Kokoro can change

The current official general checkpoint is **v1.0, January 27, 2025**; the latest published Python package is **0.9.4, April 5, 2025**. Package and checkpoint versions are separate. Both code and weights use Apache-2.0. [Model card](https://huggingface.co/hexgrad/Kokoro-82M), [package](https://pypi.org/project/kokoro/), [code](https://github.com/hexgrad/kokoro).

Kokoro exposes voices, voice blending, speed, segmentation, and pronunciation overrides. It has no documented natural-language delivery instruction field. A direction such as “sound curious, then slow down for the result” must become supported rendering choices; it must never be appended to the spoken text. [Pipeline source](https://github.com/hexgrad/kokoro/blob/main/kokoro/pipeline.py).

Official guidance says most voices work best around **100–200 tokens**, can weaken below **10–20**, and can rush above **400**. These are model tokens, not words. Test sentence-group chunking in that range, deliberate gaps at transitions, and restrained speed changes before assuming a new model is necessary. [Voice guidance](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

**v1.1-zh, February 26, 2025**, adds 100 Chinese voices and three English voices, Maple, Sol, and Vale. Its card explicitly says it is not a strict upgrade and drops many previous voices. Treat it as an optional separate audition, not a replacement checkpoint for `af_heart`. [Official card](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh).

## Ranked local challengers

This ranking reflects documented controls and practical fit for an audition. Naturalness remains a listening judgment; model marketing and parameter counts do not establish it.

| Priority | Candidate and release | Why audition it | License and hardware limits |
| --- | --- | --- | --- |
| 1 | **Qwen3-TTS 12Hz 1.7B CustomVoice**, January 22, 2026. [Repository](https://github.com/QwenLM/Qwen3-TTS), [model](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice). | A separate `instruct` field controls delivery with a fixed stock speaker. Start with native-English Ryan or Aiden. The model matrix does not advertise instruction control for **0.6B** CustomVoice, so use 1.7B for this experiment. | Code and weights: **Apache-2.0**. Official setup uses BF16 and recommends FlashAttention 2 to reduce memory. No official 3090 peak-memory measurement was found in the sources reviewed. A 24GB pilot is plausible from model size, but remains untested. |
| 2 | **Chatterbox**, including English Turbo and Original. Turbo weights updated December 15, 2025; the family's latest broader release is **Multilingual v3, June 10, 2026**. [Turbo model](https://huggingface.co/ResembleAI/chatterbox-turbo), [v3 announcement](https://www.resemble.ai/resources/chatterbox-multilingual-v3-tts-with-embedded-watermarking-for-25-languages). | Original offers `exaggeration` and `cfg_weight` controls. Turbo supports vocal tags such as `[chuckle]`, but its source explicitly ignores those two controls. Compare actual narration delivery rather than adding a quota of vocal effects. [Controls](https://github.com/resemble-ai/chatterbox#original-chatterbox-tips), [Turbo source](https://github.com/resemble-ai/chatterbox/blob/master/src/chatterbox/tts_turbo.py). | Code and weights: **MIT**. Turbo is 350M parameters; an exact official VRAM minimum was not found. Latest PyPI **0.1.7**, March 26, 2026, predates v3, so any v3 pilot must identify its source revision. [Package](https://pypi.org/project/chatterbox-tts/). |
| 3 | **Fish Audio S2 Pro**, March 10, 2026. [Release record](https://fish.audio/ru/app/changelog/), [model](https://huggingface.co/fishaudio/s2-pro). | Free-form inline directions control emphasis, pauses, tone, and other expression. Useful if the simpler auditions cannot deliver the needed variation. | Current **code and weights** use the **Fish Audio Research License**. Research/noncommercial use is free; commercial use requires a separate license. Official inference guidance recommends **at least 24GB VRAM**. The 3090 is at that floor, without assured space for other resident models. [License](https://github.com/fishaudio/fish-speech/blob/main/LICENSE), [hardware guidance](https://github.com/fishaudio/fish-speech/blob/main/docs/en/inference.md). |

Two additional candidates appear in Voicebox's lineup. Their downloadable models justify keeping them available for an audition; neither has been listened to here.

| Candidate | What the primary sources establish |
| --- | --- |
| **LuxTTS**, official weights updated January 23, 2026. [Model](https://huggingface.co/YatharthS/LuxTTS), [repository](https://github.com/ysharma3501/LuxTTS). | Code and weights are **Apache-2.0**. Reference audio, speed, sampling, and smoothing controls are exposed; the reviewed [generation API](https://github.com/ysharma3501/LuxTTS/blob/master/zipvoice/luxvoice.py) has no lexicon, phoneme, or natural-language direction input. The author warns that increasing `t_shift` can improve sound while worsening pronunciation. Test that tradeoff and whole-episode stability; neither the advertised speed nor 48kHz output establishes naturalness. |
| **Hume TADA**, released March 10, 2026. [Announcement and samples](https://www.hume.ai/blog/opensource-tada), [repository and weights](https://github.com/HumeAI/tada). | Downloadable 1B/3B models use the **Llama 3.2 Community License**; code is **MIT**. Text/acoustic alignment targets skipped or repeated content, but does not specify how a difficult name should sound. No dedicated lexicon or phoneme control was found in the reviewed interface. Hume reports occasional speaker drift during long generations despite supporting over ten minutes of context, and suggests resetting context. The README estimates roughly 9GB model memory for 3B in BF16; this is not measured 3090 peak usage. |

The RTX 3090 is shared infrastructure. Check available memory and current workloads before any future audition; do not unload services or deploy a new endpoint as part of this proposal. Parameter counts and vendor performance claims do not establish available memory or episode render time on this host.

Qwen's [technical report](https://arxiv.org/html/2601.15621v1) includes internal English/Chinese long-form evaluation with speech exceeding ten minutes. That supports testing it, not assuming a full Earworm episode will remain accurate. Chatterbox's inspected Turbo implementation has a bounded generation loop; Fish advertises long-context synthesis. All candidates still need checks for omissions, repetition, changing voice identity, and audible chunk boundaries.

## Delivery contract and audition sequence

Keep clean spoken prose separate from speaker choice, delivery directions, pronunciation information, and audio assembly instructions. Each engine adapter must translate only the controls it supports. Preserve Kokoro's pronunciation frontend; do not blindly pass its phoneme hints to another model. Likewise, Qwen instructions and Fish or Chatterbox tags must not enter Kokoro's spoken text. Unknown controls should be reported, not silently read aloud.

Pronunciation needs its own small, reusable vocabulary record: the correct written term, intended pronunciation and its source, language/context, engine-specific rendering, and an accepted audio example. Keep respellings out of the published transcript. Verify a person's name against their own speech or an authoritative recording when available. Avoid treating an automatically guessed pronunciation as an approved entry.

| Engine | Verified pronunciation interface | What remains to test |
| --- | --- | --- |
| Kokoro | Its official example uses an inline phoneme override, `[Kokoro](/kˈOkəɹO/)`, interpreted by the Misaki frontend. [Example](https://github.com/hexgrad/kokoro#usage). | Render each term in a sentence, with the selected voice. The engine's phoneme alphabet must be respected. |
| Qwen3-TTS 1.7B | The reviewed API documents text, speaker, language, and delivery instructions; no dedicated pronunciation lexicon or phoneme override was found. [API source](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/inference/qwen3_tts_model.py). | Treat spelling variants and pronunciation directions as experiments, not exact controls. Check whether a correction survives repeated renders and different sentence contexts. |
| Chatterbox | The reviewed local API exposes text and reference conditioning, without a documented phoneme or lexicon input. An August 15, 2026 [open feature request](https://github.com/resemble-ai/chatterbox/issues/550) reports this limitation; it is a user report, not a maintainer guarantee. | Test engine-specific respellings and their consistency. Hosted Resemble vocabulary features must not be assumed to exist in local Chatterbox. |
| Fish S2 Pro | Fish documents English CMU Arpabet between `<\|phoneme_start\|>` and `<\|phoneme_end\|>`. S2 Pro's tokenizer includes those tokens. [Control docs](https://docs.fish.audio/developer-guide/core-features/fine-grained-control), [S2 tokenizer](https://huggingface.co/fishaudio/s2-pro/blob/main/tokenizer_config.json). | The control page also refers to v1.6. Token presence does not prove accurate S2 pronunciation; verify the exact local checkpoint on Earworm terms before depending on it. |

The existing clips test delivery on an accessible passage. Use the [technical-term audition text](/Users/tanner/Developer/earworm/docs/experiments/2026-09-05-story-pilot/pronunciation-audition.txt) as a second fixture, then add difficult names from the actual episode being produced. It deliberately includes terms with existing lexicon entries and terms that still need an accepted pronunciation. A spelling in this fixture is not a pronunciation verdict.

## Voicebox as an audition and synthesis tool

[Voicebox](https://github.com/jamiepine/voicebox) is useful for comparing engines through one interface. Inspection of commit `51f49dea198384b4eb6087b72c17057c6eb1c1cd` confirmed a standalone Linux/FastAPI backend, generation and status endpoints, model load/unload controls, and remote-backend support. Its local generation path requires neither Voicebox Cloud nor a Claude account. Code is MIT; the selected model retains its own license. These capabilities were checked in source, not deployed on Badlands. [Backend](https://github.com/jamiepine/voicebox/blob/51f49dea198384b4eb6087b72c17057c6eb1c1cd/backend/README.md), [request controls](https://github.com/jamiepine/voicebox/blob/51f49dea198384b4eb6087b72c17057c6eb1c1cd/backend/models.py#L79-L102).

Use it first as the audition interface. If a voice wins, its backend can become Earworm's synthesis endpoint. Keep Earworm responsible for approved prose, canonical transcript text, pronunciation rendering, chunk identity, mastering, and publication. Voicebox currently has no common pronunciation dictionary or IPA/alias request field, and its guide lists SSML and word timing as forthcoming. Its merged auto-chunks do not return a chunk timing map; generate stable sentence groups separately if we need to correct a term without regenerating the whole episode. [Documented limitations](https://github.com/jamiepine/voicebox/blob/51f49dea198384b4eb6087b72c17057c6eb1c1cd/docs/content/docs/overview/generating-speech.mdx#L60-L65), [chunk merging](https://github.com/jamiepine/voicebox/blob/51f49dea198384b4eb6087b72c17057c6eb1c1cd/backend/utils/chunked_tts.py#L309-L347).

The screenshot's instruction feature needs one qualification: the ordinary Qwen path loads Base cloning models; our instruction experiment should select **1.7B CustomVoice**. A displayed instruction field alone does not establish that a backend uses it. When Earworm supplies approved text and handles mastering, disable Voicebox personality rewriting, normalization, and effects. Coordinate GPU use with Ollama and image generation; Voicebox's own sequential queue does not coordinate those other services. [CustomVoice call](https://github.com/jamiepine/voicebox/blob/51f49dea198384b4eb6087b72c17057c6eb1c1cd/backend/backends/qwen_custom_voice_backend.py#L186-L210), [personality rewriting](https://github.com/jamiepine/voicebox/blob/51f49dea198384b4eb6087b72c17057c6eb1c1cd/backend/routes/generations.py#L79-L99).

## Next auditions

1. Listen to A versus B, then B versus C. Record where attention changes, whether the pace feels rushed, and which voice makes another minute appealing.
2. Audition Qwen 1.7B on the same passage with neutral delivery and one restrained direction. Keep text and mastering fixed. Record the exact model revision, speaker, settings, and available hardware. Add Chatterbox only if the first comparison leaves a useful question unresolved.
3. For promising settings, repeat an opening, a dense technical explanation, and a turning point, including the pronunciation excerpt. Check words against the input and log pronunciation, omissions, repetitions, seams, peak VRAM, and render time. Listen for natural emphasis, pauses, and sentence endings. Repeated runs are necessary before claiming speed or reliability gains.
4. After a voice preference emerges, render one complete unpublished episode and listen through it. Keep music out of this comparison. Then use the separate intro and back-to-back transition prototypes to judge how the chosen narrator enters and leaves an episode.

Official examples are available for [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/SAMPLES.md), [Qwen](https://huggingface.co/spaces/Qwen/Qwen3-TTS), [Chatterbox Turbo](https://resemble-ai.github.io/chatterbox_turbo_demopage/), [Original Chatterbox](https://resemble-ai.github.io/chatterbox_demopage/), and [Fish](https://fish.audio/). These links are references, not evidence that the author listened or that local output will match them.

Watchlist: **Qwen-Audio-3.0-TTS** has a July 27, 2026 [report](https://arxiv.org/abs/2607.23938) describing delivery instructions and inline tags. Hosted availability and downloadable weights are separate questions; downloadable weights were not verified in this review. Do not substitute it for the January local Qwen3-TTS release in an implementation plan.
