"""Pre-fetch everything the renderer needs so the first render doesn't block on a
download: the Kokoro model + voices, and the spaCy `en_core_web_sm` model that
Kokoro's misaki G2P uses. Used by `earworm download-models` locally and at Docker
build time to bake a warm cache into the image.

espeak-ng (misaki's out-of-vocabulary G2P fallback) is a *system* package, not
something installable here — install it with your OS (`apt-get install espeak-ng`,
`brew install espeak-ng`). Kokoro degrades gracefully without it.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys

from .kokoro_engine import REPO_ID

# spaCy English model for misaki's G2P. It ships only as a GitHub release wheel
# (a direct URL PyPI won't accept in package metadata), so it is not a declared
# dependency — we install the pinned wheel here for a deterministic, offline-capable
# render. misaki would otherwise try to `spacy download` it at first synth, which
# fails in a pip-less (uv-managed) virtualenv.
_SPACY_MODEL = "en_core_web_sm"
_SPACY_WHEEL = (
    "https://github.com/explosion/spacy-models/releases/download/"
    "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
)


def _ensure_spacy_model() -> None:
    if importlib.util.find_spec(_SPACY_MODEL) is not None:
        return
    print(f"installing {_SPACY_MODEL} (Kokoro's misaki G2P needs it)...", flush=True)
    # Prefer uv when present (uv-managed venvs have no pip); fall back to pip, which
    # a `pip install earworm` user will have in their environment.
    uv = shutil.which("uv")
    cmd = (
        [uv, "pip", "install", _SPACY_WHEEL]
        if uv
        else [sys.executable, "-m", "pip", "install", _SPACY_WHEEL]
    )
    subprocess.run(cmd, check=True)


def download_models(*, verify: bool = True) -> None:
    """Download the Kokoro weights + voices and the spaCy G2P model.

    When `verify` (default), also load the engine and synthesize a short clip — a
    full-chain smoke test (torch + Kokoro + spaCy + ffmpeg, plus espeak-ng if
    installed). At Docker build time this makes a broken stack fail the build rather
    than the user's first render.
    """
    from huggingface_hub import snapshot_download

    print(f"downloading {REPO_ID} (model + voices)...", flush=True)
    path = snapshot_download(REPO_ID)
    print(f"  cached: {path}", flush=True)

    _ensure_spacy_model()

    if verify:
        from ..config import voice_config
        from . import get_engine

        print("verifying the engine loads and synthesizes...", flush=True)
        engine = get_engine(voice_config())
        audio = engine.synthesize("Earworm is ready.")
        print(f"  ok: {engine.name} produced {len(audio)} bytes of mp3", flush=True)

    print("models ready.", flush=True)
