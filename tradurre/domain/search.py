"""Search over the bead index (PLAN.md, "Search index").

The index tokenizer folds case and accents; ligatures are not diacritics, so the indexed text has them spelled
out (by the triggers in `tradurre/db.py`), and queries must be folded the same way with `fold`.
"""

import re
import sqlite3

_LIGATURES = (("œ", "oe"), ("Œ", "OE"), ("æ", "ae"), ("Æ", "AE"))


def fold(text: str) -> str:
    """Spell out ligatures, exactly as the index triggers do."""
    for ligature, spelled in _LIGATURES:
        text = text.replace(ligature, spelled)
    return text


_TERMS = re.compile(r'"([^"]*)"|(\S+)')
_COLUMNS = {"source": "source", "target": "target", "both": "{source target}"}
START, END = "\x02", "\x03"


def fts_query(text: str, side: str = "both") -> str | None:
    """Turn what the translator typed into an FTS5 expression; None if there is nothing to search for.

    Quoted stretches are phrases, other words are terms, all of them required. Every term is quoted, so FTS
    operators typed by the translator (OR, NEAR, *, -) are searched as words and never parsed as syntax.
    """
    if side not in _COLUMNS:
        raise ValueError(f"side must be 'source', 'target' or 'both', not {side!r}")
    terms = []
    for phrase, word in _TERMS.findall(text):
        term = fold(phrase or word)
        if any(ch.isalnum() for ch in term):  # a term without letters or digits has no tokens to match
            terms.append('"' + term.replace('"', '""') + '"')
    if not terms:
        return None
    return f"{_COLUMNS[side]} : ({' '.join(terms)})"


def _unfold_highlight(display: str, highlighted: str) -> str:
    """Move the highlight markers of `highlighted` (= `fold(display)` plus markers) onto `display`."""
    out: list[str] = []
    pos = 0
    for ch in display:
        before: list[str] = []
        while pos < len(highlighted) and highlighted[pos] in (START, END):
            before.append(highlighted[pos])
            pos += 1
        inside: list[str] = []
        for i in range(len(fold(ch))):
            if i:
                while pos < len(highlighted) and highlighted[pos] in (START, END):
                    inside.append(highlighted[pos])
                    pos += 1
            pos += 1
        out += before
        out += [m for m in inside if m == START]
        out.append(ch)
        out += [m for m in inside if m == END]
    out += highlighted[pos:]  # markers after the last character
    return "".join(out)


_BEAD_TEXT = """
SELECT d.side, s.text
FROM segments s
JOIN blocks b ON b.id = s.block_id
JOIN documents d ON d.id = b.document_id
WHERE s.bead_id = ?
ORDER BY b.ord, s.ord
"""


def _bead_text(conn: sqlite3.Connection, bead_id: int) -> dict[str, str]:
    """A bead's text per side, joined as the index joins it."""
    parts: dict[str, list[str]] = {"source": [], "target": []}
    for side, text in conn.execute(_BEAD_TEXT, (bead_id,)):
        parts[side].append(text)
    return {side: " ".join(texts) for side, texts in parts.items()}


def search_beads(
    conn: sqlite3.Connection, text: str, side: str = "both", project_id: str | None = None, limit: int = 50
) -> list[dict]:
    """Beads matching the query, best first, with the matches marked by START/END in their real text."""
    query = fts_query(text, side)
    if query is None:
        return []
    sql = (
        f"SELECT rowid, project_id, highlight(bead_index, 0, '{START}', '{END}'), "
        f"highlight(bead_index, 1, '{START}', '{END}') FROM bead_index WHERE bead_index MATCH ?"
    )
    params: list = [query]
    if project_id is not None:
        sql += " AND project_id = ?"
        params.append(project_id)
    sql += " ORDER BY bm25(bead_index) LIMIT ?"
    params.append(limit)

    results = []
    for bead_id, bead_project, source_hl, target_hl in conn.execute(sql, params).fetchall():
        title, ord_, reviewed = conn.execute(
            "SELECT p.title, b.ord, b.reviewed FROM beads b JOIN projects p ON p.id = b.project_id WHERE b.id = ?",
            (bead_id,),
        ).fetchone()
        position = conn.execute(
            "SELECT COUNT(*) FROM beads WHERE project_id = ? AND ord <= ?", (bead_project, ord_)
        ).fetchone()[0]
        texts = _bead_text(conn, bead_id)
        results.append({
            "bead_id": bead_id,
            "project_id": bead_project,
            "title": title,
            "position": position,
            "source": _unfold_highlight(texts["source"], source_hl),
            "target": _unfold_highlight(texts["target"], target_hl),
            "reviewed": bool(reviewed),
        })
    return results
