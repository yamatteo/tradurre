"""Score the current import pipeline (extraction, exclusion, segmentation, alignment) against the gold book
(PLAN.md, "Gold chapter", design v2).

    uv run python scripts/gold_score.py

    uv run python scripts/gold_score.py --gold library/femur.gold.rebased.zip --source ... --target ...

Builds the book exactly as the import does, in a temporary database, and compares its exclusions and bead
boundaries with the gold's (a .json gold, or a corrected bundle .zip, which adds the ligature metric). Alignment is
reported strictly and coarsely (a split finer than the gold's is not an error); exclusion pooled and per side.
Text is compared without whitespace and hyphens. Output goes to the terminal only (the gold is copyrighted text).
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
from tradurre.services.gold import (
    SIDES, Layer, LigatureCounts, Score, layer_from_bundle, layer_from_json, read_layer, score, score_ligatures,
)

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def _build(source: Path, target: Path) -> tuple[Layer, float, float]:
    """The text layer of the pair, imported as `POST /api/v2/books` does, and the seconds
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
                build_book(conn, "gold", files[0], files[1])
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


def _ligature_line(name: str, c: LigatureCounts) -> str:
    return (f"ligatures, {name}: slips {c.slips} (closed {c.slips_closed}, open {c.slips_open}), "
            f"real {c.real} (kept {c.real_kept}, joined {c.real_joined}), skipped segments {c.skipped_segments}; "
            f"slip recall {c.slip_recall:.3f}  real keep rate {c.keep_rate:.3f}")


def _print_score(gold: Layer, predicted: Layer, result: Score) -> None:
    print("predicted bead shapes: " + ", ".join(f"{s}:{t} {n}" for (s, t), n in _shapes(predicted).most_common()))
    print(f"alignment: precision {result.alignment_precision:.3f}  recall {result.alignment_recall:.3f}  "
          f"F1 {result.alignment_f1:.3f}  (boundaries: {result.gold_boundaries} gold, "
          f"{result.predicted_boundaries} predicted)")
    print(f"alignment, coarse: precision {result.coarse_precision:.3f}  recall {result.alignment_recall:.3f}  "
          f"(boundaries predicted: {result.on_gold} on a gold boundary, {result.inside_gold} inside a gold bead, "
          f"{result.elsewhere} elsewhere)")
    if predicted.blocks is not None:
        print(f"alignment, turns: precision {result.turn_precision:.3f}  recall {result.turn_recall:.3f}  "
              f"F1 {result.turn_f1:.3f}  (boundaries predicted: {result.turn_boundaries}; "
              f"gold boundaries inside a speech paragraph: {result.gold_inside_speech})")
        gold_p, predicted_p = result.paragraph_boundaries
        print(f"alignment, paragraphs: precision {result.paragraph_precision:.3f}  "
              f"recall {result.paragraph_recall:.3f}  F1 {result.paragraph_f1:.3f}  "
              f"(boundaries: {gold_p} gold, {predicted_p} predicted)")
    print(f"exclusion: precision {result.exclusion_precision:.3f}  recall {result.exclusion_recall:.3f}  "
          f"F1 {result.exclusion_f1:.3f}")
    for side, (precision, recall) in result.exclusion_by_side.items():
        print(f"  exclusion, {side}: precision {precision:.3f}  recall {recall:.3f}")
    for side, (in_gold, in_predicted) in result.excluded_chars.items():
        print(f"  excluded characters, {side}: {in_gold} gold, {in_predicted} predicted")
    for first, last in result.missed[:5]:
        segments = [text for text, bead in gold.source if bead == first] or \
                   [text for text, bead in gold.target if bead == first]
        print(f"  missed beads {first}–{last}: {segments[0][:80]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the current import against the gold book.")
    parser.add_argument("--gold", type=Path, default=LIBRARY / "contrefeu.gold.json")
    parser.add_argument("--source", type=Path, default=LIBRARY / "contrefeu.fr.pdf")
    parser.add_argument("--target", type=Path, default=LIBRARY / "contrefeu.it.pdf")
    args = parser.parse_args(argv)
    for path in (args.gold, args.source, args.target):
        if not path.exists():
            print(f"not found: {path}", file=sys.stderr)
            return 1

    if args.gold.suffix.lower() == ".zip":
        gold = layer_from_bundle(args.gold.read_bytes())
    else:
        gold = layer_from_json(json.loads(args.gold.read_text(encoding="utf-8")))
    predicted, extract_s, build_s = _build(args.source, args.target)
    is_bundle = gold.corrected is not None
    try:
        ligatures = score_ligatures(gold, predicted) if is_bundle else None
        result = score(gold, predicted)
    except ValueError as e:
        print(e, file=sys.stderr)
        print("hint: if the extraction changed how blocks are cut, re-express the gold with "
              "scripts/gold_rebase.py", file=sys.stderr)
        return 1

    print(f"extraction {extract_s:.1f} s, build {build_s:.1f} s; "
          f"beads: {len(gold.reviewed)} gold, {len(predicted.reviewed)} predicted")
    if ligatures is not None:
        for name, counts in (*ligatures.sides.items(), ("total", ligatures.total)):
            print(_ligature_line(name, counts))
        print("note: strict precision is not meaningful against a bundle (the translator grouped sentences); "
              "read recall and coarse precision")
    _print_score(gold, predicted, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
