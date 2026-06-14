"""earworm — research-to-podcast pipeline CLI.

Commands:
  earworm init                 create data dirs + db
  earworm add "<topic>"        queue a topic (--source manual|auto)
  earworm ingest <src>         stage a pre-written script (file|URL|-) for rendering
  earworm list                 show the queue
  earworm run [--id N]         drain one pending topic (research -> script)
  earworm reset-stale          requeue topics stuck 'running' after a crash
  earworm watch                watch inbox/scripts and render new scripts to mp3
  earworm render <file.md>     render a single script file (one-shot, for testing)
  earworm download-models      pre-fetch the Kokoro model + voices (warm the cache)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import db
from .config import paths, scaffold_workspace


def _cmd_init(args: argparse.Namespace) -> int:
    p = paths()
    # When installed from PyPI the working dir has no prompts/config; lay down
    # editable copies from the bundled templates. No-op in a source checkout.
    copied = scaffold_workspace(p)
    db.init()
    print(f"initialized earworm at {p.root}")
    if copied["prompts"]:
        print(f"  prompts: {len(copied['prompts'])} file(s) -> {p.root / 'prompts'}")
    if copied["config"]:
        print(
            f"  config:  {len(copied['config'])} template(s) -> {p.config} "
            "(copy <name>.example.toml -> <name>.toml and edit)"
        )
    print(f"  db:     {p.db}")
    print(f"  inbox:  {p.inbox_scripts}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    db.init()
    topic = args.topic.strip()
    if not topic:
        print("error: empty topic", file=sys.stderr)
        return 2
    tid = db.add_topic(topic, source=args.source)
    print(f"queued #{tid} [{args.source}]: {topic}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from . import ingest

    try:
        res = ingest.ingest_source(
            args.source,
            title=args.title,
            date=args.date,
            raw=args.raw,
            model=args.model,
            source_url=args.source_url,
        )
    except Exception as exc:  # noqa: BLE001 - report + non-zero exit
        print(f"ingest failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    mode = "raw" if not res["adapted"] else "adapted"
    print(f"ingested [{mode}]: {res['title']}")
    print(f"  source: {res['source']}")
    print(f"  script: {res['script_path']}  ({res['body_words']} words)")
    if res["warning"]:
        print(f"  warning: {res['warning']}", file=sys.stderr)
    print("  -> run `earworm watch` (or wait for the watch agent) to render it")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    db.init()
    rows = db.list_topics(limit=args.limit)
    if not rows:
        print("(queue empty)")
        return 0
    for r in rows:
        line = f"#{r['id']:>4} {r['status']:<8} [{r['source']:<6}] {r['topic']}"
        if r["status"] == "failed" and r["notes"]:
            line += f"  -- {r['notes'][:120]}"
        print(line)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from . import db, runner

    if args.all:
        db.init()
        drained = failed = 0
        while (row := db.next_pending()) is not None:
            try:
                runner.run_one(model=args.model)
                drained += 1
                print(f"done #{row['id']}: {row['topic']}")
            except Exception as exc:  # noqa: BLE001 - record + continue draining
                failed += 1
                print(f"failed #{row['id']}: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"drained {drained}, failed {failed}")
        return 1 if failed else 0

    try:
        result = runner.run_one(topic_id=args.id, model=args.model)
    except Exception as exc:  # noqa: BLE001
        print(f"run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"done #{result['topic_id']}: {result['topic']}")
    print(f"  report: {result['report_path']}")
    print(f"  script: {result['script_path']}")
    return 0


def _cmd_autogen(args: argparse.Namespace) -> int:
    from . import autogen

    try:
        added = autogen.generate(count=args.count, model=args.model)
    except Exception as exc:  # noqa: BLE001
        print(f"autogen failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if not added:
        print("no new topics proposed (all overlapped recent)")
        return 0
    print(f"queued {len(added)} auto topic(s):")
    for t in added:
        print(f"  - {t}")
    return 0


def _cmd_watch(args: argparse.Namespace) -> int:
    from . import render

    try:
        render.watch(poll_seconds=args.poll)
    except KeyboardInterrupt:
        print("\n[watch] stopped")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    from . import render

    script = Path(args.file).expanduser().resolve()
    if not script.exists():
        print(f"error: no such file: {script}", file=sys.stderr)
        return 2
    result = render.render_script_file(script, publish=not args.no_publish)
    print(f"{result['status']}: {result.get('title')}")
    if result.get("audio_path"):
        print(f"  audio: {result['audio_path']} ({result['duration_sec']}s, {result['engine']})")
    if result.get("audio_url"):
        print(f"  url:   {result['audio_url']}")
    return 0


def _cmd_reset_stale(args: argparse.Namespace) -> int:
    db.init()
    n = db.reset_stale_running()
    print(f"reset {n} stale running topic(s) to pending")
    return 0


def _cmd_download_models(args: argparse.Namespace) -> int:
    from .tts.download import download_models

    try:
        download_models(verify=not args.no_verify)
    except Exception as exc:  # noqa: BLE001
        print(f"download failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    from . import render

    try:
        n = render.publish_unpublished()
    except Exception as exc:  # noqa: BLE001
        print(f"publish failed: {exc}", file=sys.stderr)
        return 1
    print(f"published {n} episode(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="earworm", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create data dirs + db").set_defaults(func=_cmd_init)

    p_add = sub.add_parser("add", help="queue a topic")
    p_add.add_argument("topic", help="topic or pointed question")
    p_add.add_argument("--source", choices=["manual", "auto"], default="manual")
    p_add.set_defaults(func=_cmd_add)

    p_ingest = sub.add_parser(
        "ingest", help="stage a pre-written script (file, URL, or stdin) for rendering"
    )
    p_ingest.add_argument(
        "source",
        nargs="?",
        default="-",
        help="path to a .md/.txt file, an http(s) URL, or - for stdin (default)",
    )
    p_ingest.add_argument("--title", default=None, help="override the episode title")
    p_ingest.add_argument(
        "--date", default=None, help="episode date YYYY-MM-DD (default: today)"
    )
    p_ingest.add_argument(
        "--raw",
        action="store_true",
        help="skip the Claude audio-adaptation pass; use the text as-is",
    )
    p_ingest.add_argument(
        "--model", default=None, help="override Claude model for the adapt/fetch passes"
    )
    p_ingest.add_argument(
        "--source-url",
        default=None,
        help="cite this URL in the show notes (when reading text from a file/stdin)",
    )
    p_ingest.set_defaults(func=_cmd_ingest)

    p_list = sub.add_parser("list", help="show the queue")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=_cmd_list)

    p_run = sub.add_parser("run", help="drain pending topic(s)")
    p_run.add_argument("--id", type=int, default=None, help="run a specific topic id")
    p_run.add_argument("--all", action="store_true", help="drain every pending topic")
    p_run.add_argument("--model", default=None, help="override Claude model (e.g. sonnet)")
    p_run.set_defaults(func=_cmd_run)

    sub.add_parser(
        "reset-stale", help="requeue topics stuck 'running' after a crash"
    ).set_defaults(func=_cmd_reset_stale)

    p_autogen = sub.add_parser("autogen", help="propose + queue fresh topics from interests.md")
    p_autogen.add_argument("--count", type=int, default=3, help="how many topics to propose")
    p_autogen.add_argument("--model", default=None, help="override Claude model")
    p_autogen.set_defaults(func=_cmd_autogen)

    p_watch = sub.add_parser("watch", help="watch inbox and render scripts")
    p_watch.add_argument("--poll", type=float, default=2.0, help="poll interval seconds")
    p_watch.set_defaults(func=_cmd_watch)

    p_render = sub.add_parser("render", help="render a single script file")
    p_render.add_argument("file", help="path to a script .md")
    p_render.add_argument("--no-publish", action="store_true", help="render only, don't upload/register")
    p_render.set_defaults(func=_cmd_render)

    p_dl = sub.add_parser("download-models", help="pre-fetch the Kokoro model + voices")
    p_dl.add_argument(
        "--no-verify", action="store_true", help="download only; skip the synth smoke check"
    )
    p_dl.set_defaults(func=_cmd_download_models)

    sub.add_parser("publish", help="upload + register any unpublished episodes").set_defaults(
        func=_cmd_publish
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
