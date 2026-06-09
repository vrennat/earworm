"""Pre-fetch the Kokoro model + voices so the first render doesn't block on a
download. Used by `earworm download-models` locally and at Docker build time to bake
a warm cache into the image.

espeak-ng (Kokoro's misaki G2P out-of-vocabulary fallback) is a *system* package, not
something downloadable here — install it with your OS (`apt-get install espeak-ng`,
`brew install espeak-ng`). Kokoro degrades gracefully without it.
"""
from __future__ import annotations

from .kokoro_engine import REPO_ID


def download_models(*, verify: bool = True) -> None:
    """Download the Kokoro weights + voices into the Hugging Face cache.

    When `verify` (default), also load the engine and synthesize a short clip — a
    full-chain smoke test (torch + Kokoro + ffmpeg, plus espeak-ng if installed). At
    Docker build time this makes the build fail loudly if the stack is broken, rather
    than at a user's first render.
    """
    from huggingface_hub import snapshot_download

    print(f"downloading {REPO_ID} (model + voices)...", flush=True)
    path = snapshot_download(REPO_ID)
    print(f"  cached: {path}", flush=True)

    if verify:
        from ..config import voice_config
        from . import get_engine

        print("verifying the engine loads and synthesizes...", flush=True)
        engine = get_engine(voice_config())
        audio = engine.synthesize("Earworm is ready.")
        print(f"  ok: {engine.name} produced {len(audio)} bytes of mp3", flush=True)

    print("models ready.", flush=True)
