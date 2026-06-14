"""`earworm ingest` — feed a pre-written script straight to the renderer.

The research pipeline (db topics -> `earworm run` -> script) is one way to land a
script in `inbox/scripts/`. Ingest is a second intake path: take a ready essay from
a file, a URL, or stdin, lightly adapt it for the ear, and stage it for the watcher.
Both paths meet at `earworm watch`. Ingest never touches the topics queue — it is for
text that is already written, not researched.

Two operations need Claude Code (earworm is coupled to it by design — see
pipeline.py): fetching + extracting an article from a URL, and the audio-adaptation
pass that cleans reading-only artifacts ("see the figure below", footnote markers,
markdown) into speakable prose. Local files/stdin in --raw mode use neither: a
deterministic markdown->prose strip handles them with no LLM.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date as date_cls
from pathlib import Path
from typing import Callable, Optional

from . import claude, pipeline
from .config import Paths, paths, pipeline_config
from .feed import DEFAULT_FEED
from .frontmatter import parse
from .runner import slugify

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_HR = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_FOOTNOTE_DEF = re.compile(r"^\s*\[\^[^\]]+\]:")


# --- pure helpers ----------------------------------------------------------

def is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def _wc(text: str) -> int:
    return len(text.split())


def _truncate_title(s: str, maxlen: int = 90) -> str:
    if len(s) <= maxlen:
        return s
    cut = s[:maxlen]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > maxlen // 2 else cut).rstrip()


def derive_title(text: str, *, fallback: str, meta: Optional[dict] = None) -> str:
    """A display title for the episode: front-matter `title` wins, then the first
    markdown heading, then the first non-empty line, then the caller's fallback."""
    if meta and meta.get("title"):
        return meta["title"].strip()
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = _HEADING.match(s)
        return m.group(1).strip() if m else _truncate_title(s)
    return fallback


def markdown_to_prose(text: str) -> str:
    """Deterministic markdown -> speakable prose for --raw ingestion. Strips
    headings, list/quote markers, links (keeping their text), images, and footnotes;
    keeps paragraph breaks; maps horizontal rules to the renderer's `---` audio beat.
    Not a rewrite — just removes syntax the TTS voice would mispronounce."""
    kept: list[str] = []
    for line in text.splitlines():
        if _FOOTNOTE_DEF.match(line):
            continue  # drop footnote definitions entirely
        l = re.sub(r"^#{1,6}\s*", "", line)          # heading markers
        l = re.sub(r"^\s*>\s?", "", l)               # blockquote markers
        l = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", l)  # list markers
        if _HR.match(l):
            l = "---"                                  # horizontal rule -> audio beat
        kept.append(l)
    out = "\n".join(kept)
    out = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", out)    # images
    out = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", out)  # links -> link text
    out = re.sub(r"\[\^[^\]]+\]", "", out)            # footnote references
    out = re.sub(r"[*_`]", "", out)                   # emphasis / inline code marks
    out = re.sub(r"\n{3,}", "\n\n", out)              # collapse blank-line runs
    return out.strip()


def summary_line(body: str, maxlen: int = 240) -> str:
    """First sentence of the body, for the show-note thesis line."""
    text = re.sub(r"\s+", " ", body.strip())
    m = re.match(r"^(.+?[.!?])(?:\s|$)", text)
    s = m.group(1) if m else text
    return (s[:maxlen].rstrip() + " …") if len(s) > maxlen else s.strip()


def build_report(title: str, source_ref: Optional[str], summary: str) -> str:
    """A minimal report so the renderer's show-note extractor (shownotes.extract)
    yields a thesis line plus a link back to the original essay."""
    lines = [f"# {title}", "", f"> {summary}", ""]
    if source_ref:
        src = f"[{title}]({source_ref})" if is_url(source_ref) else source_ref
        lines += ["## Sources", "", f"- {src}", ""]
    return "\n".join(lines)


def build_script(
    title: str,
    date: str,
    report_path: str,
    body: str,
    author: Optional[str] = None,
    feed: Optional[str] = None,
) -> str:
    """The inbox script: front-matter the renderer reads (title/date/report_path)
    followed by the spoken body. An optional `author` is recorded in front-matter.
    A named `feed` routes the episode to a separate RSS feed; the default feed is
    left implicit (no `feed:` line) so ordinary scripts stay unchanged."""
    fm = [f"title: {title}", f"date: {date}", f"report_path: {report_path}"]
    if feed and feed != DEFAULT_FEED:
        fm.append(f"feed: {feed}")
    if author:
        fm.append(f"author: {author}")
    return "---\n" + "\n".join(fm) + "\n---\n\n" + body.strip() + "\n"


def prepend_byline(body: str, title: str, author: str) -> str:
    """Open the spoken body with an attribution sentence. A leading line that is
    just the title is dropped first, so the title isn't read twice."""
    lines = body.lstrip().split("\n")
    if lines and lines[0].strip() == title.strip():
        body = "\n".join(lines[1:]).lstrip()
    return f"This is {title}, an essay by {author}.\n\n{body}"


def adapted_too_short(src_words: int, out_words: int, threshold: float = 0.6) -> bool:
    """True when the adapt pass shrank the text enough to suspect it summarized
    rather than cleaned. Guards against the LLM condensing a full essay."""
    if src_words == 0:
        return False
    return out_words < threshold * src_words


# --- Claude passes (injected in tests) -------------------------------------

def _run_with_retry(
    stage_name: str,
    prompt: str,
    expect: Path,
    model: Optional[str],
    *,
    allowed: tuple[str, ...],
    timeout: int,
) -> None:
    """Drive claude.run with the same model/retry/fallback treatment the pipeline
    stages get, keyed `[pipeline.<stage_name>]` in pipeline.toml."""
    cfg = pipeline.PipelineConfig.from_toml(pipeline_config())
    sc = cfg.for_stage(stage_name)
    chosen = pipeline.resolve_model(model, sc.model, cfg.default_model)
    retries = cfg.default_retries if sc.retries is None else sc.retries
    t = timeout if sc.timeout is None else sc.timeout
    pipeline.with_retry(
        lambda m: claude.run(
            prompt,
            cwd=paths().root,
            allowed_tools=allowed,
            expect_file=expect,
            timeout=t,
            model=m,
        ),
        model=chosen,
        retries=retries,
        fallback_model=sc.fallback_model,
    )


def _claude_fetch(url: str, out_path: Path, model: Optional[str]) -> str:
    """Fetch + extract an article's text from a URL, verbatim, into out_path."""
    prompt = claude.render_prompt(
        paths().prompts / "ingest_fetch.md", url=url, out_path=str(out_path)
    )
    _run_with_retry(
        "ingest_fetch", prompt, out_path, model,
        allowed=("WebFetch", "WebSearch", "Read", "Write", "Edit"), timeout=600,
    )
    return out_path.read_text()


def _claude_adapt(
    source_path: Path, out_path: Path, model: Optional[str], author: Optional[str] = None
) -> str:
    """Rewrite the source text for the ear (light cleanup, full content) into out_path."""
    author_note = (
        f"The author is {author}. Credit them by name in that opening sentence." if author else ""
    )
    prompt = claude.render_prompt(
        paths().prompts / "ingest.md",
        source_path=str(source_path),
        out_path=str(out_path),
        author_note=author_note,
    )
    _run_with_retry(
        "ingest", prompt, out_path, model,
        allowed=("Read", "Write", "Edit"), timeout=1800,
    )
    return out_path.read_text()


# --- orchestration ---------------------------------------------------------

def ingest_source(
    source: str,
    *,
    title: Optional[str] = None,
    date: Optional[str] = None,
    raw: bool = False,
    model: Optional[str] = None,
    source_url: Optional[str] = None,
    author: Optional[str] = None,
    feed: Optional[str] = None,
    p: Optional[Paths] = None,
    _fetch: Optional[Callable[..., str]] = None,
    _adapt: Optional[Callable[..., str]] = None,
    _stdin: Optional[Callable[[], str]] = None,
) -> dict:
    """Stage one pre-written script for the renderer.

    `source` is a file path, an http(s) URL, or "-" for stdin. With `raw`, the text
    is used as-is (markdown stripped to prose); otherwise it goes through the Claude
    audio-adaptation pass. URLs are always fetched + extracted by Claude. `source_url`
    overrides the show-note source link — use it to read text from a file/stdin while
    citing the original web URL. `author`, when given, is recorded in front-matter and
    opens the episode with a spoken attribution. `feed`, when given, routes the episode
    to a separate named RSS feed (normalized to a URL-safe slug). Returns a result dict
    (run_id, paths, the resolved feed, and a `warning` if the adapt pass looks like it
    condensed the essay).
    """
    p = p or paths()
    p.ensure_dirs()
    feed_slug = slugify(feed) if feed and feed.strip() else DEFAULT_FEED
    fetch = _fetch or _claude_fetch
    adapt = _adapt or _claude_adapt
    read_stdin = _stdin or (lambda: sys.stdin.read())

    source_ref: Optional[str] = None
    title_seed = "untitled-essay"

    if source == "-":
        text = read_stdin()
    elif is_url(source):
        source_ref = source
        tmp = Path(tempfile.mkstemp(dir=p.runs, suffix=".md")[1])
        try:
            text = fetch(source, tmp, model)
        finally:
            tmp.unlink(missing_ok=True)
        title_seed = source.rstrip("/").rsplit("/", 1)[-1] or title_seed
    else:
        src_path = Path(source).expanduser()
        if not src_path.exists():
            raise FileNotFoundError(f"no such file: {src_path}")
        text = src_path.read_text()
        source_ref = str(src_path)
        title_seed = src_path.stem

    if not text.strip():
        raise ValueError("ingest source is empty")

    if source_url:  # explicit citation overrides the derived file/stdin/url ref
        source_ref = source_url

    meta, body_src = parse(text)
    resolved_title = title or derive_title(body_src, fallback=title_seed, meta=meta)
    run_date = date or meta.get("date") or date_cls.today().isoformat()
    run_id = f"{run_date}-{slugify(resolved_title)}"
    run_dir = p.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    source_path = run_dir / "source.md"
    source_path.write_text(body_src)

    if raw:
        body = markdown_to_prose(body_src)
        adapted = False
    else:
        body = adapt(source_path, run_dir / "script.body.txt", model, author)
        adapted = True

    # Raw text gets no spoken intro; add an attribution opener when an author is
    # named. The adapt pass writes its own credited opener (via author_note).
    if author and raw:
        body = prepend_byline(body, resolved_title, author)

    src_words, body_words = _wc(body_src), _wc(body)
    warning = ""
    if adapted and adapted_too_short(src_words, body_words):
        warning = (
            f"adapted body is {body_words} words vs {src_words} in the source "
            f"({body_words / src_words:.0%}). The adapt pass may have summarized it. "
            "Re-run with --raw to read the essay verbatim."
        )

    report_path = run_dir / "report.md"
    report_path.write_text(build_report(resolved_title, source_ref, summary_line(body)))

    # Generate in the run dir, then atomically rename into inbox so `earworm watch`
    # never sees a half-written file (same pattern as runner.run_one).
    staged = run_dir / "script.md"
    staged.write_text(
        build_script(resolved_title, run_date, str(report_path), body, author, feed_slug)
    )
    dest = p.inbox_scripts / f"{run_id}.md"
    os.replace(staged, dest)

    return {
        "run_id": run_id,
        "slug": run_id,
        "title": resolved_title,
        "feed": feed_slug,
        "script_path": str(dest),
        "report_path": str(report_path),
        "source": source_ref or "stdin",
        "adapted": adapted,
        "source_words": src_words,
        "body_words": body_words,
        "warning": warning,
    }
