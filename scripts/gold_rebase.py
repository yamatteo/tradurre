"""Re-express a gold bundle in the block structure of the current extraction (a "rebase").

    uv run python scripts/gold_rebase.py --gold library/femur.gold.zip --source library/femur.fr.pdf \
        --target library/femur.it.pdf --out library/femur.gold.rebased.zip

When the extraction changes how a document is cut into blocks (a paragraph split by a page break is now one block,
and the page number or footnote that sat inside it comes after it), the gold's text no longer matches the
extraction *in segment order* (`gold.py`, `_check_same_text`), although the characters are the same. The rebase
walks the extraction's blocks and re-orders / merges the gold's blocks to follow them:

  - a gold block with the same text (without whitespace) as the next extracted block is emitted as it is;
  - an extracted block made of several consecutive gold blocks (interleaved with other blocks that the extraction
    puts elsewhere) is emitted as one merged block: `kind`, `excluded` and `page` of its first part, the parts'
    segments in order, each segment untouched. The interleaved blocks are deferred and emitted where the
    extraction has them;
  - a gold block that is included, has segments in beads, is made of digits only (at most 3 characters, white
    space ignored) and whose extracted block is excluded by the extraction is a page number the translator left
    in a bead: it is *neutralised*. The block becomes excluded and its segments leave their beads (their text is
    untouched, the beads keep their other segments). "Excluded by the extraction" is the pipeline's own notion
    (`build.py`: the block's kind is in `extract.EXCLUDED_KINDS`). A moved page number left in place would also
    break the order invariant. A merged block is never neutralised.

Deterministic and idempotent; the input gold is never modified. Prints counts only (the gold is copyrighted text).
"""

import argparse
import copy
import io
import json
import re
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from tradurre.db import get_connection, init_db
from tradurre.domain.invariants import check_project
from tradurre.services.bundle import import_bundle
from tradurre.services.extract import EXCLUDED_KINDS, extract

LIBRARY = Path(__file__).resolve().parent.parent / "library"
ENTRY = "bundle.json"
SIDES = ("source", "target")
_SPACE = re.compile(r"\s+")
MAX_PAGE_NUMBER_CHARS = 3


class RebaseError(ValueError):
    """The gold cannot be reconciled with the extraction; the message holds counts only."""


# --- Reading and writing the bundle (same behaviour as gold_fix_ligatures.py) ---


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


def write_bundle(path: Path, bundle: dict) -> None:
    path.write_bytes(bundle_bytes(bundle))


# --- The rebase ---


def _strip(text: str) -> str:
    return _SPACE.sub("", text)


def _gold_text(block: dict) -> str:
    return _strip("".join(s["original_text"] for s in block["segments"]))


def _is_page_number(text: str) -> bool:
    return 0 < len(text) <= MAX_PAGE_NUMBER_CHARS and text.isascii() and text.isdigit()


def rebase_blocks(side: str, gold: list[dict], texts: list[str],
                  kinds: list[str] | None = None) -> tuple[list[dict], dict]:
    """The gold's blocks of one side re-expressed in the blocks of the extraction (`texts` and `kinds`, one per
    block; without `kinds` nothing is neutralised)."""
    gs = [_gold_text(b) for b in gold]
    ns = [_strip(t) for t in texts]
    out: list[dict] = []
    deferred: list[int] = []
    neutralised: list[tuple[str, str, int | None, bool]] = []
    merged = moved = neutralised_blocks = neutralised_moved = 0
    p = 0

    def fail(j: int, why: str) -> RebaseError:
        return RebaseError(f"{side}: block {j} of the extraction cannot be matched ({why}; gold block {p} of "
                           f"{len(gold)}, lengths gold {len(gs[p]) if p < len(gs) else 0} / extracted {len(ns[j])})")

    def neutralise(block: dict, j: int, was_moved: bool) -> dict:
        nonlocal neutralised_blocks, neutralised_moved
        if (kinds is None or kinds[j] not in EXCLUDED_KINDS or block["excluded"] or not _is_page_number(ns[j])
                or not any(s["bead"] is not None for s in block["segments"])):
            return block
        neutralised.extend((s["text"], s["original_text"], s["bead"], False) for s in block["segments"])
        neutralised_blocks += 1
        neutralised_moved += was_moved
        return {**block, "excluded": True, "segments": [{**s, "bead": None} for s in block["segments"]]}

    for j, want in enumerate(ns):
        if not want:
            raise fail(j, "empty extracted block")
        if deferred and gs[deferred[0]] == want:
            moved += 1
            out.append(neutralise(gold[deferred.pop(0)], j, True))
            continue
        if p >= len(gold):
            raise fail(j, "gold exhausted")
        if not gs[p]:
            raise fail(j, "empty gold block")
        if gs[p] == want:
            out.append(neutralise(gold[p], j, False))
            p += 1
            continue
        if not want.startswith(gs[p]):
            raise fail(j, "text differs")
        parts = [gold[p]]
        acc = gs[p]
        first = p
        p += 1
        while acc != want:
            if p >= len(gold):
                raise fail(j, "gold exhausted inside a merge")
            if not gs[p]:
                raise fail(j, "empty gold block inside a merge")
            if want.startswith(acc + gs[p]):
                parts.append(gold[p])
                acc += gs[p]
            else:
                deferred.append(p)
            p += 1
        if len({bool(b["excluded"]) for b in parts}) != 1:
            p = first
            raise fail(j, "parts of a merge differ in `excluded`")
        head = parts[0]
        out.append({**head, "segments": [s for b in parts for s in b["segments"]]})
        merged += 1
    if deferred or p != len(gold):
        raise RebaseError(f"{side}: {len(deferred)} deferred and {len(gold) - p} unread gold blocks left over "
                          f"after {len(ns)} extracted blocks")
    return out, {"merged": merged, "blocks_in": len(gold), "blocks_out": len(out), "moved": moved,
                      "neutralised": neutralised_blocks, "neutralised_moved": neutralised_moved, "neutralised_segments": neutralised}


def rebase(bundle: dict, texts: dict[str, list[str]],
           kinds: dict[str, list[str]] | None = None) -> tuple[dict, dict[str, dict]]:
    """A copy of `bundle` whose documents follow the extraction's blocks (`texts[side]`, `kinds[side]`)."""
    result = copy.deepcopy(bundle)
    stats = {}
    for document in result["documents"]:
        side = document["side"]
        document["blocks"], stats[side] = rebase_blocks(side, document["blocks"], texts[side],
                                                          kinds[side] if kinds else None)
    freed = {t[2] for side in stats for t in stats[side]["neutralised_segments"] if t[2] is not None}
    kept = {s["bead"] for d in result["documents"] for b in d["blocks"] for s in b["segments"]}
    if freed - kept:
        raise RebaseError(f"{len(freed - kept)} beads would be left without segments by neutralising")
    return result, stats


# --- Checks ---


def _flat(bundle: dict, side: str) -> list[tuple[str, str, int | None, bool]]:
    return [
        (s["text"], s["original_text"], s["bead"], bool(b["excluded"]))
        for d in bundle["documents"] if d["side"] == side
        for b in d["blocks"] for s in b["segments"]
    ]


def check(before: dict, after: dict, texts: dict[str, list[str]], stats: dict[str, dict]) -> dict[str, int]:
    """Raise AssertionError if the guarantees do not hold; return counts."""
    counts = {}
    for side in SIDES:
        extracted = _strip("".join(texts[side]))
        rebased = _strip("".join(s["original_text"] for d in after["documents"] if d["side"] == side
                                 for b in d["blocks"] for s in b["segments"]))
        assert extracted == rebased, f"{side}: text differs from the extraction"
        old, new = _flat(before, side), _flat(after, side)
        gone = Counter(stats[side]["neutralised_segments"])
        became = Counter((t, o, None, True) for t, o, _, _ in stats[side]["neutralised_segments"])
        assert not gone - Counter(old), f"{side}: neutralised segments are not in the input"
        assert Counter(old) - gone + became == Counter(new), f"{side}: segments changed"
        old_included = []
        for t in old:
            if gone[t] > 0:
                gone[t] -= 1
            elif not t[3]:
                old_included.append(t)
        assert old_included == [t for t in new if not t[3]], f"{side}: included order or beads changed"
        counts[f"{side} segments"] = len(new)
    for key in ("format", "version", "app_version", "exported_at", "book", "beads", "runs"):
        assert before.get(key) == after.get(key), f"{key} changed"
    with tempfile.TemporaryDirectory() as tmp:
        conn = get_connection(Path(tmp) / "check.db")
        try:
            init_db(conn)
            book_id = import_bundle(conn, bundle_bytes(after))
            problems = check_project(conn, book_id)
            assert problems == [], f"check_project: {len(problems)} problems"
        finally:
            conn.close()
    return counts


def extraction_blocks(source: Path, target: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    blocks = {side: extract(path.name, path.read_bytes()).blocks
              for side, path in (("source", source), ("target", target))}
    return ({side: [b.text for b in bs] for side, bs in blocks.items()},
            {side: [b.kind for b in bs] for side, bs in blocks.items()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-express a gold bundle in the current extraction's blocks.")
    parser.add_argument("--gold", type=Path, default=LIBRARY / "femur.gold.zip")
    parser.add_argument("--source", type=Path, default=LIBRARY / "femur.fr.pdf")
    parser.add_argument("--target", type=Path, default=LIBRARY / "femur.it.pdf")
    parser.add_argument("--out", type=Path, default=LIBRARY / "femur.gold.rebased.zip")
    args = parser.parse_args(argv)
    for path in (args.gold, args.source, args.target):
        if not path.exists():
            print(f"not found: {path}", file=sys.stderr)
            return 1
    before = read_bundle(args.gold)
    texts, kinds = extraction_blocks(args.source, args.target)
    try:
        after, stats = rebase(before, texts, kinds)
        counts = check(before, after, texts, stats)
    except (RebaseError, AssertionError) as e:
        print(f"rebase failed: {e}", file=sys.stderr)
        return 1
    write_bundle(args.out, after)
    for side in SIDES:
        s = stats[side]
        print(f"{side}: blocks {s['blocks_in']} -> {s['blocks_out']}, merged {s['merged']}, "
              f"moved {s['moved']}, neutralised {s['neutralised']} "
              f"(of moved blocks {s['neutralised_moved']}), segments {counts[f'{side} segments']}")
    total = sum(stats[side]["neutralised"] for side in SIDES)
    moved = sum(stats[side]["neutralised_moved"] for side in SIDES)
    print(f"neutralised {total} included page-number blocks (excluded, segments out of their beads): "
          f"{moved} moved, {total - moved} unmoved")
    print("checks passed: text equals the extraction, segments and included order kept (but for the "
          "neutralised ones), bundle restores clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
