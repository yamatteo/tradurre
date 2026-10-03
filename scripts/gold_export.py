"""Save the translator's corrected book as the gold (PLAN.md, "Gold chapter", design v2).

    uv run python scripts/gold_export.py <book id>

The book id is the one in the book's URL (`/book/<id>`). Every bead must be reviewed.
"""

import argparse
import json
import sys
from pathlib import Path

from tradurre import config
from tradurre.db import get_connection
from tradurre.services.gold import SIDES, layer_to_json, read_layer

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "library" / "contrefeu.gold.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save the translator's corrected book as the gold.")
    parser.add_argument("book_id", help="the book's id, as in its URL (/book/<id>)")
    parser.add_argument("--db", type=Path, default=None, help=f"the database (default: {config.DB_PATH})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"the file to write (default: {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    db = args.db or config.DB_PATH
    if not db.exists():
        print(f"database not found: {db}", file=sys.stderr)
        return 1
    conn = get_connection(db)
    try:
        layer = read_layer(conn, args.book_id)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        conn.close()

    unreviewed = layer.reviewed.count(False)
    if unreviewed:
        print(f"{unreviewed} of {len(layer.reviewed)} beads of the book are not reviewed; nothing written",
              file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(layer_to_json(layer), ensure_ascii=False), encoding="utf-8")
    sides = {side: {bead for _, bead in layer.side(side) if bead is not None} for side in SIDES}
    one_sided = sum(k not in sides["source"] or k not in sides["target"] for k in range(len(layer.reviewed)))
    excluded = {side: sum(bead is None for _, bead in layer.side(side)) for side in SIDES}
    print(f"{args.out}: {len(layer.reviewed)} beads, {one_sided} one-sided; "
          f"excluded segments: source {excluded['source']}, target {excluded['target']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
