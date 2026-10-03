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
- Licensed AGPL-3.0-only (`LICENSE`).
- Python 3.14 only (`.python-version`, `requires-python`, launcher). Stage 0 is complete.
- `uv run pytest`: 206 passed with PyMuPDF installed (205 + 1 skipped without), also on a fresh clone (tests read
  only committed synthetic fixtures).
- `uv.lock` is tracked; `pytest`/`httpx` are in the `dev` group. The Windows launcher's `uv tool install` resolves
  from PyPI and never reads the lock.
- `npm run type-check` passes; releases build with `npm run build`. Playwright's Chromium is not installed on the
  dev machine, so `npm run test:e2e` and browser checks can't run here until `npx playwright install chromium`.
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

Decided (user, 2026-10-03): the translator gets a usable end-to-end path **before** extraction and alignment are
polished. This stage imports a .txt/.docx pair into the new model with the v0.1 sentence splitter and anchor
aligner, and opens it in a plain correction screen that uses the Stage 1 operations. Stage 3 then improves what
feeds it (PDF, segmentation, aligner), measured against a gold chapter made **in the app**; Stage 4 turns the
screen into the full review view of SPEC §3.3.

Coexistence until Stage 7: the new model gets its own API under `/api/v2` (new module `tradurre/api/books.py`)
and its own views; `/api/v1`, the old wizard and the pairs editor stay as they are. A project is a "book" (new
model) iff it has rows in `documents`.

### Structured extraction
Files in, kinded blocks out (SPEC §3.1 step 2). Design (/pauli, 2026-10-03), shared by the txt/docx task here and
the PDF tasks in Stage 3:
- New module `tradurre/services/extract.py`. `doc_adapter.py` is **not** changed: the v0.1 import keeps using it
  until Stage 7. Reuse its `normalize_ocr_artifacts` and `glyph_resolver` by importing them.
- `@dataclass ExtractedBlock(kind: str, text: str, page: int | None = None)` (`kind` from the `blocks` schema
  list; `page` = 1-based logical page, PDF only) and `@dataclass Extraction(blocks: list[ExtractedBlock],
  warnings: list[str])`. `EXCLUDED_KINDS = {"running_head", "page_number", "footnote", "front_matter",
  "back_matter"}`: the import (later step) sets `excluded` from it. One block = one paragraph-like unit; splitting
  into sentences is the next step's job.
- `extract(filename: str, content: bytes) -> Extraction` dispatches on extension like `doc_adapter`.
- PDF facts behind the rules below are in "Reference book" plus these (measured 2026-10-03): FR body text
  11.9 pt, body lines start at x≈82–84 with first-line indent x≈96 (+1.1 em), chapter numbers are lone 14 pt
  lines; IT body 12.5 pt, columns at x≈48 / 434 with indent +14 pt.
- PDF tests build small PDFs **in the test** with PyMuPDF (`page.insert_text`), so no binary fixtures and no
  copyrighted text. That needs PyMuPDF in the dev environment (first PDF task).

#### Text and docx extraction
Status: done
**Done when:** `tests/test_extract.py` passes; `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — `tradurre/services/extract.py` (`ExtractedBlock`, `Extraction`, `EXCLUDED_KINDS`, `extract` for txt/docx; pdf → `NotImplementedError`); `tests/test_extract.py` 8 passed; pytest 214 passed (206 before).

- `tradurre/services/extract.py` with `ExtractedBlock`, `Extraction`, `EXCLUDED_KINDS`, `extract` as in the
  design; `.pdf` raises `NotImplementedError` for now (next tasks), other extensions `ValueError`.
- `.txt` (UTF-8, latin-1 fallback with a warning in `warnings`): if the text has a blank line anywhere, blocks are
  the blank-line-separated chunks, each with its internal line breaks joined by one space; otherwise every
  non-empty line is a block. Kind `paragraph`; text stripped, inner whitespace runs collapsed to one space;
  `normalize_ocr_artifacts` applied.
- `.docx`: one block per non-empty paragraph; kind `heading` if the paragraph's style name starts with
  `"Heading"` or `"Title"` (python-docx's built-in names), else `paragraph`.
- `tests/test_extract.py`: txt with blank lines (wrapped lines joined), txt without blank lines (one block per
  line), latin-1 fallback warns, docx with a heading and two paragraphs (built with python-docx in the test),
  unknown extension → `ValueError`.

### Interim build
Status: todo
**Done when:** `tests/test_build.py` passes; `uv run pytest` otherwise unchanged.

New module `tradurre/services/build.py`, the bridge from an `Extraction` pair to a project in the new model,
using v0.1's algorithms unchanged (Stage 3 replaces them behind the same function):
- `build_book(conn, project_id, source: tuple[str, str, Extraction], target: tuple[str, str, Extraction]) -> None`
  (each tuple: filename, format, extraction), called inside the caller's `transaction(conn)`; the project row
  exists already. Not recorded in the operation history (the layer builder isn't).
- Blocks: one `NewBlock` per `ExtractedBlock`, same kind and page, `excluded = kind in EXCLUDED_KINDS`, segments
  = `aligner.split_sentences(text)`, or `[text]` if that returns nothing.
- Alignment: over the **included** segments of each side in document order, `aligner.find_anchors` +
  `aligner.align` on their texts. `align` returns string pairs in order, each unit exactly once plus `""`
  padding, so walk the pairs consuming segment ids sequentially per side (a non-empty string takes the next id;
  assert it equals that segment's text). Each pair becomes one bead: method `anchor`, confidence 0.5 if both sides
  are non-empty, else 0.2. `append_beads` in order.
- Tests: two small extractions (one with an excluded `footnote` block) → `check_project` returns `[]`, bead count
  and texts as expected, a 1:0 bead when the source has an extra sentence, excluded segments have no bead; a
  block whose text has no sentence boundary gives one segment.

### Book API: import and read
Status: todo
**Done when:** `tests/test_books_api.py` passes; `uv run pytest` otherwise unchanged.

`tradurre/api/books.py`, router registered in `app.py` with prefix `/api/v2`; models in `models.py` (prefix
`Book…`):
- `POST /books` (multipart: `source`, `target` files, `title`, `source_lang` default `fr`, `target_lang`
  default `it`): `extract` both, then in one `transaction` insert the `projects` row (same id/timestamp style as
  `api/projects.py`) and `build_book`. `.pdf` → 415 with a message that PDF import comes later; extraction
  `ValueError` → 400. Returns `{id, title, bead_count, warnings}` (warnings are not stored yet: see Stage 3).
- `GET /books`: the projects that have documents, with title, languages, bead count, reviewed count.
- `GET /books/{id}`: title, languages, and every bead in order with `{id, confidence, method, reviewed, source,
  target}`, where each side is a list of `{segment_id, block_id, text}`; plus the excluded blocks with their
  segments and the id of the bead they sit after (null at the start), so the client can reveal them in place.
- `GET /books/{id}/check`: `check_project`'s list (the debug endpoint of SPEC §4).
- `GET /api/v1/projects` is not changed; the old list keeps showing every project.
- Tests: import a txt pair and a docx pair through `TestClient`; read it back; 404 on an unknown id; `.pdf` → 415;
  check returns `[]`.

### Book API: corrections
Not ready (/pauli details it when the previous task is done): one `POST` per domain operation under
`/books/{id}/…` (move, merge, split bead, split/join segment, edit text, exclude/include, reviewed incl. skim,
undo, redo), each in `transaction`, `DomainError` → 409 with its message, returning the same shape as
`GET /books/{id}` (whole-book refetch is fine at this scale; Stage 4 makes it incremental).

### Correction screen
Not ready: route `/book/:id`, `BookView.vue`, plain text, no virtualization, no TipTap: beads as rows (source
left, target right), a current bead moved with the keyboard, every correction of the previous step on a
shortcut and a button, undo/redo, reviewed toggle and progress, excluded blocks revealable. `ProjectList` opens
books here and offers "Import a book (txt/docx)" next to the old wizard. Probably two tasks (read-only list with
navigation; corrections).

---

## Stage 3 — Better import

**Decided (user, 2026-10-03): tradurre is AGPL-3.0-only** (`LICENSE`, `pyproject.toml`), so PyMuPDF (AGPL-3.0)
stays the PDF library. The launcher already installs `tradurre[pdf]` (`EXTRAS=pdf`); "PDF import in the app" moves
`pymupdf` from the `pdf` extra into the core dependencies. Until then it is a dev dependency so tests run.

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
Status: todo
**Done when:** `tests/test_extract_pdf.py` passes; `uv run pytest` otherwise unchanged.

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
Status: todo
**Done when:** `tests/test_extract_pdf.py` passes with the cases below; `uv run pytest` otherwise unchanged.

`extract` for `.pdf`, from `_pdf_lines`:
- `body_size` = the span size covering the most characters in the document (rounded to 0.1 pt). Per logical page,
  `left` = the most common `round(x0)` among lines whose `size` is within 0.5 pt of `body_size`.
- Classification, per line, in this order:
  - `page_number`: text matches `^\s*([0-9]+|[ivxlcdm]+)\s*$` (case-insensitive) and the line lies in the top or
    bottom 12% of the logical page height;
  - `running_head`: in the top 12%, and its text with digits removed, casefolded and stripped is non-empty and
    occurs (so normalized) in the top 12% of at least 3 logical pages;
  - `heading`: `size >= body_size * 1.1`;
  - `footnote`: `size <= body_size * 0.9` and in the bottom 40% of the page;
  - otherwise body.
- Assembly: consecutive lines of the same kind form one block, except that body (`paragraph`) lines also start a
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
  `page_number` block; a soft hyphen and a hard hyphen at line ends; a repeated top line on 3 pages →
  `running_head`, on 2 → not; a larger line → `heading`; small text at the bottom → `footnote`; a two-up document
  reads left page then right page.

#### Front and back matter
Not ready: half title, "Du même auteur", colophon/ISBN, series blurb → `front_matter`/`back_matter`. Planned
after "PDF blocks", with `tests/test_library.py` on the reference book, so the rule is fitted to a real book
rather than guessed.

### PDF import in the app
Not ready: `POST /books` accepts `.pdf`; `pymupdf` becomes a core dependency (see the decision above).

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

---

## Stage 4 — Review view

Decided (user, 2026-10-03): the review screen permits **cut/copy/paste between rows** ("the user is king and
responsible"). A cut at one row's edge pasted at the adjacent edge of the neighbouring row leaves the edition's
text unchanged and is recorded as a bead-boundary move; any other paste is a text edit (original text kept,
undoable). SPEC §3.3 gets a line for it when this stage is planned (wording to agree with the user then).

The correction screen of Stage 2 grows into the main screen of SPEC §3.3: virtualized bead list, confidence
and unmatched highlighting, next-problem navigation, skim-review pass, cut/copy/paste between rows, re-align
range, incremental updates instead of whole-book refetch. Plain text editing; TipTap is not used here.

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

Search UI on the new index with context expansion and jump-to-bead (SPEC §3.4). Exports: TMX/TSV corpus,
per-edition .txt/.docx, project bundle as backup (SPEC §3.5).

---

## Stage 7 — Retire the old model

Remove the `pairs` table and its API, the old import wizard, `resplit`, the TipTap per-pair editor, the
old artifact format and `services/importer.py` (unused since "Repo hygiene"); update `CLAUDE.md`, `README.md` and the e2e tests. Release v0.2.0.
