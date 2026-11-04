"""Correct bead assignments in a gold bundle, from a decisions file (a translator's pairing slips).

    uv run python scripts/gold_fix_beads.py [--gold library/femur.gold.zip] [--decisions library/femur.beads.tsv]
                                            [--out library/femur.gold.beads.zip]

The gold chain (all files under library/, none tracked):

  1. femur.bundle.zip         the translator's bundle, never edited;
  2. femur.gold.zip           `uv run python scripts/gold_fix_ligatures.py apply` (ligature fixes only, so that
                              `gold_fix_ligatures.py check` against the bundle stays valid);
  3. femur.gold.beads.zip     `uv run python scripts/gold_fix_beads.py` (this tool; reads 2, never writes it);
  4. femur.gold.rebased.zip   `uv run python scripts/gold_rebase.py --gold library/femur.gold.beads.zip`
                              (what `scripts/gold_score.py --gold library/femur.gold.rebased.zip` scores against).

The decisions file is a TSV with the columns `side`, `from_bead`, `to_bead`, `fingerprint`, `note`. A row moves the
one segment of `side` that is now in `from_bead` and whose `original_text` has that fingerprint (the first 12 hex
digits of its sha1) to `to_bead`. Rules:

  - `to_bead` is next to `from_bead` (they differ by 1);
  - exactly one segment of that side in `from_bead` matches, else the run fails; if none matches but exactly one
    matching segment is already in `to_bead`, the row was applied before and is skipped (counted);
  - a move may not leave a bead with no segments on both sides;
  - the bundle must restore with `check_project` clean afterwards.

Rows are applied in file order. Only the `bead` of the moved segments changes: texts, `reviewed` and the beads list
are untouched. The zip is written deterministically. Prints counts only (the gold is copyrighted text); keep the
decisions file out of version control and its `note` column short.
"""

import argparse
import csv
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

from tradurre.db import get_connection, init_db
from tradurre.domain.invariants import check_project
from tradurre.services.bundle import import_bundle

LIBRARY = Path(__file__).resolve().parent.parent / "library"
ENTRY = "bundle.json"
COLUMNS = ("side", "from_bead", "to_bead", "fingerprint", "note")


class FixError(ValueError):
    """A decision cannot be applied; the message holds indices only, never book text."""


def read_bundle(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        if z.namelist() != [ENTRY]:
            raise ValueError(f"{path}: unexpected entries {z.namelist()}")
        return json.loads(z.read(ENTRY))


def bundle_bytes(bundle: dict) -> bytes:
    """Deterministic zip: same serialisation as the app's export, fixed timestamp."""
    raw = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    info = zipfile.ZipInfo(ENTRY, date_time=(2026, 10, 11, 16, 43, 42))
    info.compress_type = zipfile.ZIP_DEFLATED
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(info, raw)
    return out.getvalue()


def fingerprint(original_text: str) -> str:
    return hashlib.sha1(original_text.encode("utf-8")).hexdigest()[:12]


def read_decisions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise FixError(f"{path}: columns must be {', '.join(COLUMNS)}")
        return [row for row in reader if any(row.values())]


def _segments(bundle: dict, side: str) -> list[dict]:
    return [s for d in bundle["documents"] if d["side"] == side for b in d["blocks"] for s in b["segments"]]


def apply_decisions(bundle: dict, rows: list[dict[str, str]]) -> tuple[dict, dict[str, int]]:
    """Apply the rows in order to `bundle`, in place; return it with the counts `applied` and `skipped`."""
    counts = {"applied": 0, "skipped": 0}
    for n, row in enumerate(rows, 1):
        side = row["side"]
        if side not in ("source", "target"):
            raise FixError(f"row {n}: unknown side")
        try:
            src, dst = int(row["from_bead"]), int(row["to_bead"])
        except ValueError:
            raise FixError(f"row {n}: bead indices must be integers") from None
        if abs(dst - src) != 1:
            raise FixError(f"row {n}: beads {src} and {dst} are not adjacent")
        if not 0 <= src < len(bundle["beads"]) or not 0 <= dst < len(bundle["beads"]):
            raise FixError(f"row {n}: bead out of range")
        segments = _segments(bundle, side)
        found = [s for s in segments if s["bead"] == src and fingerprint(s["original_text"]) == row["fingerprint"]]
        if len(found) > 1:
            raise FixError(f"row {n}: {len(found)} segments match in bead {src}")
        if not found:
            already = [s for s in segments
                       if s["bead"] == dst and fingerprint(s["original_text"]) == row["fingerprint"]]
            if len(already) == 1:
                counts["skipped"] += 1
                continue
            raise FixError(f"row {n}: no segment matches in bead {src}")
        if not any(s["bead"] == src for s in _segments(bundle, "source") + _segments(bundle, "target")
                   if s is not found[0]):
            raise FixError(f"row {n}: bead {src} would be left empty")
        found[0]["bead"] = dst
        counts["applied"] += 1
    return bundle, counts


def check_restores(bundle: dict) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        conn = get_connection(Path(tmp) / "check.db")
        try:
            init_db(conn)
            problems = check_project(conn, import_bundle(conn, bundle_bytes(bundle)))
        finally:
            conn.close()
    if problems:
        raise FixError(f"check_project: {len(problems)} problems after the fixes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply bead decisions to a gold bundle.")
    parser.add_argument("--gold", type=Path, default=LIBRARY / "femur.gold.zip")
    parser.add_argument("--decisions", type=Path, default=LIBRARY / "femur.beads.tsv")
    parser.add_argument("--out", type=Path, default=LIBRARY / "femur.gold.beads.zip")
    args = parser.parse_args(argv)
    for path in (args.gold, args.decisions):
        if not path.exists():
            print(f"not found: {path}", file=sys.stderr)
            return 1
    try:
        bundle, counts = apply_decisions(read_bundle(args.gold), read_decisions(args.decisions))
        check_restores(bundle)
    except FixError as e:
        print(f"bead fixes failed: {e}", file=sys.stderr)
        return 1
    args.out.write_bytes(bundle_bytes(bundle))
    print(f"decisions: {counts['applied']} applied, {counts['skipped']} already applied (skipped); "
          "bundle restores clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
