"""Generate a single mp3 auditioning several English Kokoro voices.
Run: .venv/bin/python scripts/voice_sampler.py
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np
from kokoro import KPipeline
from earworm.tts.audio import encode_mp3, silence

SAMPLE_RATE = 24000
# (voice_id, lang_code, spoken label)
VOICES = [
    ("af_heart",   "a", "American female, af heart. The current default."),
    ("af_bella",   "a", "American female, af bella."),
    ("am_michael", "a", "American male, am michael."),
    ("am_fenrir",  "a", "American male, am fenrir."),
    ("bf_emma",    "b", "British female, bf emma."),
    ("bm_george",  "b", "British male, bm george."),
]
LINE = " Local text to speech has quietly gotten very good."

pipes = {}
chunks = []
gap = silence(0.6, SAMPLE_RATE)
for voice, lang, label in VOICES:
    if lang not in pipes:
        pipes[lang] = KPipeline(lang_code=lang)
    text = label + LINE
    for _, _, audio in pipes[lang](text, voice=voice, speed=1.0):
        chunks.append(np.asarray(audio, dtype=np.float32))
    chunks.append(gap)
    print(f"rendered {voice}", flush=True)

full = np.concatenate(chunks)
out = "samples/voice-sampler.mp3"
import os
os.makedirs("samples", exist_ok=True)
open(out, "wb").write(encode_mp3(full, SAMPLE_RATE, "128k"))
print("WROTE", out, f"{len(full)/SAMPLE_RATE:.1f}s")
