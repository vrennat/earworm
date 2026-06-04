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
   - all-caps acronyms (2+ letters) become dot-separated ("API" -> "A.P.I."),
     which forces a reliable letter-by-letter read regardless of misaki's
     acronym heuristics;
   - a whitelist of pronounceable acronyms (NASA, WASM, CRUD, ...) is left
     intact so they're spoken as words;
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

_COORD = re.compile(r"(-?)(\d+)\.(\d+)\s*°\s*([NSEW])\b")
_DEG_C = re.compile(r"°\s?C\b")
_DEG_F = re.compile(r"°\s?F\b")
_DEG = re.compile(r"°")
_LEADING_MINUS = re.compile(r"(?<![\w.])-(?=\d)")

# Acronyms left intact by the dot-expansion pass — either spoken as a plain word
# or handed off to a custom lexicon pronunciation (e.g. ICANN -> "EYE-can").
_SAY_AS_WORD = frozenset({
    "WASM", "CRUD", "FOSS", "NASA", "OPEC", "NATO", "RAM", "ROM", "SIM", "PIN",
    "ICANN",   # lexicon gives it "EYE-can", not "I.C.A.N.N."
    "NVIDIA",  # lexicon gives it "en-VID-ee-ah", not "N.V.I.D.I.A."
    "CUDA",    # lexicon gives it "KOO-dah", not "C.U.D.A."
})

# Technical terms misaki mis-speaks letter-by-letter or mangles. Fixed spoken
# spellings, applied case-insensitively, longest-first (SQLite before SQL).
_TECH_SUBS = [
    ("SQLite", "sequel-lite"),
    ("Postgres", "post-gres"),
    ("nginx", "engine-X"),
    ("SQL", "sequel"),
]

# Script-level phonetic hints: "Dario Amodei [ah-mo-DAY]". The bracket follows
# the name it spells; the hint's whitespace-token count decides how many of the
# immediately-preceding capitalized words it replaces, so a one-token hint swaps
# one word ("Amodei [ah-mo-DAY]" -> "ah-mo-DAY", keeping "Dario") and a two-token
# hint swaps two ("Andrej Karpathy [ON-dray kar-PAH-thee]" -> the full hint).
# Up to 4 leading capitalized words are captured; the replacement trims to the
# hint's token count. A per-call cache then rewrites later BARE mentions of the
# same name to the same spoken form.
_HINT = re.compile(
    r"((?:[A-Z][A-Za-z.'’\-]*\s+){0,4}[A-Z][A-Za-z.'’\-]*)\s*\[([^\[\]\n]+)\]"
)
# Any bracket left after the hint pass (a hint with no capitalized word before it,
# or a stray) — keep the inner text, drop the brackets, so Kokoro never voices "[".
_STRAY_BRACKET = re.compile(r"\[([^\[\]\n]+)\]")

# A run of 2+ uppercase letters as a whole word, with an optional plural "s"
# ("APIs" -> "A.P.I's"). The leading/trailing boundaries keep it whole-word.
_ACRONYM = re.compile(r"\b([A-Z]{2,})(s)?\b")
# Single uppercase letter glued to a single digit: stack codes like D1/R2/S3.
_ALNUM_CODE = re.compile(r"\b([A-Z])([0-9])\b")


def _spell_fraction(frac: str) -> str:
    return " ".join(_DIGITS[d] for d in frac)


def _coord(m: re.Match) -> str:
    sign = "negative " if m.group(1) else ""
    return f"{sign}{m.group(2)} point {_spell_fraction(m.group(3))} degrees {_HEMI[m.group(4)]}"


def _expand_acronym(m: re.Match) -> str:
    word, plural = m.group(1), m.group(2) or ""
    if word in _SAY_AS_WORD:
        return m.group(0)
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
    """Strip "Name [hint]" markers, voicing the hint, and reuse it for later bare
    mentions via a per-call cache.

    Two refinements keep the audio clean. Hints are lowercased so neither our
    acronym pass nor misaki's own all-caps heuristic mistakes "ON-dray"/"DAY" for
    letter-by-letter acronyms (misaki reads "ON-dray" as "OH-EN-dray"). And a name
    word already in the lexicon keeps its spelling so its curated IPA wins over a
    coarse free-form hint — the lexicon is verified, hints fill the long tail.
    """
    from .lexicon import known_words

    known = known_words()
    cache: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        name_run, hint = m.group(1), m.group(2).strip()
        tokens = hint.split()
        words = name_run.split()
        n = min(len(tokens), len(words))
        kept, replaced = words[: len(words) - n], words[len(words) - n :]
        out: list[str] = list(kept)
        if len(replaced) == len(tokens):
            # token/word counts line up -> decide per word, cache the spoken form
            for w, t in zip(replaced, tokens):
                if w.lower() in known:
                    out.append(w)                       # lexicon wins for this word
                else:
                    out.append(t.lower())
                    cache[w] = t.lower()
        elif all(w.lower() in known for w in replaced):
            out.extend(replaced)                        # whole span is curated
        else:
            out.append(hint.lower())
            cache[" ".join(replaced)] = hint.lower()
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
    text = _COORD.sub(_coord, text)        # 1. coordinates (before bare degree/minus)
    text = _DEG_C.sub(" degrees Celsius", text)
    text = _DEG_F.sub(" degrees Fahrenheit", text)
    text = _DEG.sub(" degrees", text)      # bare ° would otherwise be an unknown-phoneme glitch
    text = _LEADING_MINUS.sub("negative ", text)
    text = _tech_subs(text)                # 2. SQL -> sequel, before the generic acronym pass
    text = _ALNUM_CODE.sub(_alnum_code, text)   # 3. D1 -> D-one
    text = _ACRONYM.sub(_expand_acronym, text)  # 4. API -> A.P.I. (whitelist kept intact)
    return text
