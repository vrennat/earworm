"""Final-script coverage, report sources, and renderer metadata contracts.

Run: python tests/test_shownotes.py. Audio synthesis and publication are faked;
the normal render path writes to a real temporary episode ledger.
"""
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm import db, render, shownotes  # noqa: E402
from earworm.config import Paths  # noqa: E402
from earworm.frontmatter import parse  # noqa: E402
from earworm.ingest import build_report, build_script  # noqa: E402


REPORT_SUMMARY = "The research covers sorting, storage, and indexing."
FINAL_SUMMARY = "Locale-specific comparisons change how an index orders names."
SOURCES = ["Comparison specification — https://example.com/comparison"]
BODY = "Two names can compare differently when the chosen locale changes."


def report_file(root: Path) -> Path:
    path = root / "report.md"
    path.write_text(
        f"# Research\n\n> {REPORT_SUMMARY}\n\n## Sources\n"
        "- [Comparison specification](https://example.com/comparison)\n"
    )
    return path


def test_final_coverage_replaces_report_thesis_and_preserves_sources() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        summary, sources = shownotes.extract(report_file(Path(tmp)), description=FINAL_SUMMARY)
        assert summary == FINAL_SUMMARY
        assert sources == SOURCES
        notes = shownotes.format_notes(summary, sources)
        assert notes.startswith(FINAL_SUMMARY + "\nSources:\n")
        assert REPORT_SUMMARY not in notes


def test_missing_or_unusable_description_keeps_legacy_report_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = report_file(Path(tmp))
        for description in (None, "", "  ", "|", "|-", ">", ">+", "null", "~"):
            assert shownotes.extract(report, description=description) == (REPORT_SUMMARY, SOURCES)
        assert shownotes.extract(report) == (REPORT_SUMMARY, SOURCES)


def test_description_works_without_a_report() -> None:
    assert shownotes.extract(None, description=FINAL_SUMMARY) == (FINAL_SUMMARY, [])
    with tempfile.TemporaryDirectory() as tmp:
        assert shownotes.extract(Path(tmp) / "missing.md", description=FINAL_SUMMARY) == (FINAL_SUMMARY, [])
    assert shownotes.extract(None) == ("", [])


def test_imported_script_and_report_keep_existing_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "imported.report.md"
        report.write_text(build_report(
            title="A reading", source_ref="https://example.com/essay", summary="An author's essay.",
        ))
        meta, body = parse(build_script(
            title="A reading", date="2026-10-02", report_path=str(report), body=BODY,
            author="An author", feed="readings",
        ))
        assert "description" not in meta
        assert body == BODY
        assert shownotes.extract(report, description=meta.get("description")) == (
            "An author's essay.", ["A reading — https://example.com/essay"],
        )


def test_renderer_publishes_and_archives_final_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Paths(root=Path(tmp))
        p.ensure_dirs()
        report = report_file(p.root)
        script = p.inbox_scripts / "revised-episode.md"
        script.write_text(
            f'---\ntitle: "How names compare"\ndescription: "{FINAL_SUMMARY}"\n'
            f"date: 2026-10-02\nreport_path: {report}\n---\n\n{BODY}"
        )
        fake_mp3 = ModuleType("mutagen.mp3")
        fake_mp3.MP3 = lambda path: SimpleNamespace(info=SimpleNamespace(length=12.5))
        engine = SimpleNamespace(name="fake")
        expected_notes = shownotes.format_notes(FINAL_SUMMARY, SOURCES)
        with (
            patch.dict(sys.modules, {"mutagen.mp3": fake_mp3}),
            patch.object(render, "paths", return_value=p),
            patch.object(db, "paths", return_value=p),
            patch.object(render, "voice_config", return_value={}),
            patch.object(render, "_synthesize", return_value=(b"fake audio", [], {})) as synthesize,
            patch.object(render, "_tag") as tag,
            patch.object(render.feed, "is_configured", return_value=(True, "")),
            patch.object(render.feed, "publish", return_value=("https://example.com/audio.mp3", None)) as publish,
        ):
            result = render.render_script_file(script, engine=engine, log=lambda message: None)
            assert result["status"] == "rendered"
            synthesize.assert_called_once_with(BODY, engine, {}, "How names compare")
            assert tag.call_args.kwargs["notes"] == expected_notes
            assert tag.call_args.kwargs["title"] == "How names compare"
            assert publish.call_args.kwargs["description"] == expected_notes
            episode = db.get_episode_by_slug("revised-episode")
            assert episode["description"] == expected_notes
            assert any(FINAL_SUMMARY in entry for entry in db.recent_coverage())
            assert not any(REPORT_SUMMARY in entry for entry in db.recent_coverage())
        assert (p.done_scripts / script.name).exists()
        assert (p.done_reports / "revised-episode.report.md").read_text() == report.read_text()


def test_preview_uses_same_final_coverage_without_narrating_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report = report_file(root)
        script = root / "script.md"
        script.write_text(
            f'---\ntitle: "How names compare"\ndescription: "{FINAL_SUMMARY}"\n'
            f"date: 2026-10-02\nreport_path: {report}\n---\n\n{BODY}"
        )
        fake_mp3 = ModuleType("mutagen.mp3")
        fake_mp3.MP3 = lambda path: SimpleNamespace(info=SimpleNamespace(length=12.5))
        engine = SimpleNamespace(name="fake")
        with (
            patch.dict(sys.modules, {"mutagen.mp3": fake_mp3}),
            patch.object(render, "voice_config", return_value={}),
            patch.object(render, "_synthesize", return_value=(b"fake audio", [], {})) as synthesize,
            patch.object(render, "_tag") as tag,
        ):
            result = render.render_preview(script, root / "preview", engine=engine)
            assert result["status"] == "preview" and result["published"] is False
            synthesize.assert_called_once_with(BODY, engine, {}, "How names compare")
            assert tag.call_args.kwargs["notes"] == shownotes.format_notes(FINAL_SUMMARY, SOURCES)
        assert script.exists()


def main() -> int:
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"all {len(tests)} show notes tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
