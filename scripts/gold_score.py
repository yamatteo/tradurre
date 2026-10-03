"""Score the current import pipeline (extraction, exclusion, segmentation, alignment) against the gold book
(PLAN.md, "Gold chapter", design v2).

    uv run python scripts/gold_score.py

Builds the book exactly as the import does, in a temporary database, and compares its exclusions and bead
boundaries with the gold's. Output goes to the terminal only (the gold is copyrighted text).
"""

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tradurre.db import get_connection, init_db
from tradurre.domain.history import transaction
from tradurre.services.build import build_book
from tradurre.services.extract import extract
from tradurre.services.gold import SIDES, Layer, layer_from_json, read_layer, score

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def _build(source: Path, target: Path, aligner: str = "anchor") -> tuple[Layer, float, float]:
    """The text layer of the pair, imported as `POST /api/v2/books` does with the given aligner, and the seconds
    spent extracting and building (segmentation, alignment, database writes)."""
    start = time.perf_counter()
    files = []
    for path in (source, target):
        files.append((path.name, path.suffix.lower().lstrip("."), extract(path.name, path.read_bytes())))
    extracted = time.perf_counter()
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
                build_book(conn, "gold", files[0], files[1], aligner=aligner)
            built = time.perf_counter()
            return read_layer(conn, "gold"), extracted - start, built - extracted
        finally:
            conn.close()


def _shapes(layer: Layer) -> Counter:
    """How many beads have each (source segments, target segments) shape."""
    counts = [[0, 0] for _ in layer.reviewed]
    for k, side in enumerate(SIDES):
        for _, bead in layer.side(side):
            if bead is not None:
                counts[bead][k] += 1
    return Counter((s, t) for s, t in counts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the current import against the gold book.")
    parser.add_argument("--gold", type=Path, default=LIBRARY / "contrefeu.gold.json")
    parser.add_argument("--source", type=Path, default=LIBRARY / "contrefeu.fr.pdf")
    parser.add_argument("--target", type=Path, default=LIBRARY / "contrefeu.it.pdf")
    parser.add_argument("--aligner", choices=("anchor", "length"), default="anchor")
    args = parser.parse_args(argv)
    for path in (args.gold, args.source, args.target):
        if not path.exists():
            print(f"not found: {path}", file=sys.stderr)
            return 1

    gold = layer_from_json(json.loads(args.gold.read_text(encoding="utf-8")))
    predicted, extract_s, build_s = _build(args.source, args.target, args.aligner)
    try:
        result = score(gold, predicted)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"aligner: {args.aligner}; extraction {extract_s:.1f} s, build {build_s:.1f} s; "
          f"beads: {len(gold.reviewed)} gold, {len(predicted.reviewed)} predicted")
    print("predicted bead shapes: " + ", ".join(f"{s}:{t} {n}" for (s, t), n in _shapes(predicted).most_common()))
    print(f"alignment: precision {result.alignment_precision:.3f}  recall {result.alignment_recall:.3f}  "
          f"F1 {result.alignment_f1:.3f}  (boundaries: {result.gold_boundaries} gold, "
          f"{result.predicted_boundaries} predicted)")
    print(f"exclusion: precision {result.exclusion_precision:.3f}  recall {result.exclusion_recall:.3f}  "
          f"F1 {result.exclusion_f1:.3f}")
    for side, (in_gold, in_predicted) in result.excluded_chars.items():
        print(f"  excluded characters, {side}: {in_gold} gold, {in_predicted} predicted")
    for first, last in result.missed[:5]:
        segments = [text for text, bead in gold.source if bead == first] or \
                   [text for text, bead in gold.target if bead == first]
        print(f"  missed beads {first}–{last}: {segments[0][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
