"""Standalone checks for recent-episode context and real prompt handoffs.

Run: uv run --locked python tests/test_recent.py
No provider calls, pytest, or audio dependencies are required.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm import recent  # noqa: E402
from earworm.frontmatter import parse  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SAMPLE = """---
title: A Test Episode
date: 2026-06-29
---

This is the opening paragraph. It sets the scene plainly.

The measurements initially agreed. The prior middle explains the failure mechanism.

---

A different comparison exposed the fault. This changes what the first result meant.

The team collected reports from other applications. Those reports located a faulty core.
"""


def _write(directory: Path, name: str, body: str = SAMPLE) -> Path:
    path = directory / name
    path.write_text(body)
    return path


def test_legacy_signature_keeps_opening_closing_transitions() -> None:
    _, body = parse(SAMPLE)
    signature = recent.extract_signature(body)
    assert signature["opening"].startswith("This is the opening paragraph")
    assert signature["closing"].endswith("Those reports located a faulty core.")
    assert signature["transitions"] == [
        "The measurements initially agreed.",
        "A different comparison exposed the fault.",
    ]


def test_context_empty_without_readable_history() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        assert recent.build_recent_context(directory / "missing") == ""
        assert recent.build_recent_context(directory) == ""
        _write(directory, "2026-06-29-0001-empty.md", "---\ntitle: Empty\n---\n")
        (directory / "2026-06-29-0002-binary.md").write_bytes(b"\xff\xfe")
        assert recent.build_recent_context(directory) == ""


def test_only_generated_scripts_count_not_ingested_essays() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _write(directory, "2026-06-14-machines-of-loving-grace.md")
        assert recent.recent_generated_scripts(directory) == []
        assert recent.build_recent_context(directory) == ""
        generated = _write(directory, "2026-06-27-0016-some-topic.md")
        assert recent.recent_generated_scripts(directory) == [generated]


def test_latest_scripts_follow_completion_time_and_respect_zero_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for i in range(5):
            path = _write(directory, f"2026-06-2{i}-000{i}-topic-{i}.md")
            completed = 1_700_000_000 + i
            os.utime(path, (completed, completed))
        assert [p.name for p in recent.recent_generated_scripts(directory)] == [
            "2026-06-24-0004-topic-4.md",
            "2026-06-23-0003-topic-3.md",
            "2026-06-22-0002-topic-2.md",
        ]
        assert recent.recent_generated_scripts(directory, n=0) == []
        assert recent.recent_generated_scripts(directory, n=-1) == []
        assert recent.build_recent_context(directory, n=0) == ""


def test_context_preserves_middle_developments_and_ending_in_order() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _write(directory, "2026-06-29-0001-test.md")
        context = recent.build_recent_context(directory)
        opening = context.index("This is the opening paragraph.")
        middle = context.index("The prior middle explains the failure mechanism.")
        development = context.index("This changes what the first result meant.")
        ending = context.index("Those reports located a faulty core.")
        assert opening < middle < development < ending
        assert "P2/4 | section 1 | 11 words:" in context
        assert "P3/4 | section 2 |" in context
        assert "P4/4 | section 2 |" in context
        assert "not a format assignment" in context
        assert "Shared structure is not automatically a defect" in context


def test_section_break_without_surrounding_blank_lines_is_not_a_paragraph() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _write(
            directory,
            "2026-06-29-0001-test.md",
            "---\ntitle: Breaks\n---\nFirst passage.\n---\nSecond passage.",
        )
        context = recent.build_recent_context(directory)
        assert "2 paragraphs; showing 2" in context
        assert "P1/2 | section 1" in context
        assert "P2/2 | section 2" in context


def test_long_context_is_bounded_and_samples_the_whole_episode() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        paragraphs = [
            f"Opening of passage {i}. " + "Evidence and explanation. " * 35
            + f"The result of passage {i}."
            for i in range(60)
        ]
        body = "---\ntitle: Long episode\n---\n\n" + "\n\n".join(paragraphs)
        for i in range(3):
            _write(directory, f"2026-06-29-000{i}-long.md", body)
        context = recent.build_recent_context(
            directory, max_chars_per_episode=2400, max_paragraphs=12
        )
        assert len(context) <= 3 * 2400 + 800
        assert context.count("60 paragraphs; showing 12") == 3
        assert context.count("P1/60 |") == 3
        assert context.count("P60/60 |") == 3
        assert "The result of passage 59." in context
        assert "P28/60 |" in context
        assert "[…]" in context


def test_budget_validation_is_explicit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for kwargs in ({"max_chars_per_episode": 999}, {"max_paragraphs": 1}):
            try:
                recent.build_recent_context(Path(tmp), **kwargs)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Accepted unusable excerpt budget: {kwargs}")


def test_compatibility_entry_point_provides_context_without_a_ban_list() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _write(directory, "2026-06-29-0001-test.md")
        context = recent.build_avoid_section(directory)
        assert "The prior middle explains the failure mechanism." in context
        assert "AVOID THESE" not in context


def _rendered_stage_prompts(tmp: str, review_enabled: bool = True) -> dict[str, str]:
    from earworm import llm
    from earworm.pipeline import STAGES, RunContext

    root = Path(tmp)
    context = RunContext(
        root=root,
        prompts=REPO / "prompts",
        runs=root / "runs",
        inbox_scripts=root / "inbox",
        run_id="2026-06-29-0020-foo",
        topic="A specific topic",
        date="2026-06-29",
        review_enabled=review_enabled,
    )
    context.run_dir.mkdir(parents=True, exist_ok=True)
    context.report_path.write_text("Report evidence marker.")
    context.review_path.write_text("Corrected evidence marker.")
    context.script_review_path.write_text('"Draft body marker." Cut the duplicate.')
    context.staged_script.write_text("---\ntitle: T\n---\n\nDraft body marker.\n")
    context.done_scripts.mkdir(parents=True, exist_ok=True)
    _write(context.done_scripts, "2026-06-27-0016-prior.md")
    return {
        stage.name: llm.render_prompt(
            context.prompts / stage.prompt_file, **stage.build_vars(context)
        )
        for stage in STAGES
    }


def test_every_stage_renders_without_unresolved_prompt_variables() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in _rendered_stage_prompts(tmp).items():
            assert "{{" not in text, f"Unrendered placeholder in {name} prompt"


def test_evidence_and_recent_middle_reach_each_editorial_handoff() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rendered = _rendered_stage_prompts(tmp)
    for name in ("review", "script", "script_review", "revise"):
        assert "Report evidence marker." in rendered[name], name
        assert "The prior middle explains the failure mechanism." in rendered[name], name
    for name in ("script", "script_review", "revise"):
        assert "Corrected evidence marker." in rendered[name], name
        assert "Hint placement is load-bearing" in rendered[name], name
    assert "Draft body marker." in rendered["script_review"]
    assert "Draft body marker." in rendered["revise"]
    assert "Cut the duplicate." in rendered["revise"]


def test_disabled_review_does_not_leak_a_stale_review_into_writing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rendered = _rendered_stage_prompts(tmp, review_enabled=False)
    for name in ("script", "script_review", "revise"):
        assert "Report evidence marker." in rendered[name], name
        assert "Corrected evidence marker." not in rendered[name], name


def test_research_report_envelope_remains_readable_as_show_notes() -> None:
    from earworm import shownotes

    prompt = (REPO / "prompts" / "research.md").read_text()
    # Use the actual prompt's envelope examples so loosening its output contract
    # cannot silently remove the summary or source links from rendered episodes.
    examples = (
        "# Report title",
        "> Summary text",
        "## Sources",
        "- [Descriptive source title](https://source-url)",
    )
    for example in examples:
        assert f"`{example}`" in prompt
    assert "not a required episode outline" in prompt
    report = "\n\n".join(examples)
    with tempfile.TemporaryDirectory() as tmp:
        path = _write(Path(tmp), "report.md", report)
        summary, sources = shownotes.extract(path)
    assert summary == "Summary text"
    assert sources == ["Descriptive source title — https://source-url"]


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
