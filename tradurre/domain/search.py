"""Search over the bead index (PLAN.md, "Search index").

The index tokenizer folds case and accents; ligatures are not diacritics, so the indexed text has them spelled
out (by the triggers in `tradurre/db.py`), and queries must be folded the same way with `fold`.
"""

_LIGATURES = (("œ", "oe"), ("Œ", "OE"), ("æ", "ae"), ("Æ", "AE"))


def fold(text: str) -> str:
    """Spell out ligatures, exactly as the index triggers do."""
    for ligature, spelled in _LIGATURES:
        text = text.replace(ligature, spelled)
    return text
