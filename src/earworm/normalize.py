"""Pre-G2P text normalization for cases Kokoro mishandles.

Three jobs, all deterministic and run before the lexicon overrides:

0. Punctuation Kokoro gives no pause for: em/en dashes and sentence colons run
   the surrounding words together. Dashes become a comma (brief pause), a colon
   after a letter becomes a period (full stop). Digit:digit timestamps (3:00)
   are preserved — only a colon following a letter is treated as a sentence colon.

1. Spoken-form rewrites for things verified to break the misaki G2P —
   coordinates (degree glitch + hemisphere letters + fraction-as-magnitude),
   bare degree symbols, and a leading minus before a number.

2. Acronym / technical-term normalization so scripts can be written in plain
   standard form (AI, API, HTTP) and still read correctly:
   - all-caps acronyms (2+ letters) become dot-separated ("RFC" -> "R.F.C."),
     which forces a reliable letter-by-letter read regardless of misaki's
     acronym heuristics;
   - acronyms with a lexicon entry (API, DNS, RAG, LLM, ...) and a whitelist of
     pronounceable ones (NASA, WASM, CRUD, ...) are left intact so their curated
     IPA — or misaki's own word reading — wins instead;
   - alphanumeric stack codes expand ("D1" -> "D-one", "R2" -> "R-two");
   - a few technical terms get fixed spellings ("SQL" -> "sequel").

Order matters: technical substitutions run before the generic acronym pass so
"SQL" becomes "sequel" rather than "S.Q.L.". Everything is idempotent — a second
pass over already-normalized text is a no-op.
"""
from __future__ import annotations

import re

_HEMI = {"N": "north", "S": "south", "E": "east", "W": "west"}
_DIGITS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

# Em/en dash -> comma pause; sentence colon (after a letter) -> full stop. Only
# spaces/tabs around them are absorbed, never newlines, so paragraph breaks (and
# the `---` section markers, which are hyphens) survive untouched. The colon
# lookbehind requires a letter, so digit:digit timestamps like 3:00 are kept.
_DASH = re.compile(r"[ \t]*[—–][ \t]*")
_SENT_COLON = re.compile(r"(?<=[A-Za-z])[ \t]*:[ \t]*")

# Parentheticals: Kokoro gives ( ) no pause, so the aside runs into the host
# sentence. Convert to a comma-delimited aside; a comma left directly before
# closing punctuation is then collapsed (", ." -> ".").
_PAREN = re.compile(r"[ \t]*\(([^()\n]+)\)")
_COMMA_PUNCT = re.compile(r",\s*([.,;!?])")

# Ellipses are banned by the prompts, and an acronym that lands at a sentence end
# leaves a stray double dot ("API." -> "A.P.I.."). Either run of consecutive dots
# — or a literal ellipsis char — collapses to a single full stop. A trailing
# space is only re-emitted when the original had following whitespace, so a
# sentence-final "A.P.I.." becomes "A.P.I." with no dangling space.
_ELLIPSIS_OR_DUPES = re.compile(r"[ \t]*(?:\.{2,}|…)([ \t]*)")

# Symbols misaki mis-voices (verified: it already handles %, &, $, and "/" between
# words correctly, so those are deliberately left alone — normalizing them would
# be redundant and risks regressing misaki's own number handling):
#   ~  before a number -> "about" ("~50%" phonemizes to a ❓ glitch + "fifty");
#   a colon between single digits is a RATIO -> "to" ("3:1" glitches; "3:00", a
#   clock time with a 2-digit tail, is left for its existing carve-out).
_APPROX = re.compile(r"~[ \t]*(?=\d)")
# Ratio = colon with a SINGLE-digit right side ("3:1", "16:9"). A 2-digit tail is
# a clock time ("3:00", "12:30") and is left for the existing carve-out.
_RATIO = re.compile(r"\b(\d+)[ \t]*:[ \t]*(\d)(?!\d)")

_COORD = re.compile(r"(-?)(\d+)\.(\d+)\s*°\s*([NSEW])\b")
_DEG_C = re.compile(r"°\s?C\b")
_DEG_F = re.compile(r"°\s?F\b")
_DEG = re.compile(r"°")
_LEADING_MINUS = re.compile(r"(?<![\w.])-(?=\d)")

# Acronyms left intact by the dot-expansion pass so a downstream pronunciation
# wins. Two sources feed the whitelist: this static set of plain pronounceable
# acronyms that misaki already says as words (NASA, OPEC, ...) or that carry a
# curated lexicon entry with no all-caps key derivation (ICANN, NVIDIA, CUDA),
# and — added at match time — every bare all-caps lexicon key (API, DNS, RAG,
# LLM, ...) via `lexicon.acronym_words()`, so the lexicon's curated IPA is never
# pre-empted by our coarse "A.P.I.".
_SAY_AS_WORD = frozenset({
    "WASM", "CRUD", "FOSS", "NASA", "OPEC", "NATO", "RAM", "ROM", "SIM", "PIN",
    "ICANN",   # lexicon gives it "EYE-can", not "I.C.A.N.N."
    "NVIDIA",  # lexicon gives it "en-VID-ee-ah", not "N.V.I.D.I.A."
    "CUDA",    # lexicon gives it "KOO-dah", not "C.U.D.A."
})


def _lexicon_acronyms() -> frozenset[str]:
    """Bare all-caps lexicon keys, fetched lazily (lru_cached in the lexicon
    module, so this stays cheap to call per match)."""
    from .lexicon import acronym_words

    return acronym_words()

# Technical terms misaki mis-speaks letter-by-letter or mangles. Fixed spoken
# spellings, applied case-insensitively, longest-first (SQLite before SQL).
_TECH_SUBS = [
    ("SQLite", "sequel-lite"),
    ("Postgres", "post-gres"),
    ("nginx", "engine-X"),
    ("SQL", "sequel"),
]

# Script-level phonetic hints: "Dario Amodei [ah-mo-DAY]". The bracket follows the
# word(s) it respells; the hint's whitespace-token count decides how many of the
# immediately-preceding tokens it REPLACES (not appends to), so a one-token hint
# swaps one word ("Amodei [ah-mo-DAY]" -> "ah-mo-DAY", keeping "Dario") and a
# two-token hint swaps two ("Andrej Karpathy [ON-dray kar-PAH-thee]" -> the full
# hint). Up to 5 preceding tokens are captured; a token is any run of word chars,
# so lowercase foreign phrases ("force majeure [forss mah-zhur]"), name particles
# ("Werner von Braun [von BROWN]"), and digit-bearing tokens ("R2-D2 [ar-too
# dee-too]") are all eligible — the old capitalized-only pattern left those to the
# stray pass, which kept BOTH the original and the hint (double-speak). A per-call
# cache then rewrites later BARE mentions of the same name to the same form.
_HINT = re.compile(r"((?:[\w.'’\-]+[ \t]+){0,4}[\w.'’\-]+)[ \t]*\[([^\[\]\n]+)\]")
# Any bracket left after the hint pass (bracket with no word before it, or a plain
# aside that isn't a respelling) — keep the inner text, drop the brackets, so
# Kokoro never voices "[".
_STRAY_BRACKET = re.compile(r"\[([^\[\]\n]+)\]")
# Trailing possessive on a name being respelled ("Amodei's [ah-mo-DAY]"); split
# off before matching so the base name resolves, then re-attached to the hint.
_POSSESSIVE = re.compile(r"['’]s$")


def _split_possessive(word: str) -> tuple[str, str]:
    m = _POSSESSIVE.search(word)
    return (word[: m.start()], m.group(0)) if m else (word, "")


def _looks_phonetic(hint: str) -> bool:
    """Whether a bracketed span is a phonetic respelling (replace the preceding
    word) versus a plain aside (leave it, just unwrap the brackets).

    A respelling carries a phonetic signature: a syllable hyphen between letters
    ("ah-mo-DAY", "mah-zhur") or an interior stress capital ("ON-dray", "DAY").
    A plain aside ("aside", "see note") has neither. A bare all-lowercase
    single-syllable hint with no hyphen is indistinguishable from an aside and
    stays as-is — rare, since the prompt convention always breaks syllables."""
    if re.search(r"[A-Za-z]-[A-Za-z]", hint):
        return True
    letters = [c for c in hint if c.isalpha()]
    return any(c.isupper() for c in letters[1:])

# Roman numerals the dot-expander would otherwise letter-spell (misaki reads "II"
# as "eye-eye"). Spoken as their number word instead. Only low-ambiguity forms:
# IV (intravenous) and VI (the vi editor / "six") are left out on purpose.
_ROMAN_WORDS = {
    "II": "two", "III": "three", "VII": "seven", "VIII": "eight",
    "IX": "nine", "XI": "eleven", "XII": "twelve", "XIII": "thirteen",
}
_ROMAN_RE = re.compile(r"\b(" + "|".join(sorted(_ROMAN_WORDS, key=len, reverse=True)) + r")\b")

# All-caps tokens that are real words (or word-acronyms) misaki already voices
# correctly when left intact — dotting them ("R.A.I.S.E.") is the bug. CRISPR ->
# "crisper", RAISE -> "raise", CAR (in CAR-T) -> "car". ERCOT is handled by a
# lexicon entry, so fix #1's derived whitelist already covers it.
_INTACT_WORDS = frozenset({"CRISPR", "RAISE", "CAR"})

# A run of 2+ uppercase letters as a whole word, with an optional plural "s"
# ("CEOs" -> "C.E.O's"). The leading/trailing boundaries keep it whole-word.
_ACRONYM = re.compile(r"\b([A-Z]{2,})(s)?\b")
# Single uppercase letter glued to a single digit: stack codes like D1/R2/S3.
_ALNUM_CODE = re.compile(r"\b([A-Z])([0-9])\b")


def _emphasis_words(text: str) -> frozenset[str]:
    """Lowercased forms of 4+-letter tokens that appear in the text in non-all-caps
    form. An all-caps token whose lowercase twin also appears normally is emphasis,
    not an initialism ("...a HUGE deal, and it is huge"), so misaki reads it fine as
    a word and the dot-expander leaves it. The 4-char floor avoids collisions
    between short initialisms and function words (US/us, WHO/who, IT/it)."""
    return frozenset(
        tok.lower() for tok in re.findall(r"[A-Za-z]{4,}", text) if not tok.isupper()
    )


def _spell_fraction(frac: str) -> str:
    return " ".join(_DIGITS[d] for d in frac)


def _coord(m: re.Match) -> str:
    sign = "negative " if m.group(1) else ""
    return f"{sign}{m.group(2)} point {_spell_fraction(m.group(3))} degrees {_HEMI[m.group(4)]}"


def _expand_acronym(m: re.Match, emphasis: frozenset[str] = frozenset()) -> str:
    word, plural = m.group(1), m.group(2) or ""
    if word in _SAY_AS_WORD or word in _INTACT_WORDS:
        return m.group(0)  # pronounceable word (and its plural): misaki says it
    if len(word) >= 4 and word.lower() in emphasis:
        return m.group(0)  # an emphasized ordinary word, not an initialism
    if word in _lexicon_acronyms():
        # Curated IPA lives in the lexicon; keep the word so apply_overrides can
        # rewrite it. A plural takes an apostrophe-s so `\bWORD\b` still matches
        # ("API's" -> "[API](/../)'s") and misaki voices the /z/ instead of gluing
        # an extra letter onto the last one.
        return f"{word}'s" if plural else word
    # Plural: dot the letters but join the "s" with an apostrophe ("CEOs" ->
    # "C.E.O's"). A trailing ".s" makes misaki voice the letter S ("ess"); the
    # apostrophe-s reads as a plural /z/ ("...O-z"). Singular keeps a final dot.
    if plural:
        return ".".join(word) + "'s"
    return ".".join(word) + "."


def _alnum_code(m: re.Match) -> str:
    return f"{m.group(1)}-{_DIGITS[m.group(2)]}"


def _tech_subs(text: str) -> str:
    for term, repl in _TECH_SUBS:
        text = re.sub(rf"\b{re.escape(term)}\b", repl, text, flags=re.IGNORECASE)
    return text


def _apply_phonetic_hints(text: str) -> str:
    """Replace "Name [hint]" markers with the hint (never voicing both), and reuse
    it for later bare mentions via a per-call cache.

    Three refinements keep the audio clean. Hints are lowercased so neither our
    acronym pass nor misaki's own all-caps heuristic mistakes "ON-dray"/"DAY" for
    letter-by-letter acronyms (misaki reads "ON-dray" as "OH-EN-dray"). A name
    word already in the lexicon keeps its spelling so its curated IPA wins over a
    coarse free-form hint — the lexicon is verified, hints fill the long tail. And
    a bracket whose content isn't a respelling (see `_looks_phonetic`) is left for
    the stray-bracket pass, which unwraps it in place rather than treating a plain
    aside as a name to overwrite.
    """
    from .lexicon import known_words

    known = known_words()
    cache: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        name_run, hint = m.group(1), m.group(2).strip()
        if not hint or not _looks_phonetic(hint):
            return m.group(0)  # a plain aside, not a respelling -> leave for _STRAY_BRACKET
        tokens = hint.split()
        words = name_run.split()
        n = min(len(tokens), len(words))
        kept, replaced = words[: len(words) - n], words[len(words) - n :]
        out: list[str] = list(kept)
        if len(replaced) == len(tokens):
            # token/word counts line up -> decide per word, cache the spoken form
            for w, t in zip(replaced, tokens):
                base, poss = _split_possessive(w)
                if base.lower() in known:
                    out.append(w)                       # lexicon wins; keep incl. possessive
                else:
                    out.append(t.lower() + poss)
                    cache[base] = t.lower()
        elif replaced and all(_split_possessive(w)[0].lower() in known for w in replaced):
            out.extend(replaced)                        # whole span is curated
        else:
            base_last, poss = _split_possessive(replaced[-1]) if replaced else ("", "")
            out.append(hint.lower() + poss)
            cache[" ".join([*replaced[:-1], base_last]).strip()] = hint.lower()
        return " ".join(out)

    text = _HINT.sub(repl, text)
    # later bare mentions -> same spoken form (longest cache key first). A function
    # replacement sidesteps re.sub's backslash/group-reference handling in the value.
    for key in sorted(cache, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(key)}\b", lambda m, v=cache[key]: v, text)
    text = _STRAY_BRACKET.sub(lambda m: m.group(1).lower(), text)
    return text


def normalize_for_speech(text: str) -> str:
    """Rewrite punctuation/degrees/coordinates/minus + acronyms/codes to spoken forms. Idempotent."""
    text = _apply_phonetic_hints(text)     # 0. "Name [hint]" -> spoken hint (+ cache reuse)
    text = _DASH.sub(", ", text)           #    em/en dash -> comma pause
    text = _SENT_COLON.sub(". ", text)     #    sentence colon -> full stop (3:00 kept)
    text = _PAREN.sub(lambda m: f", {m.group(1).strip()},", text)  # (aside) -> , aside,
    text = _COMMA_PUNCT.sub(r"\1", text)   #    ", ." left by the paren pass -> "."
    text = _COORD.sub(_coord, text)        # 1. coordinates (before bare degree/minus)
    text = _DEG_C.sub(" degrees Celsius", text)
    text = _DEG_F.sub(" degrees Fahrenheit", text)
    text = _DEG.sub(" degrees", text)      # bare ° would otherwise be an unknown-phoneme glitch
    text = _LEADING_MINUS.sub("negative ", text)
    text = _APPROX.sub("about ", text)     # 1b. ~50 -> about 50 (bare ~ is a G2P glitch)
    text = _RATIO.sub(r"\1 to \2", text)   #     3:1 -> 3 to 1 (a ratio colon glitches too)
    text = _tech_subs(text)                # 2. SQL -> sequel, before the generic acronym pass
    text = _ROMAN_RE.sub(lambda m: _ROMAN_WORDS[m.group(1)], text)  # 2b. II -> two
    text = _ALNUM_CODE.sub(_alnum_code, text)   # 3. D1 -> D-one
    emphasis = _emphasis_words(text)            # words that also appear in non-caps form
    text = _ACRONYM.sub(lambda m: _expand_acronym(m, emphasis), text)  # 4. RFC -> R.F.C.
    # 5. collapse ellipses + the ".." an acronym at a sentence end produces
    text = _ELLIPSIS_OR_DUPES.sub(lambda m: "." + (" " if m.group(1) else ""), text)
    return text
