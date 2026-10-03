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
  undo/redo). **Stage 2 is complete** (2026-10-03). Since Stage 3's "PDF import in the app" the reference PDFs
  import through the form too (4.3 s, 1354 beads, 185 one-sided).
- Licensed AGPL-3.0-only (`LICENSE`).
- Python 3.14 only (`.python-version`, `requires-python`, launcher). Stage 0 is complete.
- `uv run pytest`: 364 passed (PyMuPDF is a core dependency), also on a fresh clone (tests read only committed
  synthetic fixtures; `-m library` tests run only where `library/contrefeu.*.pdf` exists, and assert counts only).
- PDF extraction (`extract.py`) works on the reference book (page numbers, chapter numbers, two-up spreads), and
  `POST /api/v2/books` accepts PDFs (extraction in a worker thread; an unreadable PDF is a 400).
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
`pymupdf` a core dependency (the `pdf` extra stays, redundant, for the launcher).

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
Not ready: after "Baseline local aligner" (the rule reads the alignment), scored by the exclusion F1 of "Gold v2".
Decided (user, 2026-10-04, replacing the 2026-10-03 "no automatic rule"): exclusion is part of the pipeline and is
scored with it. Order: **align first, then exclude** by a decision rule the runs of one-sided beads that "don't
look like part of the text" (title pages, colophon, table of contents, back-cover blurbs). A one-sided preface or
dedication that *is* text stays (SPEC §2). The rule marks blocks `front_matter`/`back_matter` (kinds the schema
already has) and excludes them, so `x`/Include still override it. What the user excluded by hand in the
reference book (measured 2026-10-04: source 28 paragraphs + 1 heading, target 17 + 1) is the target the rule is
scored against.
Earlier measurements (after "PDF blocks", counts only): FR ~25 short blocks on logical pages 3–6 before chapter 1
and ~6 on the last page; IT ~9 on pages 3–5 and ~7 on the last page.

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

### Whole-book gold
Status: dropped
Report: 2026-10-04 — blocked. `gold_export.py <id> all` done and tested (pytest 368 passed); export of the user's book OK (1222 beads, 0 one-sided, `library/contrefeu.gold.tsv`, gitignored). `gold_score.py` refuses: "doesn't match the current extraction", divergence at character 0 on both sides. Cause: the user excluded blocks the import includes (source: 28 paragraphs + 1 heading; target: 17 paragraphs + 1 heading; no text edits), so the gold's text is not a contiguous substring of a fresh import's (gold 196,294 / 201,813 non-space chars vs predicted 196,871 / 203,039). The metric's "gold is a substring" assumption fails whenever the translator's exclusions differ from the import's; needs a design decision.
Dropped 2026-10-04 (Pauli, with the user): superseded by "Gold v2"; its uncommitted `all` changes to
`gold_export.py`/`tests/test_gold.py` are replaced there.

### Gold v2
Status: done
Report: 2026-10-04 — `gold.py` rewritten (`Layer`, `read_layer`, JSON format 1, `score` with alignment and exclusion metrics per character); `gold_export.py <id>` writes `library/contrefeu.gold.json`; `gold_score.py` prints both scores; `tests/test_gold.py` rewritten (13 tests; v1's 22 removed); pytest 359 passed. User's book: 1222 beads, 0 one-sided, excluded segments source 152 / target 181. Score of the current pipeline: import 4.5 s, 1353 predicted beads; alignment P 0.840 R 0.903 F1 0.870 (boundaries 1221 gold / 1312 predicted); exclusion P 1.000 R 0.421 F1 0.592 (excluded chars source 1134 gold / 557 predicted, target 1979 / 753); longest missed runs: beads 1099–1164 (66), 740–751, 243–249, 45–49, 1059–1063.
**Done when:** `uv run pytest` passes with the rewritten `tests/test_gold.py`; `uv run python scripts/gold_export.py
046fb6f2-ba5d-4b6b-ac1a-d6a9caf9f38c` writes `library/contrefeu.gold.json` from the user's database; `uv run python
scripts/gold_score.py` runs on it, and the `Report:` gives its full output except the missed-run texts (metrics,
counts, timing only).

Design v2 under "Gold chapter" is binding. Start from the working tree (it holds the dropped task's uncommitted
`all` changes; replace them).
- `tradurre/services/gold.py`, rewritten:
  - `Layer` (dataclass): `source: list[tuple[str, int | None]]`, `target: …` (segment `original_text`, bead index
    or `None`), `reviewed: list[bool]` (per bead). `read_layer(conn, book_id) -> Layer` (ValueError "book … not
    found" as now). `layer_to_json(layer) -> dict` / `layer_from_json(dict) -> Layer`, JSON shape
    `{"format": 1, "source": [[text, bead], …], "target": […], "reviewed": […]}`.
  - `score(gold: Layer, predicted: Layer) -> Score`; `Score` dataclass: `alignment_precision`, `alignment_recall`,
    `alignment_f1`, `gold_boundaries`, `predicted_boundaries`, `exclusion_precision`, `exclusion_recall`,
    `exclusion_f1`, `excluded_chars: dict[str, tuple[int, int]]` (side → (gold, predicted)), and `missed:
    list[tuple[int, int]]` (runs of gold bead indices whose boundary is not predicted, longest first, as now).
  - Remove `chapter_beads`, `book_beads`, `boundaries`, `read_tsv`, `write_tsv` and the chapter regex.
- `scripts/gold_export.py <book id> [--db] [--out]` (default `library/contrefeu.gold.json`): no chapter argument;
  refuses while any bead is unreviewed (as now, "N of M beads of the book are not reviewed"); prints bead count,
  one-sided beads, excluded segments per side.
- `scripts/gold_score.py [--gold] [--source] [--target]` (default gold `library/contrefeu.gold.json`): builds as
  now, reads the prediction with `read_layer`, prints import time and bead counts (gold, predicted), the alignment
  P/R/F1 and boundary counts, the exclusion P/R/F1 and excluded characters per side (gold vs predicted), and the 5
  longest missed runs with the first source segment of the run's first gold bead, cut to 80 characters.
- `tests/test_gold.py`, rewritten (synthetic only; hand-built `Layer`s plus the docx fixture through the API):
  identical layers → all six metrics 1; merged beads → alignment recall < 1, precision 1, `missed` names it; gold
  excludes a block that the prediction keeps as a one-sided bead → exclusion recall < 1, alignment F1 1; prediction
  excludes a block the gold keeps → exclusion precision < 1; different segmentation or whitespace of the same text
  → 1; different text → ValueError naming the side; the empty-set conventions; `read_layer` on the docx book after
  excluding one block via `POST …/blocks/{id}/exclude` gives `None` for its segments; JSON round trip; the export
  script refuses an unreviewed book and writes the file once all are reviewed; the score script on the docx pair
  with a gold that has one block excluded → "alignment F1 1.000" and exclusion recall 0.
- Don't touch `build_book`, the extractor, the segmenter, the aligner, the API or the frontend.

### Stale frontend warning
Status: todo
**Done when:** `uv run pytest` passes with the new test; the `Report:` shows the startup line printed by `uv run
tradurre --no-browser` on this machine before and after `npm run build`.

Found 2026-10-03: the user opened the app on :8000 and got the **v0.1 screens** (old import wizard, sections,
"insert"/"remove"), because `tradurre/static/` was built before Stage 2 and the backend serves it in every mode,
`--dev` included (`app.py:46-58`); the new screens existed only on Vite's :5173. Nothing warned.
- `tradurre/__main__.py`: a function `_stale_build(frontend_src: Path, static: Path) -> bool`, true when
  `frontend_src` exists (a source checkout; an installed wheel has none) and its newest file under `src/`,
  `index.html`, `package.json` is newer than `static/index.html`. At startup, in **both** modes, if true print
  `warning: the built frontend in {static} is older than frontend/src; run 'npm run build' in frontend/ (or use
  the Vite dev server on http://localhost:5173 with --dev).` Keep the existing "no built frontend" warning.
- `tests/test_main.py` (new): `_stale_build` on a `tmp_path` tree: newer source → true; older source → false; no
  `frontend/` → false; no `static/index.html` → false (the other warning covers it).
- Nothing else changes.

### Import warnings and run metadata
Status: todo
**Done when:** `uv run pytest` passes (new migration and API tests); `npm run type-check` passes; `npm run
test:e2e` passes with the new test; the `Report:` quotes the stored stats JSON of a reference-book import (counts
and timings only, no text), taken from `test_import_through_the_api` run with `-s`.

SPEC §3.1.5 (warnings attached to the project, shown in the review view) and §4 "Debuggable" (runs record counts,
timings, warnings in the project). Today the import's warnings are only in the `POST` response
(`api/books.py:77-80`), shown once by `BookImport.vue`, then lost; nothing records counts or timings.

- `tradurre/db.py`: migration 5 `_m005_runs` (append to `MIGRATIONS`, `_run_script`):
  ```sql
  CREATE TABLE runs (
      id          INTEGER PRIMARY KEY,
      project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      kind        TEXT NOT NULL CHECK (kind IN ('import', 'align')),
      created_at  TEXT NOT NULL,
      app_version TEXT NOT NULL,
      stats       TEXT NOT NULL              -- JSON object
  );
  CREATE INDEX idx_runs_project ON runs(project_id, id);
  CREATE TABLE warnings (
      id      INTEGER PRIMARY KEY,
      run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
      side    TEXT CHECK (side IN ('source', 'target')),   -- NULL: the whole run
      message TEXT NOT NULL
  );
  ```
  `'align'` is reserved for Stage 5; only `'import'` is written now. Runs are not operations: not in the undo log.
- `tradurre/api/books.py`, `import_book`: time each side's `extract` (`time.perf_counter`, around the threadpool
  call) and `build_book`; in the same transaction as the build, insert one `import` run (`app_version` =
  `importlib.metadata.version("tradurre")`) and one `warnings` row per extraction warning, with its side and the
  message **without** the "source: " prefix (the `POST` response keeps its prefixed list unchanged). `stats`:
  ```json
  {"source": {"filename": "…", "format": "pdf", "bytes": 0, "extract_ms": 0, "pages": 0,
              "blocks": {"paragraph": 0, "page_number": 0, …}, "excluded_blocks": 0, "segments": 0},
   "target": {…}, "build_ms": 0, "beads": 0, "one_sided_beads": 0}
  ```
  `pages` = the highest block `page`, or `null` (txt/docx); `blocks` counts every kind present; `segments` counts
  the side's included segments; ms are integers. Counts come from the database after `build_book` (one query
  each), not from re-running segmentation.
- `tradurre/models.py` + new endpoint `GET /api/v2/books/{id}/runs` → `list[BookRun]`, newest first: `id`,
  `kind`, `created_at`, `app_version`, `stats` (`dict`), `warnings: list[{side: str | None, message: str}]`;
  404 for an unknown book (as `get_book`). `BookResponse` does not change.
- Frontend: `client.ts` `booksApi.getRuns(id)` and a `BookRun` type. `BookView.vue` fetches the runs once on
  mount (not after corrections) and shows, in the header next to "Show excluded", a button `data-testid="import-log"`
  labelled "Import log", or "Import log (N warnings)" / "(1 warning)" in amber when the latest import run has
  warnings. Clicking it toggles a panel under the header (`data-testid="import-log-panel"`): the warnings as a
  list (`data-testid="import-warning"` per item, "source: …"/"target: …"), then the latest import run's
  `created_at`, `app_version` and `stats` as indented JSON in a `<pre data-testid="import-stats">`. Keyboard
  navigation keeps working while it is open (the button is not a text entry).
- Tests:
  - `tests/test_books_api.py`: a txt import stores one run whose `stats` has the counts of the known fixture
    (`beads` 4, `one_sided_beads` 1, `source.blocks == {"paragraph": 3}`, `pages` null, `extract_ms` ≥ 0) and no
    warnings; the Latin-1 import stores one warning with side `target` and the unprefixed message; the PDF pair
    test also checks `pages` 3 and `blocks.page_number` 3 per side; unknown book → 404; a refused import (empty
    txt) writes no run.
  - `tests/test_bead_index.py:149` already checks `user_version == len(MIGRATIONS)`; add nothing there unless it
    fails.
  - `tests/test_library.py` `test_import_through_the_api`: also `GET …/runs` and print its `stats` (with `-s`);
    assert only that it has one run.
  - `frontend/e2e/books.spec.ts`: after a Latin-1 target import through the API, the book view's button reads
    "Import log (1 warning)", opening it shows the warning and the stats, and ↓ still moves the current bead.
- Don't change the aligner, the segmenter, the extractor or any correction endpoint.

### Gold chapter
Decided (user, 2026-10-03): made **in the app**, not in a spreadsheet. The translator imports the reference book,
corrects one chapter in the correction screen (moving sentences, splitting/joining segments; text edits only for
extraction damage) and marks its beads reviewed. Default chapter: the first of the body (chapter number "1"),
~200–400 sentences, with some 1:2/2:1 and unmatched material. This is the **user's** work, between "Gold export"
(the tool to save it) and the first scored aligner task; Braun's tasks below don't wait for it (they test on
synthetic books).

Design v1 (Pauli, 2026-10-03; tasks "Gold export" and "Gold score" below, done): one chapter as a TSV of beads,
located as a substring of a fresh import. **Broken by real use** (2026-10-04, see "Whole-book gold"): the user
corrected the whole book and excluded front/back matter by hand, so the gold's included text is no longer a
contiguous piece of a fresh import's. Replaced by design v2, binding for "Gold v2":
- **Whole book, whole text layer.** The gold is the user's corrected book: every segment of both editions in
  document order (block `ord`, segment `ord`), its `original_text` (text edits don't matter), and the 0-based index
  of its bead in bead order, or `null` if its block is excluded. The prediction has the same shape, read from a
  fresh import in a temporary database. Chapters and the TSV go away.
- **Same extraction or refuse.** Per side, the concatenation of all segments' text with whitespace removed must be
  identical in gold and prediction; otherwise refuse: "the gold doesn't match the current extraction ({side})".
  Known cost: an extractor change that alters text invalidates the gold. When that first happens, map offsets with
  a diff instead of refusing (a task then, not now).
- **Two scores, per character** (non-whitespace characters of each side, now in one-to-one correspondence):
  - *Exclusion*: positives are excluded characters. Precision = excluded in both / excluded in prediction, recall
    = excluded in both / excluded in gold, both sides pooled.
  - *Alignment*, on the characters included in **both** gold and prediction ("common"): a bead's boundary is
    (number of common source characters in it and all beads before, same for target). Gold and predicted
    boundary sets, minus (0, 0) and the end (all common source, all common target). Precision, recall, F1. A bead
    made only of characters the other side excluded collapses onto its neighbour's boundary, so an exclusion
    error is charged to the exclusion score, not twice.
  - Empty-set convention for both: precision = 1 if the predicted set and the gold set are both empty, 0 if only
    the predicted one is; same for recall with the roles swapped; F1 = 0 when precision + recall = 0.
- Gold beads must all be reviewed (export refuses otherwise). The file is `library/contrefeu.gold.json`
  (gitignored, copyrighted: never committed).

#### Gold export
Status: done
Report: 2026-10-03 — `tradurre/services/gold.py` (`chapter_beads`, `write_tsv`, `read_tsv`), `scripts/gold_export.py` (refuses unreviewed chapters, missing database); `tests/test_gold.py` 6 tests on a docx book; pytest 274 passed, `--help` prints usage.
**Done when:** `uv run pytest` passes with the new `tests/test_gold.py` export tests; `uv run python
scripts/gold_export.py --help` prints usage.

- New module `tradurre/services/gold.py` (no FastAPI imports):
  - `chapter_beads(conn, book_id, chapter: int) -> list[tuple[str, str, bool]]`: the chapter's beads as
    (source cell, target cell, reviewed), per the design above. Raises `ValueError` with a clear message for an
    unknown book or a chapter number that doesn't exist ("chapter 7 not found; the book has 5").
  - `write_tsv(path, cells: list[tuple[str, str]])` and `read_tsv(path) -> list[tuple[str, str]]` (exact round
    trip, including empty cells).
- `scripts/gold_export.py <book id> <chapter> [--db PATH] [--out PATH]` (argparse; `--db` defaults to
  `tradurre.config.DB_PATH`, `--out` to `library/contrefeu.gold.tsv`; the book id is the one in the book's URL).
  Refuses (exit 1, nothing written) if any bead of the chapter is unreviewed, naming how many; otherwise writes
  the file and prints the bead count and how many beads are one-sided.
- `tests/test_gold.py`: build a small book through `POST /api/v2/books` on a temporary database (fixtures as in
  `tests/test_books_api.py`) from .docx files (txt never yields `heading` blocks) with "Heading 1" paragraphs
  "1" and "2", as `_docx` in `test_books_api.py` builds them. Cover: chapter 1 and the last chapter boundaries; a text edit doesn't
  change the cell (original text); a split segment gives the same cell as before; unknown chapter → `ValueError`;
  TSV round trip with an empty cell; the script's refusal on an unreviewed bead (call its `main(argv)`).
- Don't touch the app, the API or the schema.

#### Gold score
Status: done
Report: 2026-10-03 — `gold.py`: `book_beads` (`chapter_beads` now slices it), `boundaries`, `score`/`Score`; `scripts/gold_score.py` builds the pair as the import does in a temporary database; 12 new tests in `tests/test_gold.py`; pytest 286 passed, `--help` prints usage. Not run on a real gold: `library/contrefeu.gold.tsv` doesn't exist yet. Sanity check on the reference PDFs with a 30-bead slice of the book itself as gold (scratchpad, deleted): F1 1.000, import 4.4 s, 1354 beads.
**Done when:** `uv run pytest` passes with the new score tests in `tests/test_gold.py`; `uv run python
scripts/gold_score.py --help` prints usage; the `Report:` says whether the score could run on this machine (only
once `library/contrefeu.gold.tsv` exists; if it doesn't yet, say so, it's not a failure).

- `tradurre/services/gold.py`:
  - `book_beads(conn, book_id) -> list[tuple[str, str, bool]]`: all beads' (source cell, target cell, reviewed);
    `chapter_beads` is rewritten to slice its result (same behaviour; the export tests stay unchanged and green).
  - `boundaries(cells: list[tuple[str, str]]) -> tuple[str, str, list[tuple[int, int]]]`: the two side texts and
    the boundary of every bead, in order, per the metric in the design above.
  - `score(gold, predicted) -> Score` (both `list[tuple[str, str]]`); `Score` is a dataclass: `precision`,
    `recall`, `f1`, `gold_count`, `predicted_count` (the set sizes) and `missed: list[tuple[int, int]]`, the runs
    of consecutive gold bead indices (first, last; 0-based) whose boundary isn't predicted, longest first. Raises
    `ValueError` with the "doesn't match" message.
- `scripts/gold_score.py [--gold PATH] [--source PATH] [--target PATH]` (argparse; defaults
  `library/contrefeu.gold.tsv`, `library/contrefeu.fr.pdf`, `library/contrefeu.it.pdf`; a missing file → exit 1
  with its name). It builds the book exactly as the import does, without the server: `extract` both files, a
  temporary database file (`tempfile.TemporaryDirectory`), `get_connection` + `init_db`, then inside
  `transaction(conn)` insert the `projects` row and call `build_book` (as `api/books.py:69-76`). It prints the
  wall time of extraction + build, precision/recall/F1 (3 decimals), the two counts, and the 5 longest missed
  runs as `beads i–j` with the first gold line of the run cut to 80 characters (terminal only, never a file).
  `main(argv) -> int` like `gold_export.py`.
- Tests (synthetic, no library; build cells by hand, no database needed except for `book_beads`):
  identical lists → 1/1/1; two gold beads merged in the prediction → recall < 1, precision 1, and `missed` names
  that bead; the gold located inside a longer prediction (beads before and after) → 1/1/1; the same alignment
  with a cell's text cut at a different place inside one bead, or different whitespace → 1/1/1; a one-sided gold
  bead (empty target) predicted right → 1/1/1; a gold not in the prediction → `ValueError`; `book_beads` on the
  docx fixture returns all 7 beads and `chapter_beads` still passes its tests. One script test: `main` with
  `--source`/`--target` pointing to the existing small docx files (written to `tmp_path`) and a gold TSV written
  from their chapter → exit 0 and "F1 1.000" in the output.
- This is the measuring stick for "Segmentation" and "Baseline local aligner": from then on their `Report:` lines
  quote `gold_score.py`'s F1. Don't touch the app, the API, the schema, or the export script.

### Segmentation
Status: done
Report: 2026-10-03 — `services/segment.py` (one regex with closers/openers and an exact `isupper` class, case-sensitive abbreviations, token = letters and inner dots so `l'Avv.` holds), used by `build_book`; `tests/test_segment.py` 38 cases + invariant; library invariant test. Reference book, old → new: FR 1258 → 1260 segments, >400 chars 47 → 45, lowercase starts 1 → 1, abbreviation ends 4 → 0; IT 1265 → 1266, 46 → 45, 10 → 10, 4 → 0 (the long ones have no internal terminator: real long sentences). Import: 1353 beads (was 1354), 180 one-sided (was 185). No gold yet. pytest 364 passed, `-m library` 8 passed, e2e 28 passed.
**Done when:** `uv run pytest` passes with the new `tests/test_segment.py`; `uv run pytest -m library` passes
with the new library test; the `Report:` gives, per side of the reference book, the segment count and the
diagnostic counts below **before and after** the change, the bead and one-sided bead counts from
`test_import_through_the_api` (run with `-s`), and the F1 of `scripts/gold_score.py` if
`library/contrefeu.gold.tsv` exists (otherwise "no gold yet").

SPEC §3.1.3: segmentation handles French and Italian conventions (abbreviations, dialogue dashes and guillemets,
ellipses, quotations ending in punctuation). Today `build_book` uses v0.1's `aligner.split_sentences`
(`aligner.py:26,275`): a split only after `.?!` + whitespace + `[A-ZÀ-ÝÆŒ]`, so it misses `…`, `?`/`!` followed
by a closing `»`, a dialogue dash, an opening `«`, and splits after "M." or "Sig.".

- New module `tradurre/services/segment.py`, `split_sentences(text: str) -> list[str]`. A boundary is, in order:
  1. a terminator: one or more of `.` `?` `!` `…` (so `...`, `?!`, `!…` count once);
  2. optional closers: zero or more of `»` `”` `"` `’` `)` `]`, each optionally preceded by whitespace (so
     `! »` and `."` end the sentence *after* the closer);
  3. whitespace (at least one character; Python's `\s` covers U+00A0 and U+202F, which French uses before
     `?!»:;`);
  4. the next sentence's start: optional openers (`«` `“` `"` `(` `—` `–` or a `-` followed by whitespace,
     with whitespace between), then a character for which `str.isupper()` is true. Digits and lowercase never
     start a sentence (so `« Viens ! » dit-il.` and `Que faire ? se demanda-t-il.` stay whole).
  
  No boundary after an abbreviation: the token before the terminator (letters and inner dots, from the last
  whitespace or opener) is, **case-sensitively**, one of `M MM Mme Mlle Mgr Dr Pr St Ste Me Sig Sigg Sig.ra
  Sig.na Dott Dott.ssa Prof Prof.ssa Avv Ing Mons SS cf p pp vol chap fig éd` (the dot that follows it being the
  terminator), or a single uppercase letter (an initial: `J. Dupont`). Case matters: Italian `a me.` ends a
  sentence, `Me` (Maître) doesn't. `etc.` and `ecc.` are **not**
  abbreviations here: they end sentences often enough, and a wrong split is one `j` away.
  Segments are the text between boundaries, stripped; empty ones dropped. Invariant, tested: the segments, with
  all whitespace removed and concatenated, equal the input with all whitespace removed.
- `tradurre/services/build.py`: `_blocks` uses `segment.split_sentences` (keep the `or [block.text]` fallback);
  update the module docstring. `aligner.split_sentences` and its callers in the old API stay untouched (Stage 7
  removes them).
- `tests/test_segment.py`, one test per rule with French and Italian examples written for the test (never text
  from the reference book): `.`/`?`/`!` + capital; `…` and `...` + capital vs + lowercase; `? »` / `! »` then a
  capital (boundary after `»`) vs then `dit-il`; `."` / `.”`; NBSP and U+202F before `?` and `»`; dialogue
  `— Tu viens ? — Non.` (two segments); an opening `« ` after a period; `(` after a period; accented capitals
  (`À`, `É`); each abbreviation group (French titles, Italian titles, `p.`/`cf.`, an initial) not splitting;
  `etc.` + capital splitting; Italian `a me. Poi` splitting; digits after a period not splitting; the whitespace invariant over all the test
  inputs (a parametrized check).
- `tests/test_library.py`: one test, per side, that the invariant holds on every included block of the reference
  book (counts only in the failure message: how many blocks break it).
- Diagnostics for the `Report:` (a throwaway script in the scratchpad, never committed, printing counts only),
  per side, with the old and the new splitter on the reference book's included blocks: segment count; segments
  over 400 characters (likely missed boundaries); segments starting with a lowercase letter (likely wrong
  splits); segments whose last token is in the abbreviation list (wrong splits the old splitter made).
- Don't touch the aligner (`align`, `find_anchors`), the extractor, the API or the frontend.

### Baseline local aligner
Not ready: waits for "Gold v2" and the baseline alignment F1 of the interim aligner it reports, from which the
user and /pauli agree the target alignment F1.
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
