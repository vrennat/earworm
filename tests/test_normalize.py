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
    # acronyms with a lexicon entry are left intact so the lexicon's curated IPA
    # (not our coarse dot-expansion) pronounces them; API/AI/LLM are all in it.
    check("We built an API.", "We built an API.")
    check("AI and LLM and HTTP", "AI and LLM and H.T.T.P.")  # HTTP has no entry -> dotted
    # an acronym with no lexicon entry still dot-separates for a letter-by-letter read
    check("The spec, also called RFC", "The spec, also called R.F.C.")
    # a non-lexicon acronym at a sentence end must not leave a double period
    check("We shipped an RFC.", "We shipped an R.F.C.")
    check("Then came HTTP. Then more.", "Then came H.T.T.P. Then more.")
    # ellipses are banned by the prompts -> collapse to a single full stop
    check("Wait... really?", "Wait. really?")
    check("So on and on…", "So on and on.")
    check("One… two… three.", "One. two. three.")
    # plural of a lexicon acronym keeps an apostrophe-s so `\bAPI\b` still matches
    # in apply_overrides and misaki voices the /z/ ("API's" -> "[API](/../)'s")
    check("Lots of APIs and LLMs", "Lots of API's and LLM's")
    # plural of a non-lexicon acronym dots the letters + apostrophe-s ("CEOs" ->
    # "C.E.O's"): a trailing ".s" would voice the letter S; "...O's" reads as /z/
    check("Lots of CEOs met", "Lots of C.E.O's met")
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
    # a lowercase foreign phrase is REPLACED by its hint, not spoken then hinted
    check("It was force majeure [forss mah-zhur].", "It was forss mah-zhur.")
    # a name particle is captured into the replaced span (no dangling "von")
    check("Werner von Braun [von BROWN] rose.", "Werner von brown rose.")
    # a one-token hint keeps a preceding particle as-is and respells the name
    check("Ludwig von Braun [BRAWN] wrote.", "Ludwig von brawn wrote.")
    # digit-bearing tokens are eligible for a hint (old pattern skipped them,
    # sending them to the stray pass which kept both the name and the hint)
    check("Meet R2-D2 [artoo-detoo] here.", "Meet artoo-detoo here.")
    # a possessive on a respelled unknown name is re-attached after the hint
    check("Zorblax's [ZOR-blax] plan failed.", "zor-blax's plan failed.")
    # a bracketed aside with no phonetic signature is left in place (unwrapped)
    check("The result [see chapter 3] holds.", "The result see chapter 3 holds.")
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
