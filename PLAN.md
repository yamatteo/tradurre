# Tradurre — Plan

How to get from the current state (v0.1.0) to what `SPEC.md` describes. Maintained by the planning agent
(`/pauli`), executed one task at a time by the implementing agent (`/braun`); see "Workflow" in `CLAUDE.md`.

## Conventions

- `##` = stage, `###` = step, `####` and deeper = sub-steps. A heading with a `Status:` line and no
  sub-headings is a **task**: the unit `/braun` executes. A heading without a `Status:` line is not ready yet and
  must be broken down (or given a status and **Done when:**) by `/pauli` before anyone works on it.
- Every leaf carries a status line right under its heading:
  `Status: todo | in progress | done | blocked | dropped`, followed by **Done when:** (the verifiable outcome).
  A done leaf gets a one-line `Report:` (date, what changed, test result) from `/braun`.
- Stages are done in order. Within a stage, tasks are done top to bottom unless noted.
- Detail lives where work is imminent: the current stage is broken down to tasks; later stages stay broad until
  `/pauli` refines them.
- Completed stages move to `PLAN.<yymmdd>.Stage<n>.md`, leaving a pointer and a short summary here.

## Current state (v0.1.0), in brief

- Storage is a single `pairs` table: one row per aligned sentence pair, holding the text of both sides, with
  `section`/`paragraph` integer tags. Alignment and text are the same thing, so alignment corrections destroy and
  recreate text (`resplit` also drops formatting), and only 1:1 pairs (padded with blanks) can be represented.
- Extraction (`doc_adapter`, `glyph_resolver`) is solid for PDF glyph damage but removes junk (page numbers,
  headers) by deletion with line-based regexes, ignoring PDF layout.
- Alignment exists twice: a local anchor heuristic (`aligner.py`) and a heavy Colab pipeline (bertalign, LLM
  judge) whose many-to-many output is flattened to 1:1 on import.
- UI: three-step import wizard, a TipTap editor per pair, FTS5 search over pairs (no context).
- One connection per request; every write handler is one `BEGIN IMMEDIATE` transaction. The app's `pairs` model
  has no undo/history.
- **Stage 1 is complete.** The new model exists below the API, unused by it yet: migrations 2–4
  (documents/blocks/segments/beads, operations, `bead_index`) and `tradurre/domain/` (layer builder, invariant
  checker, every SPEC §3.3 correction with persistent undo/redo, replace beads, bead search with folding and
  highlights), covered by unit tests and a randomized round trip that also checks the index.
- **Re-planned with the user (2026-10-03):** a thin usable slice first (Stage 2: txt/docx → beads → correction
  screen), then better import and an in-app gold chapter (Stage 3), the full review view (Stage 4), Colab right
  after import (Stage 5). Footnotes stay excluded as SPEC says; reviewed and confidence stay separate.
- **Stage 2 in progress:** a txt/docx pair imports into the new model and every correction works through
  `/api/v2/books` (`tradurre/api/books.py`). The book screen (`BookView.vue`, `/book/:id`) imports, reads and
  navigates a book and makes every SPEC §3.3 correction (keys and header buttons, inline segment editing,
  undo/redo). **Stage 2 is complete** (2026-10-03); the user's books are PDFs, so the slice is usable on them only
  after Stage 3's "PDF import in the app".
- Licensed AGPL-3.0-only (`LICENSE`).
- Python 3.14 only (`.python-version`, `requires-python`, launcher). Stage 0 is complete.
- `uv run pytest`: 266 passed (PyMuPDF is in the `dev` group), also on a fresh clone (tests read only committed
  synthetic fixtures; `-m library` tests run only where `library/contrefeu.*.pdf` exists, and assert counts only).
- PDF extraction (`extract.py`) works on the reference book (page numbers, chapter numbers, two-up spreads); the
  app still refuses PDFs until "PDF import in the app".
- `uv.lock` is tracked; `pytest`/`httpx` are in the `dev` group. The Windows launcher's `uv tool install` resolves
  from PyPI and never reads the lock.
- `npm run type-check` passes; releases build with `npm run build`. `npm run test:e2e` runs on its own
  backend (:8001, throwaway `.e2e.db`) and Vite (:5174), never the user's database. Setup per machine: `npx
  playwright install chromium` (on Ubuntu 26.04 with `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64`); tests
  use the full Chromium headless (`channel: 'chromium'`), so the headless-shell build isn't needed.
- No user data needs migrating: the new model can start from an empty database.
- A real book pair is available **locally only**: `library/contrefeu.fr.pdf` / `contrefeu.it.pdf` (gitignored,
  copyrighted: never commit it or excerpts of it; the repo is public). See "Reference book" in Stage 3.

---

## Stage 0 — Groundwork
Done (2026-10-03). Archived in `PLAN.261003.Stage0.md`. Aligner recursion fix, committed synthetic test fixtures,
repo hygiene (`.gitignore`, tracked `uv.lock`, dev dependency group, dead preview endpoint removed), frontend
type-check passing, one connection per request with `BEGIN IMMEDIATE` write transactions, Python 3.14 everywhere.

---

## Stage 1 — New data model
Done (2026-10-03). Archived in `PLAN.261003.Stage1.md`. Migration mechanism (`MIGRATIONS`, `PRAGMA user_version`);
migrations 2–4: documents/blocks/segments/beads, operations log, `bead_index` FTS5 kept in sync by triggers.
`tradurre/domain/`: layer builder (`layer.py`), invariant checker I1–I5 (`invariants.py`), recorder with
persistent linear undo/redo and coalescing (`history.py`), sparse ords (`ordering.py`), every SPEC §3.3
correction (`beads.py`, `segments.py`, `blocks.py`), the bulk primitive `replace_beads` (`replace.py`), and
`search_beads` with folding and highlights (`search.py`). Rules decided there and still binding: alignment
corrections set the bead to `manual`/1.0 and keep `reviewed`; exclude/include never change existing beads'
confidence; a join across beads merges the whole run of beads. Covered by unit tests and a randomized round trip
(20 seeds × 60 steps) that also checks the index.

---

## Stage 2 — Thin slice: txt/docx to a correction screen
Done (2026-10-03). Archived in `PLAN.261003.Stage2.md`. Structured txt/docx extraction (`services/extract.py`:
blocks with kinds, BOM/Latin-1 handling, docx headings); interim build (`services/build.py`, v0.1 splitter and
anchor aligner); `/api/v2/books` (`api/books.py`): import, read, every SPEC §3.3 correction, undo/redo, 409 with
the domain's message. Book screen (`BookView.vue`, `BeadRow.vue`, `BeadActions.vue`, `selection.ts`): import form,
book list, reading and keyboard navigation, `n` to the next unreviewed bead, "Show excluded", bead corrections from
keys (Alt+↑/↓ m s r x, Ctrl+Z/Y) and a header bar, inline segment editing (Enter, Ctrl+Enter split, `j` join).
Rules decided there and still binding: after a correction the whole book is returned and reconciled (unchanged
beads keep their objects); one correction at a time (`busy`); rows never change height with the selection; the
selection is injected and a row is current via a per-id `currentRow` map, so a move wakes two rows. E2E on a
throwaway backend (:8001, `.e2e.db`) and Vite :5174, including 10,000-bead timing checks (load < 5 s, 20 ↓ < 2 s,
`r` < 1.5 s).

---

## Stage 3 — Better import

**Decided (user, 2026-10-03): tradurre is AGPL-3.0-only** (`LICENSE`, `pyproject.toml`), so PyMuPDF (AGPL-3.0)
stays the PDF library. The launcher already installs `tradurre[pdf]` (`EXTRAS=pdf`); "PDF import in the app" makes
`pymupdf` a core dependency (the `pdf` extra stays, redundant, for the launcher). Until then it is a dev dependency so tests run.

### Reference book
(Context for the whole stage, not a task.) `library/contrefeu.fr.pdf` (Emmanuel Venet, *Contrefeu*) and `library/contrefeu.it.pdf` (*Sacro fuoco*), both
born-digital, ~38,000 words per side. Local only (see "Current state"). How the tasks of this stage use it:
- **Opt-in tests.** `tests/test_library.py`, every test marked `library` and skipped when the files are missing,
  so a fresh clone stays green. They assert structural facts (logical page count, first and last sentence of
  the body, no page-number text in included blocks, reading order across page boundaries), never long excerpts.
- **Failures become committed fixtures.** A problem found on the real book gets a short synthetic reproduction in
  `tests/fixtures/` before it is fixed (same rule as Stage 0 "Test fixtures", archived).
- **Gold chapter.** One chapter whose alignment the translator has checked by hand; see the step "Gold
  chapter" below. It is how the baseline aligner (here) and the Colab aligner (Stage 5) are compared, by numbers
  instead of by impression.

Facts already measured (PyMuPDF `get_text`, 2026-10-03):
- FR: 128 single pages (439×651 pt); page number alone at the bottom centre (y≈567); no running heads seen; 480
  soft hyphens (U+00AD) and 40 hard `-` at line ends; no ligature or private-use glyphs, so this book does not
  exercise `glyph_resolver`.
- IT: 93 **two-up spreads** (765×595 pt, landscape: two book pages per PDF page, columns at x≈48–335 and
  x≈434–720); both page numbers come out as one block ("25\n24"); 1,060 soft hyphens. **The current
  extractor scrambles reading order**: `doc_adapter.load_as_text` emits the right-hand page before the left one
  on every spread (verified: "…iniziava a invecchiare e a prendere \n25\n24\nnumerosi edifici pubblici…"). So
  v0.1 cannot import this book correctly today.
- Front/back matter (half title, "Du même auteur", colophon, ISBN, series blurb) is present on both sides and must
  end up as excluded blocks.

### PDF extraction
Continues "Structured extraction" (Stage 2) with the same design.

#### PDF lines and logical pages
Status: done
**Done when:** `tests/test_extract_pdf.py` passes; `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — `pymupdf` in the `dev` group (`uv.lock`), `_Line`, `_pdf_lines` with the two-up rule in `extract.py` (`extract` still refuses `.pdf`); `tests/test_extract_pdf.py` 4 tests (the two-up case needs ≥ 60% two-up spreads, so its document has 3 spreads, one with text only on the right); local check on the reference book: FR 128 logical pages, IT 184 (91 spreads × 2 + 2 portrait covers), left page before right across a spread; pytest 253 passed (249 + 4).
Verified (/pauli, 2026-10-03, `1e3a45b`): pytest 253; the rule and tests match the task, and the test-document
fix is correct (the task's own 60% rule required it). Measured on the reference book with `_pdf_lines` to check
the next task's thresholds, which led to corrections there (see its "Measured" note).

In `extract.py`, the first half of PDF extraction (no blocks yet):
- Add `pymupdf` to the `dev` dependency group (`uv add --dev pymupdf`; `uv.lock` updated) so PDF tests run in
  `uv run pytest`. The `pdf` extra stays as it is (see the open question under this stage).
- `@dataclass _Line(page: int, x0: float, y0: float, x1: float, y1: float, text: str, size: float)`: `page` is
  the 0-based logical page, `size` the largest span size in the line, `text` the spans joined (lines whose text is
  only whitespace are dropped).
- `_pdf_lines(doc) -> tuple[list[_Line], list[tuple[float, float]]]`: the lines of every logical page in reading
  order, and each logical page's `(width, height)`.
  - **Two-up spreads**, decided once per document: a landscape page (`width > height`) "looks two-up" if at least
    20% of its lines have their centre left of `width / 2` and at least 20% right of it. If at least 60% of the
    document's landscape pages that have text look two-up, every landscape page is split: lines with centre left
    of `width / 2` go to logical page `2k`, the others to `2k + 1` with `x` shifted by `-width / 2`, and both
    logical pages are `(width / 2, height)`. (A blank or one-column page in a two-up book still yields two logical
    pages, so page counts stay right.) Otherwise one logical page per PDF page.
  - Within a logical page, lines sorted by `(y0, x0)`.
- `tests/test_extract_pdf.py` (PDFs built in the test): a portrait page's lines in top-to-bottom order; a
  two-page landscape document with text in both columns → 4 logical pages, left column's lines before the right
  column's, right-hand `x` shifted; in that document, a page with text only on the right still gives 2 logical
  pages, its lines on the second; a landscape document with one centred column → one logical page per PDF page;
  page sizes returned correctly.

#### PDF blocks
Status: done
**Done when:** `tests/test_extract_pdf.py` passes with the cases below; `uv run pytest -m library` passes on this
machine (the reference book is present); `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — rule (a) applied (non-paragraph blocks end at a page boundary) on top of the blocked tree: `_extract_pdf`, `extract` reads `.pdf`, API refuses `.pdf` by extension, obsolete test removed; `tests/test_extract_pdf.py` 13 pass (2 new for rule (a)); `tests/test_library.py` passes: FR 208 paragraph / 120 page_number / 27 heading / 3 footnote, IT 197 / 157 / 27 / 2, chapter numbers 25 = 25, no stray numbers, 0 warnings; `uv run pytest` 266 passed (253 − 1 obsolete + 9 PDF + 5 library runs); e2e `books.spec.ts` 4 passed.
Verified (/pauli, 2026-10-03, `520747c`): pytest 266, library tests pass. Checked on the reference book (counts
only): extraction takes 1.75 s (FR) / 1.89 s (IT); hard line-end hyphens kept by the join rule never produce a
word whose unhyphenated form also occurs in the book (0 of 505 FR, 0 of 221 IT hyphenated tokens), so keeping
them is right for this book.
Report: 2026-10-03 — blocked on one library test: number-only headings FR 25, IT 24. The missing IT one (size 11.3, top of logical page 7) merges into the preceding heading block (a 9-word front-matter heading on page 5; page 6 is blank), because "consecutive lines of the same kind form one block" has no page condition. Needs a rule: e.g. non-paragraph blocks don't continue across a page boundary, or a chapter-number line is always its own block. Everything else is done, uncommitted: `_extract_pdf` (classification, assembly, joining, glyphs), `extract` reads `.pdf`; the API still refuses `.pdf` with 415 (now by extension, since `extract` no longer raises) and the obsolete `test_pdf_not_implemented_yet` is removed; `tests/test_extract_pdf.py` 11 pass; `tests/test_library.py` 3 tests (marker registered), 2 pass: page numbers FR 120, IT 157; stray included numbers 0 both sides; blocks FR 208 paragraph / 120 page_number / 27 heading / 3 footnote, IT 197 / 157 / 26 / 2; `uv run pytest` here: 263 passed, 1 failed (that library test; on a fresh clone the library tests skip).
Answered (/pauli, 2026-10-03, user agreeing): resume from the uncommitted tree. **Rule (a): a block of any kind
other than `paragraph` never continues onto another logical page** (in `_extract_pdf`'s assembly, a line starts a
new block when the previous block's last line is on a different page). Only paragraphs legitimately run over a
page break, and they already have their own rule. This also fixes a second merge the same line of code allows: a
footnote at the bottom of page n and one at the bottom of page n+1, with the paragraph continuing between them,
currently join (the continuing paragraph doesn't end the footnote block). Not adopted: "a chapter number is always
its own block" alone (fixes only this case; a half title and a dedication on consecutive pages would still merge);
within one page, "IV" followed by a title line still forms one heading block, which aligns fine since the other
side merges the same way. Add tests: two heading lines on consecutive pages (with a blank page between) → two
heading blocks; footnotes at the bottom of two consecutive pages, with a paragraph running across the break → two
footnote blocks and one paragraph. Braun's deviations are accepted: the API refuses `.pdf` by extension until "PDF
import in the app"; test PDFs embed the font to keep U+00AD.

`extract` for `.pdf`, from `_pdf_lines`:
- `body_size` = the line size covering the most characters in the document (`_Line.size` rounded to 0.1 pt,
  weighted by `len(text)`; lines carry only their largest span's size, which is good enough). Per logical page,
  `left` = the most common `round(x0)` among lines whose `size` is within 0.5 pt of `body_size`.
- **Measured** (/pauli, 2026-10-03, reference book through `_pdf_lines`; numbers only, no text): FR page numbers
  sit at `y0/h` 0.871 (size 10, body 11.9), so a 12% band by `y0` would catch **none** of them; IT page numbers
  at 0.933 (size 8.2, body 12.5). Number-only lines that are **chapter numbers**: FR 25, size 14, anywhere from
  0.13 to 0.72 of the page; IT 25, size 11 (smaller than the body!), at the top (0.08) of the chapter's first
  page. So position and size alone can't tell IT chapter numbers from page numbers; frequency can (page numbers
  sit in the same slot on 120/128 and 157/184 logical pages, chapter numbers on ~13%). No running heads in this
  book. First-line indent ≈ 14 pt on both sides; body line pitch 14.0 (FR) and ≈ 16.1 (IT).
- "In the top/bottom band" below means: the line's vertical centre `(y0 + y1) / 2` is within 15% of the logical
  page height from its top or bottom edge.
- Classification, per line, in this order:
  - `page_number`: text matches `^\s*([0-9]+|[ivxlcdm]+)\s*$` (case-insensitive), `size <= body_size + 0.5`, in
    the top or bottom band, **and** its slot is frequent: candidates are grouped by (band, `round(size)`), and only
    a group with lines on at least 25% of the document's logical pages counts;
  - `running_head`: in the top band, and its text with digits removed, casefolded and stripped is non-empty and
    occurs (so normalized) in the top band of at least 3 logical pages;
  - `heading`: `size >= body_size * 1.1`, or a line that is only a chapter number, `^\s*([0-9]+|[IVXLC]+)\s*$`
    **case-sensitive** (lower-case Roman numerals would catch Italian words like "di", "mi", "vi" wrapped alone
    onto a line; lower-case Roman page numbers are still caught by `page_number`);
  - `footnote`: `size <= body_size * 0.9` and in the bottom 40% of the page;
  - otherwise body.
- Assembly: consecutive lines of the same kind form one block (non-paragraph blocks never across a logical page
  boundary; see "Answered" above), except that body (`paragraph`) lines also start a
  new block when `x0 >= left + 0.5 * body_size` (first-line indent) or the vertical gap to the previous body line
  exceeds 1.5 × the median body line pitch of the document; `page_number` and `running_head` lines are one block
  each. A paragraph continues across a page boundary unless the next page's first body line is indented (the
  excluded lines in between don't break it). `page` = logical page of the block's first line, plus 1.
- Joining lines inside a block: a line ending in U+00AD (soft hyphen) is joined to the next with the soft hyphen
  removed and no space; a line ending in a letter followed by `-` is joined keeping the `-` and no space; any
  other pair with one space. Soft hyphens elsewhere are removed. Then `normalize_ocr_artifacts`.
- Glyphs: `glyph_resolver.resolve_pua_glyphs(doc)` (no LLM) and `apply_resolution(text, mapping)` on every
  block's text; its warnings go to `Extraction.warnings`.
- Tests (PDFs built in the test, one font, sizes like the reference book): indented paragraphs become separate
  blocks; a paragraph running over a page break stays one block, with the page number between excluded as its own
  `page_number` block; a page number at 87% of the page height (FR-like) is a `page_number`; in a 10-page document
  with page numbers at the bottom of every page, a small number-only line at the top of 2 pages (IT-like chapter
  number) is a `heading`, not a `page_number`; a soft hyphen and a hard hyphen at line ends; a repeated top line
  on 3 pages → `running_head`, on 2 → not; a larger line → `heading`; small text at the bottom → `footnote`; a
  two-up document reads left page then right page.
- `tests/test_library.py` (new; every test marked `library` and skipped when `library/contrefeu.*.pdf` is missing;
  register the marker in `pyproject.toml` `[tool.pytest.ini_options]`): for each side, at least 110 (FR) / 150
  (IT) `page_number` blocks; no included block whose text is number-only except `heading`s; the number of
  number-only `heading` blocks is the same on both sides (25 each when measured). Counts only, never text in
  assertions or messages (the book is copyrighted). Report the actual numbers.

#### Front and back matter
Not ready; after "PDF import in the app", so the translator can see the real book in the screen meanwhile (front
and back matter show up as short one-sided beads at both ends, which `x` excludes one block at a time).
Measured after "PDF blocks" (counts only): FR has ~25 short blocks (1–7 words, plus a 43-word small-print block
classified `footnote`) on logical pages 3–6 before the first chapter number, and ~6 short blocks on the last page;
IT ~9 blocks on pages 3–5, ~7 on the last page. A rule can't simply exclude everything before chapter 1: SPEC §2
counts a preface as real one-sided material to align. To decide when writing the task: short-block density per
page, and whether the user wants a bulk "exclude this page" correction instead (a SPEC change).

Decided (user, 2026-10-03): sources are mixed and unknown per book (PDF, sometimes the translator's own .docx for
the Italian side), so both paths stay first-class: the PDF pipeline is not the only road, and docx import keeps
its tests.

### PDF import in the app
Status: done
Report: 2026-10-03 — pymupdf core dependency (`pdf` extra kept, commented); unreadable PDF → 400; extraction via `run_in_threadpool`; form accepts .pdf; API test on a built PDF pair, library import test (reference pair: 201, 4.3 s wall, 1354 beads, 185 one-sided); pytest 268 passed, `-m library` 6 passed, type-check clean, e2e 28 passed (the form test's button label updated too).
**Done when:** `uv run pytest` passes (including the new tests); `uv run pytest -m library` passes on this machine
with the new import test; `npm run type-check` passes; `npm run test:e2e` passes.

The reference book becomes importable in the app (SPEC §3.1.1: born-digital PDF, .docx or .txt).
- `pyproject.toml`: `pymupdf>=1.24` moves into `[project].dependencies` and out of the `dev` group (`uv.lock`
  updated). The `pdf` extra **stays** with its current content: the Windows launcher installs `tradurre[pdf]`
  (`packaging/start-tradurre.bat:14`), and dropping the extra would break that line; it is now redundant, say so in
  a comment above it. Do not change the launcher.
- `tradurre/services/extract.py`: `_extract_pdf` turns a file PyMuPDF can't open into `ValueError("The file is
  not a readable PDF")` (catch the exception `pymupdf.open` raises; don't catch broadly around the rest).
- `tradurre/api/books.py`: remove the `.pdf` refusal in `_extract` (the 415 goes away); `ValueError` already maps
  to 400. Extraction is CPU work of seconds per PDF inside an `async def` handler, which would freeze every other
  request meanwhile: call `extract` through `starlette.concurrency.run_in_threadpool`. Nothing else in the import
  changes.
- Frontend: `BookImport.vue` file inputs `accept=".txt,.docx,.pdf"`; `ProjectList.vue` button "Import a book
  (txt/docx/pdf)".
- Tests:
  - `tests/test_books_api.py`: `test_pdf_is_refused_and_writes_nothing` becomes: an unreadable `.pdf`
    (`b"%PDF-1.4"`) → 400 "The file is not a readable PDF", nothing written; plus a new test importing a small
    PDF pair built in the test (reuse the embedded-font helper pattern of `tests/test_extract_pdf.py`; a few
    paragraphs and page numbers per side) → 201, beads present, page-number blocks excluded (`GET` shows them in
    `excluded`).
  - `tests/test_library.py`: importing the reference pair through `POST /api/v2/books` (TestClient on a temporary
    database, as in the API tests) returns 201; record in the `Report:` the wall time of the request, the bead
    count, and how many beads are one-sided. Assert only 201 and bead count > 1000 (counts, no text).
  - `frontend/e2e/books.spec.ts`: the PDF case now expects "The file is not a readable PDF".
- After this task, tell the user in the report how to try it: `uv run tradurre --dev` plus `npm run dev`, import
  `library/contrefeu.fr.pdf` / `contrefeu.it.pdf`.

### Import warnings and run metadata
Not ready: warnings and run metadata (counts, timings; SPEC §3.1.5, §4 "Debuggable") stored on the project in
tables added by a migration, shown in the correction screen.

### Gold chapter
Not a task yet: becomes one once the reference book imports through "PDF import in the app". Decided
(user, 2026-10-03): made **in the app**, not in a spreadsheet:
- The translator imports the reference book, corrects one chapter in the correction screen (moving sentences,
  splitting/joining segments; text edits only for extraction damage) and marks its beads reviewed. Default
  chapter: the first of the body, ~200–400 sentences, with some 1:2/2:1 and unmatched material.
- `scripts/gold_export.py <project id> <first bead id> <last bead id>` writes `library/contrefeu.gold.tsv`
  (`source<TAB>target` per bead, segments joined with a space) and refuses if any bead in the range is unreviewed.
- **Format independent of segmentation:** a gold bead is stored as text, and scoring maps every bead to a
  character span of each side's normalized chapter text. Metrics are bead-boundary precision/recall/F1 on those
  spans, so the gold stays valid when the segmenter or extractor changes later.
- **Scoring:** `scripts/gold_score.py <aligner>` prints the metrics plus the worst-scoring stretches. Its result
  is recorded in the `Report:` of every aligner task from then on.

### Segmentation
French/Italian sentence splitter (abbreviations, dialogue dashes, guillemets, ellipses), with regression tests
from real failure cases; replaces `split_sentences` in `build_book`.

### Baseline local aligner
The current anchor heuristic plus a length-based (Gale–Church-style) cost, producing beads with real confidence,
fast enough to run on import and on an arbitrary sub-range (for "re-align range"); replaces the interim
alignment in `build_book`, scored on the gold chapter.
Decided (user, 2026-10-03): it is not yet known whether Colab will run on every book, so this work is **capped**:
one anchor + length aligner, a target F1 on the gold chapter agreed with the user when the task is written, no
further tuning rounds. After the first real book has gone through import and review, /pauli asks again whether
Colab (Stage 5) should come before any more local-aligner work.

---

## Stage 4 — Review view

Re-confirmed (user, 2026-10-03, after discussing that a mid-cell paste changes the stored edition, which search
and export then show): any paste is allowed as a text edit. The "original text / revert" display above is what
lets the translator see where an edition was changed.
Decided (user, 2026-10-03): the review screen permits **cut/copy/paste between rows** ("the user is king and
responsible"). A cut at one row's edge pasted at the adjacent edge of the neighbouring row leaves the edition's
text unchanged and is recorded as a bead-boundary move; any other paste is a text edit (original text kept,
undoable). SPEC §3.3 gets a line for it when this stage is planned (wording to agree with the user then).

The correction screen of Stage 2 grows into the main screen of SPEC §3.3: virtualized bead list, confidence
and unmatched highlighting, next-problem navigation, skim-review pass, cut/copy/paste between rows, re-align
range, incremental updates instead of whole-book refetch, and showing a segment's original extracted text with
"revert to original" (SPEC §2: "the translator can always compare or revert"; `original_text` is stored but not
yet in the API). Plain text editing; TipTap is not used here.

Decided (user, 2026-10-03): `reviewed` and `confidence` stay separate signals. A correction sets the touched
beads to `manual`/1.0 but leaves their reviewed mark as SPEC §3.3 says; "done with the book" = every bead
reviewed.

---

## Stage 5 — Colab round trip

Decided (user, 2026-10-03): the Colab alignment is meant to run **right after import**, before review. The
bundle records a fingerprint of the project's text layer (segment ids and texts, block exclusion); loading an
alignment file is **refused** if the project's text layer no longer matches it ("export a new bundle"), so the
file never refers to stale segments. Within a matching project, reviewed beads are kept as SPEC §3.2 says
(after a skim pass that means little or nothing is replaced: by design).

Project bundle format (text layer) and alignment file format (beads over bundle segments), both versioned.
Adapt `pipeline.py`/`pipeline_cli.py` and the bertalign/LLM-judge stages to consume a bundle and emit native
many-to-many beads. Loading an alignment file replaces only unreviewed regions. A notebook for Colab.

Input from the old Colab cell (`colab_cell_blueprint.py`, untracked, user's past workflow: clone → `uv sync
--extra align --extra ocr --extra pdf` → upload two files → `tradurre-align` → download JSON + log). Keep its
shape (one cell, upload, run the CLI, download), but:
- **Version pinning.** It clones `main`, while the app is an installed release. The bundle records the app version
  and format version; the notebook checks out that tag (fallback: refuse with a clear message on an unknown
  format version), so app and aligner always agree on formats.
- **GPU check on the right torch.** It checks `torch.cuda` with Colab's preinstalled torch (`:15`, `:47`), not the
  one `uv sync` installs from `uv.lock` into `.venv`. Check with `uv run python -c "import torch; …"` after the
  sync and stop if the locked torch can't see the GPU (a CUDA/driver mismatch would otherwise run silently on CPU).
- **Only `--extra align`.** A bundle is already extracted text; `pdf`/`ocr` are needed only for the raw-files
  convenience route.
- **No token.** The repo is public; drop `GITHUB_TOKEN` (today it is also written into `.git/config` on the VM).
- **Warnings travel in the alignment file**, not only in the `.log`, so they reach the project (SPEC §3.1.5).

---

## Stage 6 — Search and export

Search UI on the new index with context expansion and jump-to-bead (SPEC §3.4). Kept here rather than pulled
forward (user, 2026-10-03): alignment quality first. Exports: TMX/TSV corpus,
per-edition .txt/.docx, project bundle as backup (SPEC §3.5).

---

## Stage 7 — Retire the old model

Remove the `pairs` table and its API, the old import wizard, `resplit`, the TipTap per-pair editor, the
old artifact format and `services/importer.py` (unused since "Repo hygiene"); update `CLAUDE.md`, `README.md` and the e2e tests. Release v0.2.0.
