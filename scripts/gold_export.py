"""Save a reviewed chapter of a book as the gold chapter (PLAN.md, "Gold chapter").

    uv run python scripts/gold_export.py <book id> <chapter>

The book id is the one in the book's URL (`/book/<id>`). Every bead of the chapter must be reviewed.
"""

import argparse
import sys
from pathlib import Path

from tradurre import config
from tradurre.db import get_connection
from tradurre.services.gold import chapter_beads, write_tsv

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "library" / "contrefeu.gold.tsv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save a reviewed chapter of a book as the gold chapter.")
    parser.add_argument("book_id", help="the book's id, as in its URL (/book/<id>)")
    parser.add_argument("chapter", type=int, help="the chapter number (1 = the first chapter of the body)")
    parser.add_argument("--db", type=Path, default=None, help=f"the database (default: {config.DB_PATH})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"the TSV to write (default: {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    db = args.db or config.DB_PATH
    if not db.exists():
        print(f"database not found: {db}", file=sys.stderr)
        return 1
    conn = get_connection(db)
    try:
        beads = chapter_beads(conn, args.book_id, args.chapter)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        conn.close()

    unreviewed = sum(not reviewed for _, _, reviewed in beads)
    if unreviewed:
        print(f"{unreviewed} of {len(beads)} beads of chapter {args.chapter} are not reviewed; nothing written",
              file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_tsv(args.out, [(source, target) for source, target, _ in beads])
    one_sided = sum(not source or not target for source, target, _ in beads)
    print(f"{args.out}: {len(beads)} beads, {one_sided} one-sided")
    return 0


if __name__ == "__main__":
    sys.exit(main())
