"""Standalone tests for earworm.ingest. Run: uv run python tests/test_ingest.py
(or: PYTHONPATH=src python3.11 tests/test_ingest.py)

No pytest dependency — plain asserts. The real `claude` CLI is never invoked: the
fetch (URL) and adapt (audio cleanup) passes are dependency-injected fakes, exactly
like test_pipeline.py fakes claude.run. Everything else is pure logic + local FS.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm import shownotes  # noqa: E402
from earworm.config import Paths  # noqa: E402
from earworm.frontmatter import parse  # noqa: E402
from earworm.ingest import (  # noqa: E402
    adapted_too_short,
    build_report,
    build_script,
    derive_title,
    ingest_source,
    is_url,
    markdown_to_prose,
    summary_line,
)


# --- pure helpers ----------------------------------------------------------

def test_is_url() -> None:
    assert is_url("https://darioamodei.com/essay")
    assert is_url("http://example.com")
    assert not is_url("/Users/me/essay.md")
    assert not is_url("essay.md")
    assert not is_url("-")


def test_derive_title_prefers_frontmatter() -> None:
    text = "---\ntitle: Machines of Loving Grace\n---\nBody here."
    meta, body = parse(text)
    assert derive_title(body, fallback="x", meta=meta) == "Machines of Loving Grace"


def test_derive_title_from_first_heading() -> None:
    text = "# The Urgency of Interpretability\n\nFirst paragraph."
    assert derive_title(text, fallback="x") == "The Urgency of Interpretability"


def test_derive_title_from_first_line_when_no_heading() -> None:
    text = "On DeepSeek and Export Controls\n\nLong essay body that goes on."
    assert derive_title(text, fallback="x") == "On DeepSeek and Export Controls"


def test_derive_title_falls_back() -> None:
    assert derive_title("   \n\n", fallback="essay-2026") == "essay-2026"


def test_markdown_to_prose_strips_reading_artifacts() -> None:
    md = (
        "# Heading\n\n"
        "See [the chart](https://x.com/chart) for details.[^1]\n\n"
        "- first point\n"
        "- second point\n\n"
        "[^1]: a footnote\n"
    )
    out = markdown_to_prose(md)
    assert "#" not in out
    assert "https://" not in out
    assert "[^1]" not in out
    assert "a footnote" not in out  # footnote definition line dropped
    assert "the chart" in out  # link text kept
    assert "first point" in out and "second point" in out
    assert "- first" not in out  # bullet markers stripped


def test_markdown_to_prose_preserves_paragraphs() -> None:
    md = "Para one.\n\nPara two.\n\n\n\nPara three."
    out = markdown_to_prose(md)
    assert out.count("\n\n") == 2, "paragraph breaks preserved, runs collapsed"


def test_summary_line_takes_first_sentence() -> None:
    body = "This is the hook. Then a second sentence. And a third."
    assert summary_line(body) == "This is the hook."


def test_build_script_has_frontmatter_and_body() -> None:
    s = build_script(
        title="Test Title",
        date="2026-06-14",
        report_path="/abs/runs/x/report.md",
        body="The spoken body.\n\nSecond paragraph.",
    )
    meta, body = parse(s)
    assert meta["title"] == "Test Title"
    assert meta["date"] == "2026-06-14"
    assert meta["report_path"] == "/abs/runs/x/report.md"
    assert body.startswith("The spoken body.")


def test_build_script_includes_author() -> None:
    s = build_script(
        title="T", date="2026-06-14", report_path="/x/report.md", body="Body.", author="Dario Amodei"
    )
    meta, _ = parse(s)
    assert meta["author"] == "Dario Amodei"


def test_build_script_omits_author_when_absent() -> None:
    s = build_script(title="T", date="2026-06-14", report_path="/x/report.md", body="Body.")
    meta, _ = parse(s)
    assert "author" not in meta


def test_raw_author_prepends_byline_and_drops_dup_title() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        res = ingest_source(
            "-",
            raw=True,
            title="The Urgency of Interpretability",
            author="Dario Amodei",
            date="2026-06-14",
            p=p,
            _stdin=lambda: "The Urgency of Interpretability\n\nIn the decade I have worked in AI.",
        )
        meta, body = parse((p.inbox_scripts / f"{res['run_id']}.md").read_text())
        assert meta["author"] == "Dario Amodei"
        assert body.startswith("This is The Urgency of Interpretability, an essay by Dario Amodei.")
        assert body.count("The Urgency of Interpretability") == 1  # title not spoken twice
        assert body.rstrip().endswith("In the decade I have worked in AI.")


def test_build_report_is_shownotes_parseable() -> None:
    report = build_report(
        title="Machines of Loving Grace",
        source_ref="https://darioamodei.com/essay/machines-of-loving-grace",
        summary="An essay on AI's upside.",
    )
    summary, sources = shownotes.extract(_write_tmp(report))
    assert summary == "An essay on AI's upside."
    assert len(sources) == 1
    assert "darioamodei.com" in sources[0]


def test_build_report_without_source_has_no_sources() -> None:
    report = build_report(title="From stdin", source_ref=None, summary="A reading.")
    summary, sources = shownotes.extract(_write_tmp(report))
    assert summary == "A reading."
    assert sources == []


def test_adapted_too_short_guard() -> None:
    # output that keeps most of the words is fine
    assert not adapted_too_short(src_words=1000, out_words=900)
    # output that collapses to a summary trips the guard
    assert adapted_too_short(src_words=1000, out_words=300)
    # empty input never trips (avoid div-by-zero)
    assert not adapted_too_short(src_words=0, out_words=0)


# --- orchestration (claude passes injected) --------------------------------

def _paths(tmp: str) -> Paths:
    p = Paths(root=Path(tmp))
    p.ensure_dirs()
    return p


def _write_tmp(text: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w")
    f.write(text)
    f.close()
    return Path(f.name)


def test_ingest_stdin_raw_writes_inbox_script() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        called = {"adapt": False, "fetch": False}

        def no_adapt(*a, **k):
            called["adapt"] = True
            raise AssertionError("raw mode must not call adapt")

        res = ingest_source(
            "-",
            raw=True,
            title="Piped Essay",
            date="2026-06-14",
            p=p,
            _stdin=lambda: "# Piped Essay\n\nThe body of the essay.",
            _adapt=no_adapt,
        )
        assert called["adapt"] is False
        dest = p.inbox_scripts / f"{res['run_id']}.md"
        assert dest.exists(), "raw ingest stages a script into inbox/scripts"
        meta, body = parse(dest.read_text())
        assert meta["title"] == "Piped Essay"
        assert "the body of the essay" in body.lower()
        assert "#" not in body, "markdown stripped in raw prose"


def test_ingest_file_runs_adapt_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        src = Path(tmp) / "essay.md"
        src.write_text("---\ntitle: My Essay\n---\nRaw essay prose, lightly written.")
        seen = {}

        def fake_adapt(source_path, out_path, model, author=None):
            seen["source_text"] = Path(source_path).read_text()
            cleaned = "Adapted spoken prose for the ear."
            Path(out_path).write_text(cleaned)
            return cleaned

        res = ingest_source(str(src), raw=False, date="2026-06-14", p=p, _adapt=fake_adapt)
        # the adapt pass reads the frontmatter-stripped source body
        assert "Raw essay prose" in seen["source_text"]
        assert "title:" not in seen["source_text"]
        dest = p.inbox_scripts / f"{res['run_id']}.md"
        meta, body = parse(dest.read_text())
        assert meta["title"] == "My Essay"
        assert body.strip() == "Adapted spoken prose for the ear."
        assert res["adapted"] is True


def test_ingest_url_fetches_then_adapts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        order = []

        def fake_fetch(url, out_path, model):
            order.append("fetch")
            text = "# Fetched Title\n\nFetched article body."
            Path(out_path).write_text(text)
            return text

        def fake_adapt(source_path, out_path, model, author=None):
            order.append("adapt")
            Path(out_path).write_text("Spoken version.")
            return "Spoken version."

        res = ingest_source(
            "https://darioamodei.com/essay/x",
            raw=False,
            date="2026-06-14",
            p=p,
            _fetch=fake_fetch,
            _adapt=fake_adapt,
        )
        assert order == ["fetch", "adapt"], "URL is fetched, then adapted"
        assert res["title"] == "Fetched Title"
        # the source URL ends up in the report's show-note sources
        report = (p.runs / res["run_id"] / "report.md").read_text()
        summary, sources = shownotes.extract(p.runs / res["run_id"] / "report.md")
        assert any("darioamodei.com" in s for s in sources)


def test_ingest_archives_source_and_report_in_run_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        res = ingest_source(
            "-",
            raw=True,
            title="Archived",
            date="2026-06-14",
            p=p,
            _stdin=lambda: "Some essay text.",
        )
        run_dir = p.runs / res["run_id"]
        assert (run_dir / "source.md").exists()
        assert (run_dir / "report.md").exists()
        # the staged script was moved (os.replace) out of the run dir into inbox
        assert not (run_dir / "script.md").exists()
        assert (p.inbox_scripts / f"{res['run_id']}.md").exists()


def test_ingest_source_url_override_sets_shownote_source() -> None:
    # read the text from stdin/a file but cite a canonical URL in the show notes
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        res = ingest_source(
            "-",
            raw=True,
            title="Cited",
            date="2026-06-14",
            p=p,
            source_url="https://darioamodei.com/essay/x",
            _stdin=lambda: "Body text here.",
        )
        _, sources = shownotes.extract(p.runs / res["run_id"] / "report.md")
        assert any("darioamodei.com/essay/x" in s for s in sources)
        assert res["source"] == "https://darioamodei.com/essay/x"


def test_ingest_warns_when_adapt_overcondenses() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = _paths(tmp)
        src = Path(tmp) / "long.md"
        src.write_text(" ".join(f"word{i}" for i in range(1000)))

        def shrinking_adapt(source_path, out_path, model, author=None):
            Path(out_path).write_text("a very short summary")
            return "a very short summary"

        res = ingest_source(str(src), raw=False, date="2026-06-14", p=p, _adapt=shrinking_adapt)
        assert res["warning"], "over-condensed adaptation must surface a warning"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
