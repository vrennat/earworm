"""Tests for topic dedup on `earworm add`. Run: python tests/test_dedup.py

No pytest dependency — plain asserts. Uses a throwaway EARWORM_HOME so it never
touches a real workspace.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm.config import paths  # noqa: E402


def _fresh_db(tmp: str):
    os.environ["EARWORM_HOME"] = tmp
    paths.cache_clear()
    from earworm import db

    db.init()
    return db


def _semantic_dedup_tests() -> None:
    """The semantic gate catches same-idea-different-words repeats the lexical
    check misses, and its JSON parsing tolerates the shapes a model actually
    returns."""
    from pathlib import Path

    from earworm import dedup

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "dedup.md"
    candidates = [
        "Why hands-on knowledge dies faster than written knowledge",
        "How atomic clocks synchronize the power grid",
    ]
    covered = ["The Part Nobody Wrote Down — lost technologies and tacit skill"]

    # The judge flags candidate 1 as a rephrase of a covered episode.
    def judge_flags_first(_prompt: str) -> str:
        return '{"duplicates": [{"n": 1, "matches": "The Part Nobody Wrote Down"}]}'

    kept, dropped = dedup.filter_new(
        candidates, covered, judge=judge_flags_first, prompt_path=prompt_path
    )
    assert kept == ["How atomic clocks synchronize the power grid"], kept
    assert len(dropped) == 1 and dropped[0].candidate == candidates[0], dropped

    # No duplicates -> everything kept.
    kept, dropped = dedup.filter_new(
        candidates, covered, judge=lambda _p: '{"duplicates": []}', prompt_path=prompt_path
    )
    assert kept == candidates and dropped == [], (kept, dropped)

    # No prior coverage (or no candidates) -> no-op, judge never consulted.
    def judge_should_not_run(_prompt: str) -> str:  # pragma: no cover - must not be called
        raise AssertionError("judge called with nothing to compare")

    assert dedup.filter_new(candidates, [], judge=judge_should_not_run, prompt_path=prompt_path) == (
        candidates,
        [],
    )

    # A judge/parse failure propagates so the caller owns the fail-open policy.
    try:
        dedup.filter_new(candidates, covered, judge=lambda _p: "not json at all", prompt_path=prompt_path)
        raise AssertionError("expected ValueError on unparseable judge output")
    except ValueError:
        pass

    # parse tolerates a ```json fence, a bare array, and drops out-of-range indices
    assert dedup.parse_duplicate_indices('```json\n{"duplicates": [{"n": 2}]}\n```', 3) == {2: ""}
    assert dedup.parse_duplicate_indices('[{"n": 1, "matches": "x"}]', 2) == {1: "x"}
    assert dedup.parse_duplicate_indices('{"duplicates": [{"n": 9}]}', 3) == {}


def _proposal_parsing_tests() -> None:
    """autogen strips list markers and reads the PAPER: fast-track tag."""
    from earworm import autogen

    text = "\n".join(
        [
            "- A plain evergreen topic",
            "PAPER: Anthropic's J-space paper and what it means for oversight",
            "2. paper:  Case-insensitive tag with padding",
            "   ",
            "Another plain one",
        ]
    )
    parsed = autogen._parse_proposals(text)
    assert parsed == [
        ("A plain evergreen topic", 0),
        ("Anthropic's J-space paper and what it means for oversight", autogen.PAPER_PRIORITY),
        ("Case-insensitive tag with padding", autogen.PAPER_PRIORITY),
        ("Another plain one", 0),
    ], parsed


def _commentary_parsing_tests() -> None:
    """Chat furniture never becomes a topic. Each shape here reached the queue and
    shipped as an episode, because a research agent handed a non-topic invents one
    rather than failing: "Based on recent research, here are 3 timely topics:" (#81),
    "Sources:" (#60), and a bare citation link (#69)."""
    from earworm import autogen

    text = "\n".join(
        [
            "Based on recent research, here are 3 timely topics:",
            "When Reasoning Tokens Get Cheap, Who Judges the Judgment?",
            "How Robotics Learned to Scale Like LLMs",
            "",
            "Sources:",
            "- [Meta FAIR research releases](https://ai.meta.com/blog/meta-fair)",
            "- [arXiv cs.CL](https://arxiv.org/list/cs.CL/recent)",
        ]
    )
    assert autogen._parse_proposals(text) == [
        ("When Reasoning Tokens Get Cheap, Who Judges the Judgment?", 0),
        ("How Robotics Learned to Scale Like LLMs", 0),
    ], autogen._parse_proposals(text)

    # A colon inside a topic is not a heading, and a link inside a topic is not a citation.
    keeps = [
        "ICML 2026: what the awards actually signal",
        "Does [this paper](https://arxiv.org/abs/1) overturn the consensus?",
    ]
    assert autogen._parse_proposals("\n".join(keeps)) == [(k, 0) for k in keeps]

    # Commentary-only output queues nothing rather than queueing junk.
    assert autogen._parse_proposals("Here are your topics:\nSources:") == []

    # count caps the survivors, applied after commentary is stripped.
    capped = autogen._parse_proposals("Here are 2 topics:\nTopic one\nTopic two\nTopic three", 2)
    assert capped == [("Topic one", 0), ("Topic two", 0)], capped


def main() -> int:
    from earworm import db

    # normalize_topic folds case, punctuation, and whitespace to one key
    assert db.normalize_topic("The RAG Revolution!") == db.normalize_topic("the rag   revolution")
    assert db.normalize_topic("A, B, and C?") == "a b and c"
    assert db.normalize_topic("   ") == ""

    _semantic_dedup_tests()
    _proposal_parsing_tests()
    _commentary_parsing_tests()

    with tempfile.TemporaryDirectory() as tmp:
        d = _fresh_db(tmp)
        tid = d.add_topic("Why do songs get stuck in our heads?", source="manual")

        # an exact re-add is caught
        dup = d.find_duplicate_topic("Why do songs get stuck in our heads?")
        assert dup is not None and dup["id"] == tid, dup

        # a casing/punctuation variant is caught too (the 25-30 = 19-21 re-add bug)
        dup2 = d.find_duplicate_topic("why do SONGS get stuck in our heads")
        assert dup2 is not None and dup2["id"] == tid, dup2

        # a genuinely different topic is not a duplicate
        assert d.find_duplicate_topic("How do atomic clocks synchronize the grid?") is None

        # an empty/blank topic never matches
        assert d.find_duplicate_topic("   ") is None

    print("all dedup tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
