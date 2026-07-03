"""Standalone tests for earworm.transcript. Run: uv run python tests/test_transcript.py

No pytest dependency — plain asserts so it runs anywhere the package imports.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm.transcript import build_vtt, dedot_acronyms as d  # noqa: E402


def check(text: str, expected: str) -> None:
    got = d(text)
    assert got == expected, f"\n  in:  {text!r}\n  got: {got!r}\n  exp: {expected!r}"


def main() -> int:
    # dotted acronyms collapse back to plain letters for display
    check("The I.N.M.I. and O.C.D. link", "The INMI and OCD link")
    # a trailing dot at end of the cue is a sentence end -> keep the period
    check("built an R.F.C.", "built an RFC.")
    # a mid-text acronym before a Capital word is a compound noun, not a sentence
    # break ("UK Parliament", "UC Davis") -> the dot just drops
    check("the U.K. Parliament voted", "the UK Parliament voted")
    check("at U.C. Davis in 2017", "at UC Davis in 2017")
    check("in the U.K. and U.S.", "in the UK and US.")
    # the normalizer's plural trick ("C.E.O's") displays as a real plural
    check("many C.E.O's agreed", "many CEOs agreed")
    check("old A.O.L's era", "old AOLs era")
    # a possessive (dot before the apostrophe) keeps the apostrophe
    check("A.I.'s reach", "AI's reach")
    # a leftover double period (old renders) collapses to one
    check("the A.I.. was", "the AI. was")
    # a lone initial and mixed-case abbreviations are NOT acronyms — left alone
    check("J. Robert Oppenheimer", "J. Robert Oppenheimer")
    check("a Ph.D. thesis", "a Ph.D. thesis")
    check("e.g. this", "e.g. this")
    # plain prose is untouched
    check("nothing to change here", "nothing to change here")

    # build_vtt de-dots cue text and keeps timestamps aligned to segment audio
    vtt = build_vtt([("We built an A.P.I. today", 0.0, 2.5)])
    assert "We built an API today" in vtt, vtt
    assert "A.P.I." not in vtt, vtt
    assert "00:00:00.000 --> 00:00:02.500" in vtt, vtt
    # empty/whitespace segments are dropped
    assert build_vtt([("   ", 0.0, 1.0)]).strip() == "WEBVTT", build_vtt([("   ", 0.0, 1.0)])

    print("all transcript tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
