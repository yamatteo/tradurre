"""Sentence segmentation for French and Italian (PLAN.md, "Segmentation"; SPEC §3.1.3).

A boundary is a terminator (`.?!…`, any run of them), optional closers (`»”"’)]`, each optionally after
whitespace), whitespace, then the next sentence's start: optional openers (`«“"(—–`, or `-` and whitespace) and
an uppercase letter. Lowercase and digits never start a sentence, so `« Viens ! » dit-il.` stays whole. A single
`.` after an abbreviation or an initial is not a boundary.
"""

import re
import sys

# Every character `str.isupper()` accepts, as a regex class (`re` has no \p{Lu}).
_UPPER = "".join(re.escape(c) for c in map(chr, range(sys.maxunicode + 1)) if c.isupper())

_BOUNDARY = re.compile(
    r"([.?!…]+)"                        # terminator
    r"(?:\s*[»”\"’)\]])*"               # closers: the sentence ends after them
    rf"(?=\s+(?:[«“\"(—–]\s*|-\s+)*[{_UPPER}])"  # whitespace, openers, a capital
)

# Case-sensitive: Italian "a me." ends a sentence, "Me" (Maître) doesn't.
_ABBREVIATIONS = frozenset(
    "M MM Mme Mlle Mgr Dr Pr St Ste Me Sig Sigg Sig.ra Sig.na Dott Dott.ssa Prof Prof.ssa Avv Ing Mons SS "
    "cf p pp vol chap fig éd".split()
)
_TOKEN = re.compile(r"(?:[^\W\d_]|\.)*$")  # the token before the terminator: letters and inner dots ("l'Avv" → "Avv")


def _abbreviation(text: str, terminator: re.Match) -> bool:
    if terminator.group(1) != ".":
        return False
    end = terminator.start()
    token = _TOKEN.search(text, max(0, end - 20), end).group(0).lstrip(".")  # abbreviations are short
    return token in _ABBREVIATIONS or (len(token) == 1 and token.isupper())


def split_sentences(text: str) -> list[str]:
    """The sentences of `text`, stripped, in order; no character other than whitespace is lost."""
    segments: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        if _abbreviation(text, m):
            continue
        segments.append(text[start:m.end()])
        start = m.end()
    segments.append(text[start:])
    return [s.strip() for s in segments if s.strip()]
