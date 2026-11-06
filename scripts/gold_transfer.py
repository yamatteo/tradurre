"""Transfer a gold book's review marks (turn level) and text edits onto a freshly imported book.

    uv run python scripts/gold_transfer.py --book BOOK_ID --gold library/femur.gold.rebased.zip [--db PATH] [--apply]

A dry run unless `--apply`: then everything is written as one undoable operation. Refuses a gold whose text differs
from the book's, and `--apply` on a book that already has marks or edits. Prints counts and ids only, never text.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from tradurre import config
from tradurre.db import get_connection
from tradurre.domain.history import transaction
from tradurre.services.gold import SIDES, Layer, layer_from_bundle, layer_from_json
from tradurre.services.transfer import Plan, apply_transfer, has_work_done, plan_transfer


def load_gold(path: Path) -> Layer:
    if path.suffix.lower() == ".zip":
        return layer_from_bundle(path.read_bytes())
    if path.suffix.lower() == ".json":
        import json
        return layer_from_json(json.loads(path.read_text(encoding="utf-8")))
    raise ValueError(f"unknown gold file type {path.suffix!r} (.zip or .json)")


def print_plan(plan: Plan) -> None:
    print(f"turns marked: {plan.turns_marked} of {plan.turns_total}; beads marked: {len(plan.beads_to_mark)}")
    for side in SIDES:
        e = plan.edits[side]
        print(f"edits, {side}: applied {len(e.applied)}, already {e.already}, unplaced {len(e.unplaced)}, "
              f"spacing {e.spacing} (matched by the book {e.spacing_matched}, never applied)"
              + (f" (gold segments {e.unplaced})" if e.unplaced else ""))
    for side in SIDES:
        x = plan.exclusions[side]
        print(f"exclusions, {side}: excluded only in the gold {x.gold_only} chars, only in the book "
              f"{x.fresh_only} chars; book blocks {x.blocks}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transfer a gold book's marks and edits onto a fresh import.")
    parser.add_argument("--book", required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    db = args.db or config.DB_PATH
    try:
        gold = load_gold(args.gold)
        if args.apply:
            conn = get_connection(db)
        else:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        try:
            if args.apply and has_work_done(conn, args.book):
                raise ValueError("the book already has review marks or edits: a transfer is for fresh imports only")
            plan = plan_transfer(conn, args.book, gold)
            print_plan(plan)
            if not args.apply:
                print("dry run: nothing written (use --apply)")
                return 0
            with transaction(conn):
                operation = apply_transfer(conn, args.book, plan, gold)
            print(f"applied: operation {operation}")
            return 0
        finally:
            conn.close()
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
