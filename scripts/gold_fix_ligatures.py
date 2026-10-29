"""Correct the ligature gaps of a reviewed bundle, with independent evidence, into a separate gold copy.

    uv run python scripts/gold_fix_ligatures.py scan     # candidates + PDF evidence + dropped-ligature survey
    uv run python scripts/gold_fix_ligatures.py apply    # decisions file -> corrected copy of the bundle
    uv run python scripts/gold_fix_ligatures.py check    # the corrected copy against the original

A PDF's `f`/`fi`/`fl`/`ff`/`ffi`/`ffl` ligature glyph (and the capital `Th` ligature) is sometimes extracted as
its letters plus a stray space ("fi lms"). A *candidate* is any whitespace gap right after `f`, `fi`, `fl` (any
case) or a capital `Th` (case-sensitive: words ending in a lowercase "th" are not candidates) and before a letter. The PDF itself
tells a stray space from a real word space: the stray one is a space character whose box starts *inside* the
previous glyph (it overlaps it), a real one starts where the previous glyph ends (see `evidence`).

Files, all in `library/` (local, copyrighted, gitignored; nothing derived from the book is committed):

  femur.bundle.zip              the translator's bundle (never written)
  femur.ligatures.candidates.tsv   scan: side, block, segment, offset, page, context, evidence
  femur.ligatures.dropped.tsv      scan: survey of dropped ligatures (not corrected)
  femur.ligatures.tsv              the decisions: side, block, segment, offset, decision, class, note
  femur.ligatures.doubtful.tsv     apply: the doubtful decisions, with context, for the user
  femur.gold.zip                   apply: the corrected copy (only some segments' `text` differ, by whitespace)

Block and segment indexes are list positions in the bundle; the offset is the position of the gap's first
whitespace character in the segment's `text`. Rows of class `translator` are gaps the translator already
closed herself (found by comparing `original_text` with `text`): the offset is where her text is joined.
"""

import argparse
import csv
import json
import re
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from tradurre.services.gold import LIGATURE_GAP

LIBRARY = Path(__file__).resolve().parent.parent / "library"
BUNDLE = LIBRARY / "femur.bundle.zip"
GOLD = LIBRARY / "femur.gold.zip"
SOURCE_PDF = LIBRARY / "femur.fr.pdf"
TARGET_PDF = LIBRARY / "femur.it.pdf"
CANDIDATES = LIBRARY / "femur.ligatures.candidates.tsv"
DROPPED = LIBRARY / "femur.ligatures.dropped.tsv"
DECISIONS = LIBRARY / "femur.ligatures.tsv"
DOUBTFUL = LIBRARY / "femur.ligatures.doubtful.tsv"

ENTRY = "bundle.json"
DECISION_VALUES = ("join", "keep", "doubtful")
CLASS_VALUES = ("translator", "pdf", "context")

# A gap: whitespace right after f / fi / fl (so after any of f, fi, fl, ff, ffi, ffl; any case) or after a capital
# Th (case-sensitive), and before a letter.
GAP = LIGATURE_GAP
LETTER = re.compile(r"[^\W\d_]")
LIGATURE_CHARS = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}

# PDF evidence: a space character whose box starts more than this many points before the *origin* of the glyph it
# follows lies inside a ligature glyph (a stray space); a real word space starts at or after that origin.
# Calibrated on the translator's own fixes (see the report).
STRAY_BELOW = -1.0


# --- Reading and writing the bundle ---


def read_bundle(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        if z.namelist() != [ENTRY]:
            raise ValueError(f"{path}: unexpected entries {z.namelist()}")
        return json.loads(z.read(ENTRY))


def write_bundle(path: Path, bundle: dict) -> None:
    """Deterministic: same serialisation as the app's export, fixed timestamp."""
    raw = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    info = zipfile.ZipInfo(ENTRY, date_time=(2026, 10, 11, 16, 43, 42))
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(info, raw)


def segments(bundle: dict):
    """(side, block index, segment index, block, segment) in list order."""
    for document in bundle["documents"]:
        for bi, block in enumerate(document["blocks"]):
            for si, seg in enumerate(block["segments"]):
                yield document["side"], bi, si, block, seg


# --- Candidates ---


@dataclass(frozen=True)
class Candidate:
    side: str
    block: int
    segment: int
    offset: int
    kind: str  # "open" (a gap in `text`) or "translator" (a gap she closed; offset where her text is joined)
    page: int | None
    text: str  # the segment text the offset refers to
    context_from: str  # the text the context/PDF key is taken from (original_text for a translator fix)
    context_offset: int  # the gap's position in context_from

    @property
    def key(self) -> tuple[str, int, int, int]:
        return (self.side, self.block, self.segment, self.offset)

    @property
    def context(self) -> str:
        t, o = self.context_from, self.context_offset
        return t[max(0, o - 20) : o] + "_" + t[o + 1 : o + 21]


def translator_gaps(original: str, text: str) -> list[tuple[int, int]]:
    """Whitespace runs the translator removed after f/fi/fl/Th before a letter: (offset in `text`, offset in
    `original`). Other edits (hyphens, ...) are not ligature fixes and are ignored."""
    import difflib

    out = []
    for tag, i1, i2, j1, _ in difflib.SequenceMatcher(None, original, text, autojunk=False).get_opcodes():
        if tag != "delete" or not original[i1:i2].isspace():
            continue
        # i1 is the gap in `original`; check the neighbours there.
        if re.search(r"(?:(?i:f[il]?)|Th)$", original[:i1]) and LETTER.match(original[i2 : i2 + 1] or "0"):
            out.append((j1, i1))
    return out


def find_candidates(bundle: dict) -> list[Candidate]:
    out = []
    for side, bi, si, block, seg in segments(bundle):
        text = seg["text"]
        for m in GAP.finditer(text):
            out.append(Candidate(side, bi, si, m.start(1), "open", block.get("page"), text, text, m.start(1)))
        if text != seg["original_text"]:
            for offset, original_offset in translator_gaps(seg["original_text"], text):
                out.append(Candidate(side, bi, si, offset, "translator", block.get("page"), text,
                                     seg["original_text"], original_offset))
    out.sort(key=lambda c: (c.side != "source", c.block, c.segment, c.offset, c.kind))
    return out


# --- PDF evidence ---


def classify_run(run: tuple[float, ...]) -> str:
    """A run of space characters between two letters of the PDF, each given as how far it starts before the
    origin of the glyph it follows. Only stray spaces: "stray" (join). Only real ones: "real". Both: "ligature+real",
    a word that ends in a ligature glyph, then its real space (keep)."""
    stray = sum(d < STRAY_BELOW for d in run)
    return "stray" if stray == len(run) else "real" if stray == 0 else "ligature+real"


class PdfPages:
    """Per physical page: the text of its lines (ligature characters expanded, whitespace runs collapsed) and, for
    every gap in it, what kind of gap it is, from the glyph boxes (`rawdict`)."""

    def __init__(self, path: Path):
        import pymupdf

        self.doc = pymupdf.open(path)
        self.two_up = self.doc[0].rect.width > self.doc[0].rect.height
        self._cache: dict[int, tuple[str, dict[int, tuple[str, tuple[float, ...]]]]] = {}

    def physical(self, logical_page: int) -> int:
        """0-based physical page of a 1-based logical page (a two-up spread is two logical pages)."""
        return (logical_page - 1) // 2 if self.two_up else logical_page - 1

    def page(self, index: int) -> tuple[str, dict[int, tuple[str, tuple[float, ...]]]]:
        if index not in self._cache:
            self._cache[index] = self._build(index)
        return self._cache[index]

    def _build(self, index: int) -> tuple[str, dict[int, tuple[str, tuple[float, ...]]]]:
        text: list[str] = []
        gaps: dict[int, tuple[str, tuple[float, ...]]] = {}
        for block in self.doc[index].get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                chars = [c for span in line["spans"] for c in span["chars"]]
                if not any(c["c"].strip() for c in chars):
                    continue
                if text:
                    text.append("\n")
                    gaps[len(text) - 1] = ("linebreak", ())
                last_origin = None  # x of the last non-space glyph's origin
                run: list[float] = []  # for each space since it, how far it starts before that origin
                for c in chars:
                    ch = c["c"]
                    if ch.isspace():
                        if last_origin is not None:
                            run.append(c["bbox"][0] - last_origin)
                        continue
                    if run:
                        gaps[len(text)] = ("space", tuple(run))
                        text.append(" ")
                        run = []
                    text.append(LIGATURE_CHARS.get(ch, ch))
                    last_origin = c["origin"][0]
                # a trailing run at a line end is dropped (the next line adds its own break)
        return "".join(text), gaps

    @staticmethod
    def _loose(key: str) -> str:
        """The key as a pattern: a space may be a line break in the PDF, a hyphen may end a line."""
        return "".join("[ \n]" if ch == " " else "-\n?" if ch == "-" else re.escape(ch) for ch in key)

    def evidence(self, logical_page: int | None, left: str, right: str) -> tuple[str, float | None]:
        """("stray" | "real" | "ligature+real" | "linebreak" | "nomatch" | "multiple", smallest start relative to the glyph origin)."""
        if logical_page is None:
            return "nomatch", None
        base = self.physical(logical_page)
        for width in (12, 6, 3):
            lk, rk = left[-width:], right[:width]
            pattern = re.compile(self._loose(lk) + r"([ \n])" + self._loose(rk))
            verdicts = set()
            found: list[float | None] = []
            for index in range(max(0, base - 1), min(len(self.doc), base + 2)):
                text, gaps = self.page(index)
                for m in pattern.finditer(text):
                    pos = m.start(1)
                    kind, run = gaps.get(pos, ("space", (0.0,)))
                    verdicts.add(kind if kind == "linebreak" else classify_run(run))
                    d = min(run) if run else 0.0
                    found.append(d)
            if len(verdicts) == 1:
                return verdicts.pop(), (found[0] if found[0] else 0.0)
            if len(verdicts) > 1:
                return "multiple", None
        return "nomatch", None

    def stray_keys(self) -> list[tuple[int, str, str]]:
        """Every stray space of the document: (page, left 8 chars, right 8 chars)."""
        out = []
        for index in range(len(self.doc)):
            text, gaps = self.page(index)
            for pos, (kind, d) in gaps.items():
                if kind == "space" and classify_run(d) == "stray":
                    out.append((index, text[max(0, pos - 8) : pos].replace("\n", " "), text[pos + 1 : pos + 9].replace("\n", " ")))
        return out


def candidate_evidence(c: Candidate, pdfs: dict[str, PdfPages]) -> str:
    text, o = c.context_from, c.context_offset
    kind, d = pdfs[c.side].evidence(c.page, text[:o], text[o + 1 :])
    shown = "" if d is None else f" d={d:.1f}"
    prefix = "translator-fixed; " if c.kind == "translator" else ""
    return f"{prefix}pdf={kind}{shown}"


# --- Dropped ligatures (survey only) ---


def dropped_survey(bundle: dict) -> list[tuple[str, int, int, int, int | None, str, str, str]]:
    """Words that look like a ligature letter group went missing: the book's own vocabulary is the guide (this is a
    survey, nothing is corrected). Two shapes: a token that becomes a frequent word when a group is inserted, and
    two neighbouring fragments that become one."""
    token = re.compile(r"[^\W\d_]+")
    groups = ("ffi", "ffl", "ff", "fi", "fl")
    freq: Counter[str] = Counter()
    for _, _, _, _, seg in segments(bundle):
        freq.update(w.lower() for w in token.findall(seg["text"]))

    def repair(word: str, min_freq: int) -> list[str]:
        return [word[:i] + g + word[i:] for i in range(1, len(word)) for g in groups
                if freq.get(word[:i] + g + word[i:], 0) >= min_freq]

    out = []
    for side, bi, si, block, seg in segments(bundle):
        text = seg["text"]
        matches = list(token.finditer(text))
        for k, m in enumerate(matches):
            w = m.group().lower()
            if freq[w] <= 2:
                fixes = repair(w, 3)
                if fixes:
                    out.append((side, bi, si, m.start(), block.get("page"), text[max(0, m.start() - 20) : m.end() + 20],
                                "inside-token", fixes[0]))
            if k + 1 < len(matches):
                n = matches[k + 1]
                if text[m.end() : n.start()] != " ":
                    continue
                v = n.group().lower()
                for g in groups:
                    joined = w + g + v
                    if freq.get(joined, 0) >= 2 and (freq[v] <= 3 or freq[w] <= 3) and freq[w] + freq[v] < 2 * freq[joined] + 6:
                        out.append((side, bi, si, m.start(), block.get("page"),
                                    text[max(0, m.start() - 20) : n.end() + 20], "fragment-gap", joined))
                        break
    return out


# --- Subcommands ---


def _write_tsv(path: Path, header: list[str], rows) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writerow(header)
        w.writerows(rows)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\"))


def cmd_scan(args) -> int:
    bundle = read_bundle(args.bundle)
    candidates = find_candidates(bundle)
    pdfs = {"source": PdfPages(args.source_pdf), "target": PdfPages(args.target_pdf)}
    rows = []
    stats: Counter = Counter()
    for c in candidates:
        evidence = candidate_evidence(c, pdfs)
        rows.append([c.side, c.block, c.segment, c.offset, c.page, c.context, evidence])
        stats[(c.side, c.kind, evidence.split(";")[-1].strip().split(" ")[0])] += 1
    _write_tsv(args.candidates, ["side", "block", "segment", "offset", "page", "context", "evidence"], rows)

    # Recall check against the PDF: every stray space of the PDF should have a candidate with the same key.
    keys = {(re.sub(r"\s+", " ", c.context_from[max(0, c.context_offset - 8) : c.context_offset]),
             re.sub(r"\s+", " ", c.context_from[c.context_offset + 1 : c.context_offset + 9])) for c in candidates}
    missing = 0
    stray_total = 0
    for _, left, right in pdfs["source"].stray_keys():
        stray_total += 1
        if not any(k[0].endswith(left[-4:]) and right.startswith(k[1].replace("\n", " ")[:4]) for k in keys):
            missing += 1
    dropped = dropped_survey(bundle)
    _write_tsv(args.dropped, ["side", "block", "segment", "offset", "page", "context", "shape", "repair"], dropped)

    print(f"candidates: {len(candidates)}")
    for k, n in sorted(stats.items()):
        print(" ", *k, n)
    print(f"stray spaces in the source PDF: {stray_total}; without a candidate: {missing}")
    print(f"stray spaces in the target PDF: {len(pdfs['target'].stray_keys())}")
    print(f"dropped-ligature survey: {len(dropped)}", dict(Counter((r[0], r[6]) for r in dropped)))
    return 0


def read_decisions(path: Path) -> list[dict[str, str]]:
    rows = _read_tsv(path)
    for r in rows:
        if r["decision"] not in DECISION_VALUES or r["class"] not in CLASS_VALUES:
            raise ValueError(f"bad decision row: {r}")
    return rows


def apply_decisions(bundle: dict, rows: list[dict[str, str]]) -> dict:
    """The bundle with every `join` gap closed. Fails loudly if a decision does not match a current candidate, if a
    candidate has no decision, or if a decision is duplicated. Only whitespace is removed from `text`."""
    candidates = find_candidates(bundle)
    by_key = {c.key: c for c in candidates}
    seen: set[tuple] = set()
    removals: dict[tuple[str, int, int], list[int]] = {}
    for r in rows:
        key = (r["side"], int(r["block"]), int(r["segment"]), int(r["offset"]))
        if key in seen:
            raise ValueError(f"duplicate decision {key}")
        seen.add(key)
        c = by_key.get(key)
        if c is None:
            raise ValueError(f"decision {key} does not match a candidate")
        if (r["class"] == "translator") != (c.kind == "translator"):
            raise ValueError(f"decision {key}: class {r['class']} against a {c.kind} candidate")
        if c.kind == "translator" and r["decision"] != "join":
            raise ValueError(f"decision {key}: the translator's fix cannot be reverted")
        if c.kind == "open" and r["decision"] == "join":
            removals.setdefault(key[:3], []).append(key[3])
    undecided = [k for k in by_key if k not in seen]
    if undecided:
        raise ValueError(f"{len(undecided)} candidates have no decision, first: {undecided[0]}")

    out = json.loads(json.dumps(bundle))
    documents = {d["side"]: d for d in out["documents"]}
    for (side, bi, si), offsets in removals.items():
        seg = documents[side]["blocks"][bi]["segments"][si]
        text = seg["text"]
        for offset in sorted(offsets, reverse=True):
            m = re.compile(r"\s+").match(text, offset)
            if not m or not GAP.search(text[max(0, offset - 3) : m.end() + 1]):
                raise ValueError(f"offset {offset} of {(side, bi, si)} no longer matches a gap")
            text = text[:offset] + text[m.end() :]
        seg["text"] = text
    return out


def _context_of(bundle: dict, key: tuple[str, int, int, int]) -> str:
    documents = {d["side"]: d for d in bundle["documents"]}
    text = documents[key[0]]["blocks"][key[1]]["segments"][key[2]]["text"]
    return text[max(0, key[3] - 20) : key[3]] + "_" + text[key[3] + 1 : key[3] + 21]


def cmd_apply(args) -> int:
    bundle = read_bundle(args.bundle)
    rows = read_decisions(args.decisions)
    gold = apply_decisions(bundle, rows)
    write_bundle(args.gold, gold)
    doubtful = [[r["side"], r["block"], r["segment"], r["offset"], r["class"], _context_of(bundle, (r["side"], int(r["block"]), int(r["segment"]), int(r["offset"]))), r["note"]]
                for r in rows if r["decision"] == "doubtful"]
    _write_tsv(args.doubtful, ["side", "block", "segment", "offset", "class", "context", "note"], doubtful)
    print(f"{args.gold}: {Counter(r['decision'] for r in rows)}; doubtful rows mirrored: {len(doubtful)}")
    return 0


def is_subsequence(small: str, big: str) -> bool:
    it = iter(big)
    return all(ch in it for ch in small)


def check_gold(original: dict, gold: dict) -> dict[str, int]:
    """Raise AssertionError on any difference other than removed whitespace in segment texts; return counts."""
    assert original.keys() == gold.keys()

    def without_text(bundle: dict) -> dict:
        copy = json.loads(json.dumps(bundle))
        for _, _, _, _, seg in segments(copy):
            seg["text"] = None
        return copy

    assert without_text(original) == without_text(gold), "a field other than segment text differs"
    changed = 0
    removed = 0
    for (side, bi, si, _, a), (_, _, _, _, b) in zip(segments(original), segments(gold)):
        if a["text"] == b["text"]:
            continue
        where = (side, bi, si)
        assert re.sub(r"\s+", "", a["text"]) == re.sub(r"\s+", "", b["text"]), f"{where}: not whitespace only"
        assert len(b["text"]) < len(a["text"]) and is_subsequence(b["text"], a["text"]), f"{where}: whitespace added"
        changed += 1
        removed += len(a["text"]) - len(b["text"])
    translator_kept = 0
    for c in find_candidates(original):
        if c.kind != "translator":
            continue
        documents = {d["side"]: d for d in gold["documents"]}
        text = documents[c.side]["blocks"][c.block]["segments"][c.segment]["text"]
        around = c.text[max(0, c.offset - 3) : c.offset + 3]
        assert around in text, f"{c.key}: the translator's fix was not kept"
        translator_kept += 1
    return {"segments changed": changed, "whitespace removed": removed, "translator fixes kept": translator_kept}


def cmd_check(args) -> int:
    original = read_bundle(args.bundle)
    gold = read_bundle(args.gold)
    with zipfile.ZipFile(args.bundle) as a, zipfile.ZipFile(args.gold) as b:
        assert a.namelist() == b.namelist(), "entries differ"
    counts = check_gold(original, gold)

    from tradurre.db import get_connection, init_db
    from tradurre.domain.invariants import check_project
    from tradurre.services.bundle import import_bundle

    with tempfile.TemporaryDirectory() as tmp:
        conn = get_connection(Path(tmp) / "check.db")
        try:
            init_db(conn)
            book_id = import_bundle(conn, args.gold.read_bytes())
            problems = check_project(conn, book_id)
        finally:
            conn.close()
    assert problems == [], f"invariants: {problems[:3]}"

    left = [c for c in find_candidates(gold) if c.kind == "open"]
    counts["gaps left"] = len(left)
    if args.decisions.exists():
        rows = read_decisions(args.decisions)
        expected = sum(r["decision"] in ("keep", "doubtful") for r in rows)
        assert len(left) == expected, f"{len(left)} gaps left, {expected} keep+doubtful decisions"
        counts["keep + doubtful decisions"] = expected
        counts["translator rows"] = sum(r["class"] == "translator" for r in rows)
    print("check passed:", counts)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Correct ligature gaps of a reviewed bundle into a gold copy.")
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument("--decisions", type=Path, default=DECISIONS)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="candidates, PDF evidence, dropped-ligature survey")
    scan.add_argument("--source-pdf", type=Path, default=SOURCE_PDF)
    scan.add_argument("--target-pdf", type=Path, default=TARGET_PDF)
    scan.add_argument("--candidates", type=Path, default=CANDIDATES)
    scan.add_argument("--dropped", type=Path, default=DROPPED)
    scan.set_defaults(run=cmd_scan)
    apply = sub.add_parser("apply", help="decisions file -> corrected copy")
    apply.add_argument("--doubtful", type=Path, default=DOUBTFUL)
    apply.set_defaults(run=cmd_apply)
    check = sub.add_parser("check", help="the corrected copy against the original")
    check.set_defaults(run=cmd_check)
    args = parser.parse_args(argv)
    for path in (args.bundle,):
        if not path.exists():
            print(f"not found: {path}", file=sys.stderr)
            return 1
    try:
        return args.run(args)
    except (ValueError, AssertionError) as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
