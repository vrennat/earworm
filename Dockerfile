# Earworm renderer image.
#
# Owns the painful native stack — CPU PyTorch + Kokoro + espeak-ng + ffmpeg — and
# ships a pre-warmed model, so `earworm watch` / `earworm render` work out of the box
# with no first-run download. Generation (`earworm run`) needs the authenticated
# `claude` CLI and normally runs on the host; Earworm's two halves share only a folder,
# mounted here at /data. (You CAN generate in-container too: install the claude CLI and
# pass ANTHROPIC_API_KEY — see README "Docker".)
#
# NOTE: built and shipped CPU-only on purpose. The default Linux torch wheel bundles
# CUDA (~2GB); UV_TORCH_BACKEND=cpu selects the CPU PyTorch index instead.

FROM python:3.11-slim

# Native deps: ffmpeg (loudness mastering + mp3 encode), espeak-ng (Kokoro's misaki
# G2P out-of-vocabulary fallback — improves proper-noun pronunciation).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv (pinned) — copy the static binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

ENV UV_TORCH_BACKEND=cpu \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install deps in a cached layer. The project installs too (it provides the `earworm`
# console script), so src/ must be present for the build backend. prompts/ + config/
# must also be present BEFORE sync: the wheel build force-includes them as package
# data (see pyproject), and --no-editable forces a built install so that bundling
# actually runs. .dockerignore keeps real configs out of the build context.
COPY pyproject.toml uv.lock .python-version ./
COPY src ./src
COPY prompts ./prompts
COPY config ./config
RUN uv sync --no-dev --no-editable

# Bake a warm Kokoro cache (model + voices) into the image and smoke-test the full
# render chain at BUILD time. A broken stack fails the build, not the user's first run.
RUN uv run earworm download-models

# User data — config/*.toml, inbox/scripts/, episodes/, earworm.db — lives on a mounted
# volume. Mount your working directory:  docker run -v "$PWD":/data earworm watch
ENV EARWORM_HOME=/data
VOLUME /data

ENTRYPOINT ["uv", "run", "earworm"]
CMD ["watch"]
