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
  - a gold block whose text starts with the next extracted block's and is longer is split there: the leading
    segments form one block, the remaining ones stay at the head of the gold and are matched against the
    following extracted blocks. Both parts keep the block's `kind`, `excluded` and `page`. The cut is normally on
    a segment boundary; a cut *inside* a segment is allowed when its `text` equals its `original_text` (the gold
    holds as one segment what the extraction cuts into several blocks); the segment is then cut right after the
    last non-white-space character before the cut, so the white space at the cut starts the second part and the
    two parts' texts concatenate to the original exactly. Both parts keep the segment's bead. A cut inside an
    edited segment fails. Every such cut is recorded and printed (side, block, page, bead or not). Counted as `split` (blocks) and `segment_split`.
    The rest of a split block may wait while the extraction puts other blocks (a footer, a note) in between, and
    continue later, like a deferred block;
  - a gold block that is included, has segments in beads, is made of digits only (at most 3 characters, white
    space ignored) and whose extracted block is excluded by the extraction is a page number the translator left
    in a bead: it is *neutralised*. The block becomes excluded and its segments leave their beads (their text is
    untouched, the beads keep their other segments). "Excluded by the extraction" is the pipeline's own notion
    (`build.py`: the block's kind is in `extract.EXCLUDED_KINDS`). A moved page number left in place would also
    break the order invariant. A merged block is never neutralised.

The checks: for the segments that are in beads, each bead's segments concatenate to the same `text` and
`original_text` as before and the beads come in the same order; the number of segments grows only through the
recorded cuts. The bead-less segments of excluded blocks: those not cut keep their order, and the pieces of the cut ones hold
exactly the characters of the segments they replace (the extraction may put other blocks between the pieces).

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
_SPACE = re.compile(r"[\s\-\u00ad]+")  # white space and hyphens: a line-end hyphen may or may not be kept
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


def _cut(text: str, n: int) -> tuple[str, str]:
    """`text` cut after its first `n` characters that `_strip` keeps (and no later): what follows them starts the
    second part."""
    seen = 0
    for i, c in enumerate(text):
        if not _SPACE.fullmatch(c):
            seen += 1
            if seen == n:
                return text[:i + 1], text[i + 1:]
    raise RebaseError("a cut beyond the end of a segment")


def _is_page_number(text: str) -> bool:
    return 0 < len(text) <= MAX_PAGE_NUMBER_CHARS and text.isascii() and text.isdigit()


def rebase_blocks(side: str, gold: list[dict], texts: list[str],
                  kinds: list[str] | None = None) -> tuple[list[dict], dict]:
    """The gold's blocks of one side re-expressed in the blocks of the extraction (`texts` and `kinds`, one per
    block; without `kinds` nothing is neutralised)."""
    blocks_in = len(gold)
    gold = list(gold)
    gs = [_gold_text(b) for b in gold]
    ns = [_strip(t) for t in texts]
    out: list[dict] = []
    deferred: list[int] = []
    leftovers: set[int] = set()  # gold blocks that are the rest of a split
    neutralised: list[tuple[str, str, int | None, bool]] = []
    merged = moved = split = segment_split = neutralised_blocks = neutralised_moved = 0
    cuts: list[tuple[str, int, int | None, bool]] = []  # in-segment cuts: side, extraction block, page, had a bead
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

    def cut(idx: int, want: str, j: int) -> dict:
        """Split the head of gold block `idx` off (its text is `want`) and return it as a block; the rest stays
        in `gold[idx]`. A cut inside a segment is allowed only in an unedited one; both parts keep its bead."""
        nonlocal segment_split
        head, acc, k = [], "", 0
        rest = gold[idx]["segments"]
        while acc != want:
            if k >= len(rest):
                raise fail(j, "a split would cut inside a segment")
            seg = rest[k]
            piece = _strip(seg["original_text"])
            if not want.startswith(acc):
                raise fail(j, "a split would cut inside a segment")
            if want.startswith(acc + piece):
                acc += piece
                head.append(seg)
                k += 1
                continue
            # the cut falls inside this segment
            if not piece.startswith(want[len(acc):]):
                raise fail(j, "a split would cut inside a segment")
            if seg["text"] != seg["original_text"]:
                raise fail(j, "a split would cut inside an edited segment")
            first, second = _cut(seg["original_text"], len(want) - len(acc))
            head.append({**seg, "text": first, "original_text": first})
            rest = rest[:k] + [{**seg, "text": second, "original_text": second}] + rest[k + 1:]
            acc = want
            segment_split += 1
            cuts.append((side, j, gold[idx].get("page"), seg["bead"] is not None))
        block = neutralise({**gold[idx], "segments": head}, j, False)
        gold[idx] = {**gold[idx], "segments": rest[k:]}
        gs[idx] = gs[idx][len(want):]
        leftovers.add(idx)
        return block

    for j, want in enumerate(ns):
        if not want:
            raise fail(j, "empty extracted block")
        if deferred and gs[deferred[0]] == want:
            moved += 1
            out.append(neutralise(gold[deferred.pop(0)], j, True))
            continue
        if deferred and deferred[0] in leftovers and gs[deferred[0]].startswith(want):
            # the leftover of an earlier split continues here, after blocks that the extraction put in between
            out.append(cut(deferred[0], want, j))
            split += 1
            continue
        # the leftover of an earlier split that the extraction continues further on waits in `deferred`
        while p in leftovers and gs[p] != want and not gs[p].startswith(want) and not want.startswith(gs[p]):
            deferred.append(p)
            p += 1
        if p >= len(gold):
            raise fail(j, "gold exhausted")
        if not gs[p]:
            raise fail(j, "empty gold block")
        if gs[p] == want:
            out.append(neutralise(gold[p], j, False))
            p += 1
            continue
        if gs[p].startswith(want):
            # the extraction cuts this gold block: the leading segments that make up `want` are one block, the
            # rest stays at the pointer (and may match, be split again or start a merge)
            out.append(cut(p, want, j))
            split += 1
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
    return out, {"merged": merged, "split": split, "segment_split": segment_split, "cuts": cuts, "blocks_in": blocks_in, "blocks_out": len(out), "moved": moved,
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


def _without(items: list, drop: Counter) -> list:
    """`items` without the first `drop[x]` occurrences of each `x`."""
    drop, out = Counter(drop), []
    for x in items:
        if drop[x] > 0:
            drop[x] -= 1
        else:
            out.append(x)
    return out


def _per_bead(flat: list[tuple[str, str, int | None, bool]]) -> list[tuple[int | None, str, str]]:
    """The beads in order of appearance, each with its segments' `text` and `original_text` concatenated."""
    out: list[list] = []
    for text, original, bead, _ in flat:
        if out and out[-1][0] == bead:
            out[-1][1] += text
            out[-1][2] += original
        else:
            out.append([bead, text, original])
    return [tuple(x) for x in out]


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

        def loose(t):  # bead-less segments of excluded blocks
            return t[2] is None and t[3]

        old_loose, new_loose, left = [t for t in old if loose(t)], [], Counter(became)
        for t in new:
            if loose(t):
                if left[t] > 0:
                    left[t] -= 1
                else:
                    new_loose.append(t)
        assert not +left, f"{side}: neutralised segments are missing"
        # a segment cut in pieces may have other blocks put between its pieces: the segments that were not cut
        # keep their order, and the pieces hold exactly the characters of the segments they replace
        removed, added = Counter(old_loose) - Counter(new_loose), Counter(new_loose) - Counter(old_loose)
        assert _without(old_loose, removed) == _without(new_loose, added), f"{side}: excluded bead-less order changed"
        for k in (0, 1):
            assert (Counter("".join(t[k] for t in removed.elements()))
                    == Counter("".join(t[k] for t in added.elements()))), f"{side}: excluded bead-less text changed"
        old_included = []
        for t in old:
            if gone[t] > 0:
                gone[t] -= 1
            elif not t[3]:
                old_included.append(t)
        new_included = [t for t in new if not t[3]]
        assert len(new_included) == len(old_included) + sum(c[3] for c in stats[side]["cuts"]), \
            f"{side}: segment count changed other than by recorded cuts"
        assert _per_bead(old_included) == _per_bead(new_included), f"{side}: included order, beads or text changed"
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
              f"block splits {s['split']}, segment splits {s['segment_split']}, moved {s['moved']}, neutralised {s['neutralised']} "
              f"(of moved blocks {s['neutralised_moved']}), segments {counts[f'{side} segments']}")
        for _, j, page, had_bead in s["cuts"]:
            print(f"  in-segment cut: {side}, extraction block {j}, page {page}, "
                  f"{'with' if had_bead else 'without'} a bead")
    total = sum(stats[side]["neutralised"] for side in SIDES)
    moved = sum(stats[side]["neutralised_moved"] for side in SIDES)
    print(f"neutralised {total} included page-number blocks (excluded, segments out of their beads): "
          f"{moved} moved, {total - moved} unmoved")
    print("checks passed: text equals the extraction, segments and included order kept (but for the "
          "neutralised ones), bundle restores clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
