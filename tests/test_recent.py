"""Standalone tests for earworm.recent (cross-episode memory) and the macro-
structure rotation. Run: uv run python tests/test_recent.py
(or: PYTHONPATH=src python3.11 tests/test_recent.py)

No pytest dependency — plain asserts. No LLM and no heavy deps: pure text
extraction + a couple of prompt-wiring invariants.
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm import recent  # noqa: E402
from earworm.pipeline import (  # noqa: E402
    MACRO_STRUCTURES,
    _macro_structure,
    _structure_index,
    RunContext,
)

SAMPLE = """---
title: A Test Episode
date: 2026-06-29
---

This is the opening paragraph. It sets the scene plainly.

So put it together. The middle does some work here. And it keeps going.

---

Which brings us to the cascade. A second body section with its own pivot.

Thanks for listening, and I'll see you next time.
"""


def _write(dir_: Path, name: str, body: str = SAMPLE) -> Path:
    p = dir_ / name
    p.write_text(body)
    return p


def test_extract_signature_pulls_opening_closing_transitions() -> None:
    from earworm.frontmatter import parse

    _, body = parse(SAMPLE)
    sig = recent.extract_signature(body)
    assert sig["opening"].startswith("This is the opening paragraph")
    assert sig["closing"].startswith("Thanks for listening")
    # interior paragraphs' first sentences become transitions; `---` is dropped
    assert "So put it together." in sig["transitions"]
    assert "Which brings us to the cascade." in sig["transitions"]
    assert all(t != "---" for t in sig["transitions"])


def test_build_avoid_section_empty_without_history() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert recent.build_avoid_section(Path(tmp) / "nonexistent") == ""
        empty = Path(tmp) / "scripts"
        empty.mkdir()
        assert recent.build_avoid_section(empty) == ""


def test_build_avoid_section_includes_recurring_phrases() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        _write(d, "2026-06-27-0016-some-topic.md")
        block = recent.build_avoid_section(d)
        assert "AVOID THESE — used in recent episodes:" in block
        assert "So put it together." in block
        assert "Thanks for listening" in block
        assert "Recent openings" in block and "Recent closings" in block


def test_only_generated_scripts_counted_not_ingested() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        # an ingested essay (no 4-digit topic id) must be ignored
        _write(d, "2026-06-14-machines-of-loving-grace.md")
        assert recent.recent_generated_scripts(d) == []
        assert recent.build_avoid_section(d) == ""
        # a generated episode is counted
        _write(d, "2026-06-27-0016-some-topic.md")
        assert len(recent.recent_generated_scripts(d)) == 1


def test_recent_generated_scripts_takes_latest_n_by_mtime() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for i in range(5):
            p = _write(d, f"2026-06-2{i}-000{i}-topic-{i}.md")
            # stagger mtimes so ordering is deterministic, newest = highest i
            t = 1_700_000_000 + i
            import os

            os.utime(p, (t, t))
        latest = recent.recent_generated_scripts(d, n=3)
        names = [p.name for p in latest]
        assert names == [
            "2026-06-24-0004-topic-4.md",
            "2026-06-23-0003-topic-3.md",
            "2026-06-22-0002-topic-2.md",
        ], names


def test_structure_index_rotates_with_topic_id() -> None:
    n = len(MACRO_STRUCTURES)
    # consecutive topic ids land on consecutive structures (rotation)
    base = _structure_index("2026-06-29-0019-foo")
    assert _structure_index("2026-06-29-0020-foo") == (base + 1) % n
    assert _structure_index("2026-06-29-0021-foo") == (base + 2) % n
    # reproducible for the same run_id
    assert _structure_index("2026-06-29-0019-foo") == base


def test_macro_structure_directive_well_formed() -> None:
    ctx = RunContext(
        root=Path("/tmp"),
        prompts=Path("/tmp/prompts"),
        runs=Path("/tmp/runs"),
        inbox_scripts=Path("/tmp/inbox"),
        run_id="2026-06-29-0020-foo",
        topic="foo",
        date="2026-06-29",
        review_enabled=True,
    )
    directive = _macro_structure(ctx)
    assert directive.startswith("STRUCTURE FOR THIS EPISODE — ")
    assert any(name in directive for name, _ in MACRO_STRUCTURES)


def test_script_prompt_lists_every_macro_structure() -> None:
    # the catalog in pipeline.py and the menu in script.md must not drift
    script_md = (Path(__file__).resolve().parent.parent / "prompts" / "script.md").read_text()
    for name, _ in MACRO_STRUCTURES:
        assert name in script_md, f"macro structure {name!r} missing from script.md"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
