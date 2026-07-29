"""Recover characters that a PDF's own font mapping mangles.

Some PDF exporters (InDesign in particular) apply OpenType ligature /
contextual-alternate substitution to letters like "r" or "f" and then embed a
subset font whose ToUnicode CMap points those substituted glyphs at arbitrary
Private-Use-Area (PUA) codepoints instead of the real character -- because the
substituted glyph has no natural Unicode value of its own. PyMuPDF (and every
other extractor) faithfully returns that PUA codepoint: the character isn't
missing, it's mislabeled, and it renders as nothing since no installed font
has a glyph for an arbitrary PUA slot. This is a property of the PDF file
itself (visible directly in its /ToUnicode stream), not of any one document,
so detect it generically in any PDF and recover it via OCR when possible.

Requires the optional 'ocr' dependency group (pytesseract, pillow) to actually
recover characters -- without it, occurrences are still detected and reported
as warnings so the corruption is visible instead of silently vanishing.
"""

import logging

logger = logging.getLogger("tradurre.glyph_resolver")

# The three Unicode Private Use Areas.
_PUA_RANGES = ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD))

# How much to zoom the glyph crop before OCR -- these crops are typically a
# few pixels at page resolution, far too small for reliable recognition.
_OCR_ZOOM = 12
_OCR_PAD_RATIO = 0.4  # padding around the glyph bbox, as a fraction of its size

# A single occurrence's crop can be OCR-ambiguous (bad kerning with a
# neighboring glyph, a partially-clipped ascender/descender, antialiasing
# noise, ...). Since a PDF-wide substitution is applied from one glyph
# decision, sample several distinct occurrences and vote instead of betting
# the entire document on whichever occurrence happened to be seen first --
# this matters most for exactly the highest-frequency glyphs, where a wrong
# or missed call corrupts the largest fraction of the text.
_MAX_SAMPLES_PER_GLYPH = 16
_MIN_VOTES_TO_ACCEPT = 2

# How many already-known (non-PUA) characters on each side of the mystery
# glyph to include in its OCR crop. An isolated single-glyph crop throws away
# exactly the information that disambiguates it (e.g. a bare "r" is easily
# misread as "n"); OCR'ing it together with a couple of known neighbors and
# then locating the glyph via the known text gives the recognizer real
# context to work with, the same way a human reader would use it.
_CONTEXT_CHARS = 3


def _is_pua(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _PUA_RANGES)


def _iter_lines(doc):
    """Yield (page_index, [char_dict, ...]) for every text line in the doc.

    Concatenates all spans within a line (a span boundary is often just a
    font/style change mid-word, e.g. italics) so word-level context survives
    across them.
    """
    for page_index in range(len(doc)):
        page_dict = doc[page_index].get_text("rawdict")
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                chars = [ch for span in line.get("spans", []) for ch in span.get("chars", [])]
                if chars:
                    yield page_index, chars


def find_pua_occurrences(doc) -> dict[str, dict]:
    """Scan every page of an open fitz.Document for PUA-codepoint characters.

    Returns {char: {"count": int, "samples": [sample, ...]}} where each
    sample is {"page_index", "bbox" (of just the glyph, for the no-context
    fallback), "context_bbox" (covering a few neighboring known characters),
    "prefix", "suffix" (the known text on each side, within that bbox)}.
    Up to _MAX_SAMPLES_PER_GLYPH samples per distinct character, so recovery
    can vote across multiple occurrences/contexts rather than trusting one.
    """
    occurrences: dict[str, dict] = {}
    for page_index, chars in _iter_lines(doc):
        for i, ch in enumerate(chars):
            c = ch["c"]
            if not _is_pua(c):
                continue
            entry = occurrences.setdefault(c, {"count": 0, "samples": []})
            entry["count"] += 1
            if len(entry["samples"]) >= _MAX_SAMPLES_PER_GLYPH:
                continue

            lo = max(0, i - _CONTEXT_CHARS)
            hi = min(len(chars), i + _CONTEXT_CHARS + 1)
            window = chars[lo:hi]
            xs0 = min(w["bbox"][0] for w in window)
            ys0 = min(w["bbox"][1] for w in window)
            xs1 = max(w["bbox"][2] for w in window)
            ys1 = max(w["bbox"][3] for w in window)

            entry["samples"].append({
                "page_index": page_index,
                "bbox": ch["bbox"],
                "context_bbox": (xs0, ys0, xs1, ys1),
                "prefix": "".join(w["c"] for w in chars[lo:i]),
                "suffix": "".join(w["c"] for w in chars[i + 1:hi]),
            })
    return occurrences


def _render_crop(doc, page_index: int, bbox: tuple[float, float, float, float]):
    import fitz
    from PIL import Image
    import io as _io

    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    pad_x, pad_y = w * _OCR_PAD_RATIO, h * _OCR_PAD_RATIO
    rect = fitz.Rect(x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y)

    page = doc[page_index]
    pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(_OCR_ZOOM, _OCR_ZOOM))
    return Image.open(_io.BytesIO(pix.tobytes("png")))


def _ocr_isolated_glyph(doc, page_index: int, bbox: tuple[float, float, float, float]) -> str | None:
    """Fallback for when a glyph has no usable neighboring context (e.g. it's
    alone on its line): OCR just the glyph itself, as a single character."""
    import pytesseract

    image = _render_crop(doc, page_index, bbox)
    raw = pytesseract.image_to_string(
        image, config="--psm 10 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )
    guess = raw.strip()
    if not guess or not guess.isalpha() or len(guess) > 4:
        return None
    return guess


def _ocr_glyph_in_context(doc, sample: dict) -> str | None:
    """OCR the mystery glyph together with its known neighbors, then recover
    it by matching the known prefix/suffix text against the OCR output --
    whatever OCR produced in between is the recovered glyph."""
    import pytesseract

    prefix, suffix = sample["prefix"], sample["suffix"]
    if not prefix and not suffix:
        return _ocr_isolated_glyph(doc, sample["page_index"], sample["bbox"])

    image = _render_crop(doc, sample["page_index"], sample["context_bbox"])
    # psm 7 (strict single text line) frequently returns nothing at all on
    # these crops -- likely because rendering noise just below the baseline
    # reads as a second line, which psm 7's single-line assumption can't
    # accommodate. psm 6 (uniform block of text) tolerates that noise line
    # and reliably recovers the real text as its first line.
    raw = pytesseract.image_to_string(image, config="--psm 6").strip()
    if not raw:
        return None
    raw = raw.split("\n", 1)[0]

    start = 0
    if prefix:
        start = _match_end(raw, prefix)
        if start is None:
            return None
    end = len(raw)
    if suffix:
        found = _match_start(raw, suffix, start)
        if found is None:
            return None
        end = found

    guess = raw[start:end].strip()
    if not guess or not guess.isalpha() or len(guess) > 4:
        return None
    return guess


def _match_end(haystack: str, needle: str) -> int | None:
    """Best-effort: find where `needle` (known text) ends within `haystack`
    (OCR'd text that may contain minor recognition errors), returning the
    index right after the match. None if no usable match is found."""
    import difflib

    matcher = difflib.SequenceMatcher(None, haystack, needle, autojunk=False)
    block = matcher.find_longest_match(0, len(haystack), 0, len(needle))
    if block.size == 0:
        return None
    # The match may not reach the very end of `needle`; extrapolate by the
    # remaining unmatched needle length so `start` lands right after where
    # the mystery glyph should begin.
    remaining = len(needle) - (block.b + block.size)
    return min(len(haystack), block.a + block.size + remaining)


def _match_start(haystack: str, needle: str, search_from: int) -> int | None:
    import difflib

    haystack_tail = haystack[search_from:]
    matcher = difflib.SequenceMatcher(None, haystack_tail, needle, autojunk=False)
    block = matcher.find_longest_match(0, len(haystack_tail), 0, len(needle))
    if block.size == 0:
        return None
    start = block.a - block.b  # extrapolate backwards to the start of `needle`
    return search_from + max(0, start)


def _try_context(doc, sample: dict) -> str | None:
    try:
        return _ocr_glyph_in_context(doc, sample)
    except Exception:
        logger.exception("context OCR failed for a glyph sample")
        return None


def _try_isolated(doc, sample: dict) -> str | None:
    try:
        return _ocr_isolated_glyph(doc, sample["page_index"], sample["bbox"])
    except Exception:
        logger.exception("isolated OCR failed for a glyph sample")
        return None


def resolve_pua_glyphs(doc) -> tuple[dict[str, str], list[str]]:
    """Best-effort recovery of PUA-mapped glyphs via contextual OCR.

    Returns (substitution_map, warnings). `substitution_map` only contains
    characters OCR recovered with reasonable confidence (a plain 1-4 letter
    result agreed on by a majority of sampled occurrences); everything else
    is left for the caller to flag visibly rather than silently guess wrong.
    """
    occurrences = find_pua_occurrences(doc)
    if not occurrences:
        return {}, []

    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        warnings = [
            f"PDF contains {info['count']} occurrence(s) of unresolved glyph "
            f"U+{ord(c):04X} (likely a dropped ligature/contextual-alternate "
            "character baked into the PDF's own font mapping); install the "
            "'ocr' extra (pytesseract, pillow + the tesseract binary) to "
            "auto-recover it, or fix it manually."
            for c, info in sorted(occurrences.items())
        ]
        return {}, warnings

    mapping: dict[str, str] = {}
    warnings: list[str] = []
    for c, info in sorted(occurrences.items()):
        votes: dict[str, int] = {}
        for sample in info["samples"]:
            # Context OCR (glyph + known neighbors) resolves genuinely
            # ambiguous single letters (e.g. bare "r" misread as "n") that
            # isolated single-glyph OCR gets wrong; but for glyphs that are
            # themselves multi-character ligatures (fi/ff/ffi), the extra
            # neighboring text tends to confuse the line reader while the
            # isolated single-glyph crop nails it directly. Neither
            # dominates the other in general, so pool both as independent
            # votes and let majority voting sort it out.
            for guess in (_try_context(doc, sample), _try_isolated(doc, sample)):
                if guess:
                    votes[guess] = votes.get(guess, 0) + 1

        winner, winner_votes = max(votes.items(), key=lambda kv: kv[1], default=(None, 0))
        total_votes = sum(votes.values())
        # A raw vote count alone is not enough signal: with several samples
        # failing to OCR at all, a "winner" that only accounts for a small
        # minority of the successful attempts is often wrong -- confidently
        # substituting it would silently corrupt text instead of leaving a
        # visible, honest warning. Require an outright majority of the
        # successful OCR attempts, not just a plurality.
        if (
            winner
            and winner_votes >= _MIN_VOTES_TO_ACCEPT
            and winner_votes > total_votes / 2
        ):
            mapping[c] = winner
            logger.info(
                "resolved glyph U+%04X -> %r (%d/%d sample vote(s), %d occurrence(s) total, votes=%r)",
                ord(c), winner, winner_votes, len(info["samples"]), info["count"], votes,
            )
        else:
            warnings.append(
                f"could not confidently OCR glyph U+{ord(c):04X} "
                f"({info['count']} occurrence(s), votes={votes!r}); left unresolved"
            )

    return mapping, warnings


# Visible stand-in for any PUA character resolve_pua_glyphs couldn't recover,
# so a broken glyph shows up as an obvious flag instead of vanishing.
UNRESOLVED_MARKER = "�"  # U+FFFD REPLACEMENT CHARACTER


def apply_resolution(text: str, mapping: dict[str, str]) -> str:
    """Apply a PUA->text substitution map, then flag any remaining PUA chars."""
    for pua_char, real in mapping.items():
        text = text.replace(pua_char, real)
    return "".join(UNRESOLVED_MARKER if _is_pua(c) else c for c in text)
