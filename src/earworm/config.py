"""Paths and configuration loading.

The project root is the directory containing `pyproject.toml`. All runtime data
(queue db, runs, inbox, done, episodes) lives under the root and is gitignored.
Override the root with the EARWORM_HOME environment variable.
"""
from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Prompts + config templates bundled into the wheel (see pyproject force-include).
# Present in an installed package; absent in a source checkout (which uses its own
# repo-root prompts/ and config/ instead).
_ASSETS = Path(__file__).resolve().parent / "_assets"


def project_root() -> Path:
    env = os.environ.get("EARWORM_HOME")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def db(self) -> Path:
        return self.root / "earworm.db"

    @property
    def prompts(self) -> Path:
        """Local prompts/ if the working dir has them (clone, or after `earworm
        init`), else the prompts bundled in the installed package."""
        local = self.root / "prompts"
        return local if local.exists() else _ASSETS / "prompts"

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def inbox_scripts(self) -> Path:
        return self.root / "inbox" / "scripts"

    @property
    def done_scripts(self) -> Path:
        return self.root / "done" / "scripts"

    @property
    def done_reports(self) -> Path:
        return self.root / "done" / "reports"

    @property
    def episodes(self) -> Path:
        return self.root / "episodes"

    @property
    def interests(self) -> Path:
        return self.root / "interests.md"

    def ensure_dirs(self) -> None:
        for d in (
            self.runs,
            self.inbox_scripts,
            self.done_scripts,
            self.done_reports,
            self.episodes,
        ):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def paths() -> Paths:
    return Paths(root=project_root())


def scaffold_workspace(p: Paths) -> dict:
    """Copy the bundled prompts + config templates into the working dir so they can
    be edited (prompts are the product; tune them). Skips anything that already
    exists. No-op in a source checkout, which has no bundled `_assets`. Returns the
    filenames copied, keyed by kind.
    """
    copied: dict = {"prompts": [], "config": []}
    for kind, dst, pattern in (
        ("prompts", p.root / "prompts", "*.md"),
        ("config", p.config, "*.example.toml"),
    ):
        src = _ASSETS / kind
        if not src.exists():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(src.glob(pattern)):
            target = dst / f.name
            if not target.exists():
                shutil.copy2(f, target)
                copied[kind].append(f.name)
    return copied


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def pipeline_config() -> dict:
    """Per-stage model / retry / toggle settings. Optional — every key defaults."""
    return _load_toml(paths().config / "pipeline.toml")


def voice_config() -> dict:
    return _load_toml(paths().config / "voice.toml")


def show_config() -> dict:
    return _load_toml(paths().config / "show.toml")


def feed_config() -> dict:
    return _load_toml(paths().config / "feed.toml")


def secrets() -> dict:
    """Feed + Cloudflare secrets. Env vars win over config/secrets.toml:
    EARWORM_INGEST_SECRET, EARWORM_FEED_TOKEN, CLOUDFLARE_API_TOKEN.
    """
    data = _load_toml(paths().config / "secrets.toml")
    feed = data.get("feed", {})
    cf = data.get("cloudflare", {})
    return {
        "ingest_secret": os.environ.get("EARWORM_INGEST_SECRET")
        or feed.get("ingest_secret", ""),
        "feed_token": os.environ.get("EARWORM_FEED_TOKEN") or feed.get("feed_token", ""),
        "cf_api_token": os.environ.get("CLOUDFLARE_API_TOKEN") or cf.get("api_token", ""),
    }
