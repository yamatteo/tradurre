"""Score the current import (extraction, segmentation, alignment) against the gold chapter (PLAN.md, "Gold
chapter").

    uv run python scripts/gold_score.py

Builds the book exactly as the import does, in a temporary database, and compares its bead boundaries with the
gold's. Output goes to the terminal only (the gold is copyrighted text).
"""

import argparse
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from tradurre.db import get_connection, init_db
from tradurre.domain.history import transaction
from tradurre.services.build import build_book
from tradurre.services.extract import extract
from tradurre.services.gold import book_beads, read_tsv, score

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def _build(source: Path, target: Path) -> list[tuple[str, str]]:
    """Every bead's (source cell, target cell) of the pair, imported as `POST /api/v2/books` does."""
    files = []
    for path in (source, target):
        files.append((path.name, path.suffix.lower().lstrip("."), extract(path.name, path.read_bytes())))
    with tempfile.TemporaryDirectory() as tmp:
        conn = get_connection(Path(tmp) / "gold.db")
        try:
            init_db(conn)
            now = datetime.now(timezone.utc).isoformat()
            with transaction(conn):
                conn.execute(
                    "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("gold", source.stem, "fr", "it", now, now),
                )
                build_book(conn, "gold", files[0], files[1])
            return [(s, t) for s, t, _ in book_beads(conn, "gold")]
        finally:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the current import against the gold chapter.")
    parser.add_argument("--gold", type=Path, default=LIBRARY / "contrefeu.gold.tsv")
    parser.add_argument("--source", type=Path, default=LIBRARY / "contrefeu.fr.pdf")
    parser.add_argument("--target", type=Path, default=LIBRARY / "contrefeu.it.pdf")
    args = parser.parse_args(argv)
    for path in (args.gold, args.source, args.target):
        if not path.exists():
            print(f"not found: {path}", file=sys.stderr)
            return 1

    gold = read_tsv(args.gold)
    start = time.perf_counter()
    predicted = _build(args.source, args.target)
    elapsed = time.perf_counter() - start
    try:
        result = score(gold, predicted)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"import: {elapsed:.1f} s, {len(predicted)} beads")
    print(f"precision {result.precision:.3f}  recall {result.recall:.3f}  F1 {result.f1:.3f}")
    print(f"boundaries: {result.gold_count} gold, {result.predicted_count} predicted")
    for first, last in result.missed[:5]:
        source, target = gold[first]
        print(f"  beads {first}–{last}: {f'{source} | {target}'[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
