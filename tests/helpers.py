"""Shared test helpers."""

from tradurre.domain.search import fold

_SIDE_TEXTS = """
SELECT s.bead_id, d.side, s.text
FROM segments s
JOIN blocks b ON b.id = s.block_id
JOIN documents d ON d.id = b.document_id
WHERE s.bead_id IS NOT NULL
ORDER BY b.ord, s.ord
"""


def expected_index(conn):
    """The bead index rebuilt in Python: {(bead_id, folded source, folded target, project_id)}."""
    texts = {}
    for bead_id, side, text in conn.execute(_SIDE_TEXTS):
        texts.setdefault((bead_id, side), []).append(text)
    return {
        (bead_id, fold(" ".join(texts.get((bead_id, "source"), []))),
         fold(" ".join(texts.get((bead_id, "target"), []))), project_id)
        for bead_id, project_id in conn.execute("SELECT id, project_id FROM beads")
    }


def actual_index(conn):
    return {tuple(r) for r in conn.execute("SELECT rowid, source, target, project_id FROM bead_index")}
