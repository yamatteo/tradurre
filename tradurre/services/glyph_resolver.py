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


def _is_pua(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _PUA_RANGES)


def find_pua_occurrences(doc) -> dict[str, dict]:
    """Scan every page of an open fitz.Document for PUA-codepoint characters.

    Returns {char: {"count": int, "sample": (page_index, bbox)}}: one
    representative bbox per distinct character (the first one seen), enough
    to crop and OCR a single glyph without needing every occurrence.
    """
    occurrences: dict[str, dict] = {}
    for page_index in range(len(doc)):
        page = doc[page_index]
        page_dict = page.get_text("rawdict")
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    for ch in span.get("chars", []):
                        c = ch["c"]
                        if not _is_pua(c):
                            continue
                        entry = occurrences.setdefault(c, {"count": 0, "sample": None})
                        entry["count"] += 1
                        if entry["sample"] is None:
                            entry["sample"] = (page_index, ch["bbox"])
    return occurrences


def _ocr_glyph(doc, page_index: int, bbox: tuple[float, float, float, float]) -> str | None:
    import fitz
    from PIL import Image
    import io as _io
    import pytesseract

    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    pad_x, pad_y = w * _OCR_PAD_RATIO, h * _OCR_PAD_RATIO
    rect = fitz.Rect(x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y)

    page = doc[page_index]
    pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(_OCR_ZOOM, _OCR_ZOOM))
    image = Image.open(_io.BytesIO(pix.tobytes("png")))

    # psm 10: treat the crop as a single character/glyph.
    raw = pytesseract.image_to_string(
        image, config="--psm 10 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )
    guess = raw.strip()
    if not guess or not guess.isalpha() or len(guess) > 4:
        return None
    return guess


def resolve_pua_glyphs(doc) -> tuple[dict[str, str], list[str]]:
    """Best-effort recovery of PUA-mapped glyphs via isolated-glyph OCR.

    Returns (substitution_map, warnings). `substitution_map` only contains
    characters OCR recovered with reasonable confidence (a plain 1-4 letter
    result); everything else is left for the caller to flag visibly rather
    than silently guess wrong.
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
        page_index, bbox = info["sample"]
        try:
            guess = _ocr_glyph(doc, page_index, bbox)
        except Exception:
            logger.exception("OCR failed while resolving glyph U+%04X", ord(c))
            guess = None

        if guess:
            mapping[c] = guess
            logger.info(
                "resolved glyph U+%04X -> %r (%d occurrence(s))",
                ord(c), guess, info["count"],
            )
        else:
            warnings.append(
                f"could not confidently OCR glyph U+{ord(c):04X} "
                f"({info['count']} occurrence(s)); left unresolved"
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
