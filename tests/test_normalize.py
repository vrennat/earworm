"""Standalone tests for earworm.normalize. Run: uv run python tests/test_normalize.py

No pytest dependency — plain asserts so it runs anywhere the package imports.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from earworm.normalize import normalize_for_speech as n  # noqa: E402


def check(text: str, expected: str) -> None:
    got = n(text)
    assert got == expected, f"\n  in:  {text!r}\n  got: {got!r}\n  exp: {expected!r}"


def main() -> int:
    # all-caps acronyms -> dot-separated
    check("We built an API.", "We built an A.P.I..")
    check("AI and LLM and HTTP", "A.I. and L.L.M. and H.T.T.P.")
    check("The spec, also called RFC", "The spec, also called R.F.C.")
    # plural acronyms read as plurals: dotted letters + apostrophe-s (a trailing
    # ".s" would voice the letter S; "...I's" reads as the /z/ plural)
    check("Lots of APIs and LLMs", "Lots of A.P.I's and L.L.M's")
    # NVIDIA/CUDA are whitelisted so the lexicon (not the dot-expander) pronounces them
    check("NVIDIA and CUDA", "NVIDIA and CUDA")
    # say-as-word whitelist is left intact (lexicon handles pronunciation)
    check("WASM CRUD FOSS NASA OPEC NATO RAM ROM SIM PIN",
          "WASM CRUD FOSS NASA OPEC NATO RAM ROM SIM PIN")
    check("PINs stay intact", "PINs stay intact")
    # ICANN is whitelisted (lexicon pronounces it "EYE-can"), not letter-by-letter
    check("ICANN sets policy", "ICANN sets policy")
    # alphanumeric stack codes
    check("Cloudflare D1, R2, and S3", "Cloudflare D-one, R-two, and S-three")
    # technical substitutions win over the generic acronym pass
    check("SQL and SQLite and Postgres and nginx",
          "sequel and sequel-lite and post-gres and engine-X")
    check("a postgres db", "a post-gres db")  # case-insensitive
    # preexisting spoken rewrites still work
    check("-12 below", "negative 12 below")
    # single letters and ordinary words are untouched
    check("I is a letter", "I is a letter")
    check("the cat sat", "the cat sat")
    # phonetic hints: a one-token hint replaces one preceding word, a two-token
    # hint replaces two; the hint is lowercased and reused for later bare mentions.
    # (Use clearly-unknown names so the assertion doesn't depend on lexicon contents,
    # which intentionally let a curated IPA win over a hint for known names.)
    check("Meet Zylonth [zy-LONTH] now. Zylonth waved.",
          "Meet zy-lonth now. zy-lonth waved.")
    check("Talk to Qorvlen Draxhal [KOR-ven DRAKS-hahl] today.",
          "Talk to kor-ven draks-hahl today.")
    check("A stray [aside] survives.", "A stray aside survives.")
    # parentheticals -> comma asides (Kokoro gives parens no pause)
    check("The model (released last year) won.", "The model, released last year, won.")
    check("It ended badly (for them).", "It ended badly, for them.")
    # idempotent (a second pass over already-normalized text is a no-op)
    sample = "API and SQL and D1 and APIs and Zylonth [zy-LONTH] (an aside)"
    assert n(n(sample)) == n(sample), "normalize is not idempotent"

    print("all normalize tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
