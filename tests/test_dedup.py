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
    import json
    from earworm import dedup

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "dedup.md"
    candidates = ["SQLite documents", "SQLite concurrency", "A fresh story"]
    covered = ["SQLite application format", "Why reasoning has a wasted tail"]
    search = {"decisions": [
        {"n": 1, "matches": [1], "reason": "Same document mechanism"},
        {"n": 2, "matches": [1], "reason": "Possibly related"},
        {"n": 3, "matches": [], "reason": "Distinct"},
    ]}
    calls = []
    def judge(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            assert "1. SQLite application format" in prompt
            return json.dumps(search)
        assert "Why reasoning has a wasted tail" not in prompt
        return json.dumps({"decisions": [
            {"n": 2, "duplicate": False, "reason": "Concurrency differs from document format"},
            {"n": 1, "duplicate": True, "reason": "Same transaction and portability payoff"},
        ]})
    kept, dropped = dedup.filter_new(candidates, covered, judge=judge, prompt_path=prompt_path)
    assert kept == candidates[1:]
    assert [d.candidate for d in dropped] == candidates[:1]
    assert "SQLite application format" in dropped[0].matches
    assert len(calls) == 2

    def never(_prompt):
        raise AssertionError("unnecessary model call")
    assert dedup.filter_new(candidates, [], judge=never, prompt_path=prompt_path) == (candidates, [])
    assert dedup.filter_new([], covered, judge=never, prompt_path=prompt_path) == ([], [])
    new = json.dumps({"decisions": [
        {"n": n, "matches": [], "reason": "Distinct"} for n in range(1, 4)
    ]})
    calls.clear()
    def all_new(prompt):
        calls.append(prompt)
        return new
    assert dedup.filter_new(candidates, covered, judge=all_new, prompt_path=prompt_path) == (candidates, [])
    assert len(calls) == 1
    assert dedup.parse_duplicate_indices("```json\n" + json.dumps(search) + "\n```", 3, covered) == {1: [covered[0]], 2: [covered[0]]}

    expanded = json.loads(json.dumps(search))
    expanded["decisions"][0]["matches"] = [{"n": 1, "reason": "Same evidence"}]
    assert dedup.parse_duplicate_indices(json.dumps(expanded), 3, covered) == {1: [covered[0]], 2: [covered[0]]}

    malformed = ["not json", "{}", '{"decisions": []}', '{"duplicates": []}',
                 '{"decisions": [{"n":1,"n":2,"matches":[1],"reason":"x"}]}']
    for field, value in [("n", True), ("n", 1.5), ("n", "1"), ("n", 4),
                         ("matches", True), ("matches", [3]),
                         ("matches", ["1"]), ("matches", [True]),
                         ("matches", [{"n": True, "reason": "x"}]),
                         ("matches", [{"n": 1}]), ("matches", [{"n": 1, "reason": ""}]),
                         ("matches", [1, 1]), ("matches", [1, 2, 1, 2]), ("reason", ""), ("reason", None)]:
        data = json.loads(json.dumps(search))
        data["decisions"][0][field] = value
        malformed.append(json.dumps(data))
    malformed.append(json.dumps({"decisions": search["decisions"] + search["decisions"][:1]}))
    for text in malformed:
        try:
            dedup.parse_duplicate_indices(text, 3, covered)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted incomplete/invalid decision: {text}")

    # A related first result cannot hide a true match later in the shortlist.
    shortlist = json.dumps({"decisions": [
        {"n": 1, "matches": [1, 2], "reason": "Possible matches"},
    ]})
    confirmation = json.dumps({"decisions": [
        {"n": 1, "duplicate": False, "reason": "Different mechanism"},
        {"n": 2, "duplicate": True, "reason": "Same evidence and payoff"},
    ]})
    responses = iter([shortlist, confirmation])
    kept, dropped = dedup.filter_new(["Repeated story"], covered, judge=lambda _: next(responses), prompt_path=prompt_path)
    assert kept == [] and covered[1] in dropped[0].matches

    for confirmation in ['{"decisions": []}', json.dumps({"decisions": [
        {"n": 1, "duplicate": "false", "reason": "Distinct"},
        {"n": 2, "duplicate": False, "reason": "Distinct"},
    ]})]:
        responses = iter([json.dumps(search), confirmation])
        try:
            dedup.filter_new(candidates, covered, judge=lambda _: next(responses), prompt_path=prompt_path)
        except ValueError:
            pass
        else:
            raise AssertionError("Accepted invalid confirmation")


def _incomplete_screening_does_not_queue() -> None:
    from unittest.mock import patch
    from earworm import autogen, llm
    for bad_stage in ("search", "confirmation"):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"EARWORM_HOME": tmp}):
            d = _fresh_db(tmp)
            d.add_topic("An earlier topic")
            p = paths()
            (p.root / "prompts").mkdir(parents=True, exist_ok=True)
            source = Path(__file__).resolve().parent.parent / "prompts"
            for name in ("autogen.md", "dedup.md", "dedup_confirm.md"):
                (p.prompts / name).write_text((source / name).read_text())
            responses = ["New proposal", "{}"] if bad_stage == "search" else [
                "New proposal",
                '{"decisions":[{"n":1,"matches":[1],"reason":"Related"}]}', "{}"
            ]
            with patch.object(llm, "run_text", side_effect=responses):
                try:
                    autogen.generate(count=1)
                except llm.LLMError as exc:
                    assert "no proposals queued" in str(exc)
                else:
                    raise AssertionError("Malformed screening was ignored")
            assert len(d.list_topics()) == 1
    paths.cache_clear()


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
    _incomplete_screening_does_not_queue()
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
