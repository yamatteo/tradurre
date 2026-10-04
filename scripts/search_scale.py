"""Time search on a synthetic library at the scale of SPEC §1 (PLAN.md, "Search at library scale").

    uv run python scripts/search_scale.py

Builds 40 books × 2,500 beads of pseudo-words in a temporary database, then times `search_beads` on the queries
most likely to be slow (short word beginnings rank and highlight many matches). SPEC §5: under a second. Output
goes to the terminal only; nothing is stored.
"""

import argparse
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

from tradurre.db import get_connection, init_db
from tradurre.domain.history import transaction
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.search import search_beads

SYLLABLES = ["de", "la", "re", "mi", "to", "pa", "an", "ou", "in", "ch", "es", "ri", "ve", "so", "lu", "ne", "ta",
             "co", "pi", "ma", "ga", "bo", "fe", "su", "di", "on", "ar", "el", "ui", "te"]
LIMIT_MS = 1000


def _vocabulary(rng: random.Random, size: int) -> list[str]:
    words: set[str] = set()
    while len(words) < size:
        words.add("".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 4))))
    return sorted(words)


def _sentence(rng: random.Random, vocabulary: list[str]) -> str:
    words = [rng.choice(vocabulary) for _ in range(12)]
    return words[0].capitalize() + " " + " ".join(words[1:]) + "."


def _build(conn, books: int, beads: int, rng: random.Random, vocabulary: list[str]) -> list[str]:
    """`books` books of `beads` 1:1 beads, 10 sentences per paragraph; returns the first book's first sentence."""
    first = ""
    for b in range(books):
        project_id = f"book{b}"
        with transaction(conn):
            conn.execute(
                "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
                "VALUES (?, ?, 'fr', 'it', 'now', 'now')",
                (project_id, f"Book {b}"),
            )
            ids = {}
            for side in ("source", "target"):
                sentences = [_sentence(rng, vocabulary) for _ in range(beads)]
                if not first:
                    first = sentences[0]
                blocks = [NewBlock("paragraph", sentences[k:k + 10]) for k in range(0, beads, 10)]
                ids[side] = [s for block in create_document(conn, project_id, side, f"{side}.txt", "txt", blocks)
                             for s in block]
            append_beads(conn, project_id, [NewBead([s], [t], 0.9, "length")
                                            for s, t in zip(ids["source"], ids["target"])])
    return first


def _time(conn, runs: int, query: str, **kwargs) -> tuple[float, float, int]:
    """Median and max milliseconds over `runs` runs, and the number of results."""
    times = []
    hits = 0
    for _ in range(runs):
        start = time.perf_counter()
        hits = len(search_beads(conn, query, **kwargs))
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times), max(times), hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time search on a synthetic library.")
    parser.add_argument("--books", type=int, default=40)
    parser.add_argument("--beads", type=int, default=2500)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args(argv)

    rng = random.Random(0)
    vocabulary = _vocabulary(rng, 20_000)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scale.db"
        conn = get_connection(path)
        try:
            init_db(conn)
            start = time.perf_counter()
            first = _build(conn, args.books, args.beads, rng, vocabulary)
            build_s = time.perf_counter() - start
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            bead_count = conn.execute("SELECT COUNT(*) FROM beads").fetchone()[0]
            print(f"build {build_s:.1f} s; {args.books} books, {bead_count} beads; "
                  f"database {path.stat().st_size / 1e6:.1f} MB")

            word = first.split()[3]
            phrase = '"' + " ".join(first.split()[4:6]) + '"'
            queries = [
                ("one-letter prefix", "d", {}),
                ("two-letter prefix", "de", {}),
                ("full word", word, {}),
                ("two-word phrase", phrase, {}),
                ("one-letter prefix, source", "d", {"side": "source"}),
                ("one-letter prefix, offset 200", "d", {"offset": 200}),
                ("full word, one book", word, {"project_id": "book0"}),
            ]
            worst = 0.0
            for label, query, kwargs in queries:
                median, top, hits = _time(conn, args.runs, query, **kwargs)
                worst = max(worst, median)
                print(f"{label:32} {query!r:28} median {median:7.1f} ms  max {top:7.1f} ms  {hits} results")
        finally:
            conn.close()
    print(f"worst median {worst:.1f} ms: {'OK' if worst < LIMIT_MS else 'OVER'} (limit {LIMIT_MS} ms)")
    return 0 if worst < LIMIT_MS else 1


if __name__ == "__main__":
    sys.exit(main())
