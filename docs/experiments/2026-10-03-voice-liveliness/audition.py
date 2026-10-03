"""Unpublished voice-liveliness audition on Badlands. Writes only to OUTPUT.

Variants (same passage, same Qwen Base 1.7B clone model):
  0-baseline         production today: approved reference, seed 42 reset per paragraph,
                     350 ms gaps, loudnorm-only mastering
  1-seed-mastering   approved reference, per-paragraph seed, 550 ms gaps, compression/EQ
  2-new-ref-same     new reference: same voice description, livelier reference text
  3-new-ref-lively   new reference: more animated voice description, livelier reference text
Variants 2 and 3 also use the variant-1 seed, gap, and mastering settings.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUNTIME = Path('/home/tanner/earworm-audition/2026-09-05-qwen')
HUB = RUNTIME / '.cache/huggingface/hub'
OUTPUT = Path('/home/tanner/earworm-audition/2026-10-03-voice')
APP = Path('/opt/stacks/earworm/app')
os.environ.update(HF_HOME=str(RUNTIME / '.cache/huggingface'), HF_HUB_OFFLINE='1',
                  TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1')
sys.path.insert(0, str(APP / 'src'))

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from earworm.normalize import normalize_for_speech

OUTPUT.mkdir(parents=True, exist_ok=True)
RATE = 24000

DESIGN_PATH = HUB / 'models--Qwen--Qwen3-TTS-12Hz-1.7B-VoiceDesign/snapshots/5ecdb67327fd37bb2e042aab12ff7391903235d3'
BASE_PATH = HUB / 'models--Qwen--Qwen3-TTS-12Hz-1.7B-Base/snapshots/fd4b254389122332181a7c3db7f27e918eec64e3'
APPROVED_REF = APP / 'config/earworm-modern.wav'
APPROVED_TEXT = ("Richard Hipp kept getting support calls after operators restarted their equipment. His application "
                 "would start, try to connect to its database, and put up an error. As he later explained on the "
                 "Changelog podcast, the problem was a misconfigured database installation. But the message appeared "
                 "in his application, and that made it his problem to sort out.")

# Same description that produced the approved voice on 2026-09-07.
DIRECTION_SAME = ('An adult female voice with a native contemporary American English accent and a comfortable lower-mid '
                  'register. Warm, grounded and clear, with a clean, lightly bright timbre. Speak casually and directly to '
                  'one curious friend, like a thoughtful contemporary tech podcast host. Use easy connected speech, natural '
                  'contractions, a brisk but unhurried conversational flow, varied sentence lengths in the delivery, and '
                  'brief pauses only where the thought needs them. Let emphasis come from curiosity and meaning, with '
                  'understated wit and small spontaneous changes in pitch. Keep articulation relaxed and natural. Avoid a '
                  'formal documentary or broadcast cadence, grand rounded vowels, theatrical resonance, drawn-out sentence '
                  'endings, sing-song intonation, breathiness or a sales-pitch tone.')
DIRECTION_LIVELY = ('An adult female voice with a native contemporary American English accent and a comfortable lower-mid '
                    'register. Warm, clear and lightly bright. She is genuinely enjoying telling a friend about something '
                    'she just learned: engaged and animated, with a wide but natural pitch range, real emphasis on the '
                    'surprising word in a sentence, a quicker pace through setup and a slower, weighted delivery when a '
                    'point lands. Questions rise naturally; asides drop a little lower and faster, with a hint of a smile. '
                    'Natural contractions and connected speech. Avoid a flat explanatory read, a newsreader or documentary '
                    'cadence, theatrical exaggeration, sing-song intonation, breathiness or a sales-pitch tone.')
LIVELY_REF_TEXT = ("Try this the next time you bake bread. Leave one loaf of dough in the fridge overnight, and bake the "
                   "other one right away. The cold one comes out tangier, with bigger holes and a crust that actually "
                   "crackles. So why would a night in the fridge do all that? Mostly, the yeast slows way down while the "
                   "bacteria keep working. Which, honestly, is a pretty good deal for doing nothing at all.")

PASSAGE = [
    "The process of forcing a single standard began inside an American Standards Association committee in nineteen "
    "fifty-eight. The instigator was not a shipping executive, but a retired engineer from the Aluminum Company of "
    "America named Herbert Hall. Hall knew little about the economics of using containers. What he had was a fixation "
    "on preferred numbers. He wanted a clean arithmetic series of ten, twenty, thirty, and forty feet.",
    "Herbert Hall intervened and pushed through his modular series of ten, twenty, and forty feet. His argument became "
    "the technical heart of the system. A twenty foot box was defined precisely as nineteen feet, ten and a half inches "
    "long. That exact dimension meant two twenty foot boxes could fit perfectly into a single forty foot space on a "
    "truck bed or a rail car.",
    "But the approval was incredibly fragile. Individual companies did not vote in this committee. Industry "
    "organizations voted, and more than a dozen of them were so divided internally that they simply abstained. The "
    "first ballot collapsed. Hall organized a revote on the modular lengths alone and declared victory on the strength "
    "of abstentions. There was no published vote count.",
]

OLD_MASTER = 'loudnorm=I=-16:TP=-1.5:LRA=11'
NEW_MASTER = ('highpass=f=70,equalizer=f=180:t=q:w=1:g=1.5,equalizer=f=3500:t=q:w=1.2:g=2.5,deesser=i=0.3,'
              'acompressor=threshold=-21dB:ratio=2.5:attack=8:release=120:makeup=3,loudnorm=I=-16:TP=-1.5:LRA=9')


def gpu_busy() -> bool:
    out = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'],
                         capture_output=True, text=True).stdout.strip()
    return bool(out)


def master(samples: np.ndarray, chain: str, mp3: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / 'in.wav'
        sf.write(wav, samples, RATE, subtype='PCM_16')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(wav), '-ac', '1',
                        '-af', f'{chain},apad=pad_dur=0.8,aresample={RATE}', '-codec:a', 'libmp3lame', '-b:a', '128k',
                        str(mp3)], check=True)


def seed(value: int) -> None:
    torch.manual_seed(value)
    torch.cuda.manual_seed_all(value)


if gpu_busy():
    raise SystemExit('GPU in use by another process; audition deferred')
receipt = {'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'variants': {}, 'references': {}}

# 1. Design two livelier references, then release the design model.
design = Qwen3TTSModel.from_pretrained(str(DESIGN_PATH), device_map='cuda:0', dtype=torch.bfloat16,
                                       attn_implementation='sdpa', local_files_only=True)
references = {'approved': (APPROVED_REF, APPROVED_TEXT)}
for name, direction in (('same', DIRECTION_SAME), ('lively', DIRECTION_LIVELY)):
    seed(42)
    wavs, rate = design.generate_voice_design(text=LIVELY_REF_TEXT, language='English', instruct=direction,
                                              max_new_tokens=2048)
    path = OUTPUT / f'reference-{name}.wav'
    sf.write(path, np.asarray(wavs[0], dtype=np.float32), rate, subtype='PCM_16')
    references[name] = (path, LIVELY_REF_TEXT)
    receipt['references'][name] = {'file': path.name, 'direction': direction,
                                   'seconds': len(wavs[0]) / rate,
                                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    print('reference', name, flush=True)
del design
torch.cuda.empty_cache()

# 2. Clone the passage under each variant.
base = Qwen3TTSModel.from_pretrained(str(BASE_PATH), device_map='cuda:0', dtype=torch.bfloat16,
                                     attn_implementation='sdpa', local_files_only=True)
variants = [
    ('0-baseline', 'approved', False, 350, OLD_MASTER),
    ('1-seed-mastering', 'approved', True, 550, NEW_MASTER),
    ('2-new-ref-same', 'same', True, 550, NEW_MASTER),
    ('3-new-ref-lively', 'lively', True, 550, NEW_MASTER),
]
prompts = {}
for name, ref, vary_seed, gap_ms, chain in variants:
    if ref not in prompts:
        path, text = references[ref]
        prompts[ref] = base.create_voice_clone_prompt(ref_audio=str(path), ref_text=text, x_vector_only_mode=False)
    parts = []
    for index, paragraph in enumerate(PASSAGE):
        seed(42 + index if vary_seed else 42)
        wavs, rate = base.generate_voice_clone(text=normalize_for_speech(paragraph), language='English',
                                               voice_clone_prompt=prompts[ref], max_new_tokens=2048)
        assert rate == RATE
        if parts:
            parts.append(np.zeros(int(gap_ms / 1000 * RATE), dtype=np.float32))
        parts.append(np.asarray(wavs[0], dtype=np.float32))
    pcm = np.concatenate(parts)
    mp3 = OUTPUT / f'{name}.mp3'
    master(pcm, chain, mp3)
    receipt['variants'][name] = {'reference': ref, 'per_paragraph_seed': vary_seed, 'gap_ms': gap_ms,
                                 'mastering': chain, 'seconds': round(len(pcm) / RATE, 2)}
    print('variant', name, flush=True)

(OUTPUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
