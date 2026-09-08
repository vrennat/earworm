"""Disposable Qwen Base process. Verified reference and per-paragraph cache."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gpu_busy() -> bool:
    rows = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"], text=True, timeout=5)
    free = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True, timeout=5)
    return any(row.strip() != str(os.getpid()) for row in rows.splitlines() if row.strip()) or int(free.splitlines()[0]) < 6500


def run(request: dict) -> dict:
    import numpy as np
    import soundfile as sf
    texts = request["texts"]
    if not texts or len(texts) > 150 or any(not isinstance(t, str) or not t.strip() or len(t) > 2000 for t in texts):
        raise ValueError("Invalid or oversized Qwen request")
    model_path = Path(request["model_path"]).resolve()
    config = json.loads((model_path / "config.json").read_text())
    if config["tts_model_type"] != "base" or model_path.name != request["model_revision"]:
        raise ValueError("Qwen model type or revision mismatch")
    reference = Path(request["reference_audio"])
    if digest(reference) != request["reference_sha256"]:
        raise ValueError("Qwen reference hash mismatch")
    identity = {k: request[k] for k in ("model_revision", "reference_sha256", "reference_text", "seed", "worker_sha256")}
    identity["packages"] = {p: importlib.metadata.version(p) for p in ("qwen-tts", "torch", "transformers")}
    cache = Path(request["cache_dir"])
    cache.mkdir(parents=True, exist_ok=True)
    results = []
    for text in texts:
        key = hashlib.sha256(json.dumps({"text": text, **identity}, sort_keys=True).encode()).hexdigest()
        results.append({"path": str(cache / f"{key}.wav"), "metadata": cache / f"{key}.json"})
    deadline = time.monotonic() + float(request.get("gpu_wait_sec", 600))
    with (cache / "render.lock").open("a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Another Earworm renderer is busy")
                time.sleep(2)
        missing = []
        for index, entry in enumerate(results):
            wav, metadata = Path(entry["path"]), entry["metadata"]
            try:
                saved = json.loads(metadata.read_text())
                if saved["sha256"] != digest(wav):
                    missing.append(index)
            except (OSError, ValueError, KeyError):
                missing.append(index)
        if missing:
            while gpu_busy():
                if time.monotonic() >= deadline:
                    raise TimeoutError("Shared GPU remains busy; no other workload was evicted")
                time.sleep(5)
            stop = threading.Event()

            def monitor() -> None:
                while not stop.wait(2):
                    try:
                        if gpu_busy():
                            os._exit(75)
                    except (OSError, subprocess.SubprocessError):
                        os._exit(76)

            threading.Thread(target=monitor, daemon=True).start()
            os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1")
            import torch
            from qwen_tts import Qwen3TTSModel
            model = Qwen3TTSModel.from_pretrained(str(model_path), device_map="cuda:0",
                                                  dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True)
            prompt = model.create_voice_clone_prompt(ref_audio=str(reference), ref_text=request["reference_text"],
                                                       x_vector_only_mode=False)
            for index in missing:
                torch.manual_seed(request["seed"])
                torch.cuda.manual_seed_all(request["seed"])
                wavs, rate = model.generate_voice_clone(text=texts[index], language="English",
                                                        voice_clone_prompt=prompt, max_new_tokens=2048)
                samples = np.asarray(wavs[0], dtype=np.float32)
                if rate != 24000 or samples.ndim != 1 or not samples.size or not np.isfinite(samples).all():
                    raise RuntimeError("Invalid Qwen generated audio")
                if len(samples) / rate > max(30, len(texts[index].split()) + 15):
                    raise RuntimeError("Qwen audio exceeded its paragraph duration bound")
                path = Path(results[index]["path"])
                temporary = path.with_suffix(".tmp.wav")
                sf.write(temporary, samples, rate, subtype="PCM_16")
                temporary.replace(path)
                metadata = results[index]["metadata"]
                temporary_meta = metadata.with_suffix(".tmp")
                temporary_meta.write_text(json.dumps({"sha256": digest(path)}))
                temporary_meta.replace(metadata)
                print(f"Rendered Qwen paragraph {index + 1}/{len(texts)}", file=sys.stderr, flush=True)
            stop.set()
        return {"texts": texts, "chunks": [{"path": e["path"], "sha256": digest(Path(e["path"]))} for e in results],
                "provenance": {**identity, "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base", "reference_audio": str(reference)}}


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    # Dependencies sometimes print startup notices; stdout is exclusively the protocol.
    with contextlib.redirect_stdout(sys.stderr):
        result = run(payload)
    print(json.dumps(result))
