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
  navigates a book and makes the bead corrections with keys and buttons, with undo/redo; segment editing is next,
  then Stage 3.
- Licensed AGPL-3.0-only (`LICENSE`).
- Python 3.14 only (`.python-version`, `requires-python`, launcher). Stage 0 is complete.
- `uv run pytest`: 249 passed with PyMuPDF installed (248 + 1 skipped without), also on a fresh clone (tests read
  only committed synthetic fixtures).
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
Verified (/pauli, 2026-10-03, `56c180d`): matches the task; pytest 214 passed. Three edge cases found in the rules as
I wrote them, fixed by "Extraction fixes" below.

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

#### Extraction fixes
Status: done
**Done when:** `tests/test_extract.py` passes with the three new cases below; `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — `utf-8-sig` decoding, chunk mode only for a blank line between non-blank lines, docx text through `_clean`; `tests/test_extract.py` 11 passed; pytest 217 passed (214 before).
Verified (/pauli, 2026-10-03, `551ab56`): matches the task; pytest 217 passed.

Found by /pauli reviewing `56c180d` (each reproduced against `extract`):
- **BOM.** A UTF-8 file with a byte-order mark (Notepad's "UTF-8 with BOM", Word's plain-text export) keeps
  `\ufeff` at the start of the first block. Decode with `utf-8-sig` (the Latin-1 fallback is unchanged).
- **Trailing blank lines.** `"Une.\nDeux.\n\n"` gives one block `"Une. Deux."`: a blank line at the start or end
  of the file switches to chunk mode. Chunk mode applies only if a blank line lies **between two non-blank
  lines**.
- **docx line breaks and tabs.** A paragraph with a manual line break and a tab gives `"Vers un\n\tvers deux"`.
  docx block text goes through the same `_clean` as txt (so `"Vers un vers deux"`).
- Tests: BOM stripped; trailing blank lines → one block per line; a docx paragraph with `add_break()` and a tab
  is cleaned.

### Interim build
Status: done
**Done when:** `tests/test_build.py` passes; `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — `tradurre/services/build.py` (`build_book`: blocks via `split_sentences`, excluded per `EXCLUDED_KINDS`, v0.1 anchor alignment mapped to segment ids, beads 0.5/0.2 `anchor`); `tests/test_build.py` 3 passed; pytest 220 passed (217 before).
Verified (/pauli, 2026-10-03, `43b5a87`): matches the task; pytest 220 passed. The bare `assert` in the mapping is
acceptable (the app never runs with `-O`); confidence is flat (0.5/0.2) until "Baseline local aligner".

New module `tradurre/services/build.py`, the bridge from an `Extraction` pair to a project in the new model,
using v0.1's algorithms unchanged (Stage 3 replaces them behind the same function):
- `build_book(conn, project_id, source: tuple[str, str, Extraction], target: tuple[str, str, Extraction]) -> None`
  (each tuple: filename, format, extraction), called inside the caller's `transaction(conn)`; the project row
  exists already. Not recorded in the operation history (the layer builder isn't).
- Blocks: one `NewBlock` per `ExtractedBlock`, same kind and page, `excluded = kind in EXCLUDED_KINDS`, segments
  = `aligner.split_sentences(text)`, or `[text]` if that returns nothing.
- Alignment (assumptions checked by /pauli on 300 random cases with repeated names and identical texts: `align`
  returns every unit once, in order, never an all-empty pair; 4,000 × 4,200 sentences in 0.16 s): over the
  **included** segments of each side in document order, `aligner.find_anchors` +
  `aligner.align` on their texts. `align` returns string pairs in order, each unit exactly once plus `""`
  padding, so walk the pairs consuming segment ids sequentially per side (a non-empty string takes the next id;
  assert it equals that segment's text). Each pair becomes one bead: method `anchor`, confidence 0.5 if both sides
  are non-empty, else 0.2. `append_beads` in order.
- Tests: two small extractions (one with an excluded `footnote` block) → `check_project` returns `[]`, bead count
  and texts as expected, a 1:0 bead when the source has an extra sentence, excluded segments have no bead; a
  block whose text has no sentence boundary gives one segment.

### Book API: import and read
Status: done
**Done when:** `tests/test_books_api.py` passes; `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — `tradurre/api/books.py` (`POST /books`, `GET /books`, `GET /books/{id}`, `GET /books/{id}/check` under `/api/v2`), `Book…` models in `models.py`, router in `app.py`; `tests/test_books_api.py` 12 passed; pytest 232 passed (220 before).
Verified (/pauli, 2026-10-03, `08c257a`): matches the task; pytest 232 passed. Uploads are read whole with no size cap:
acceptable for a local single-user app.

`tradurre/api/books.py`, router registered in `app.py` with prefix `/api/v2`; response models in `models.py`
(prefix `Book…`). Handlers take `db: sqlite3.Connection = Depends(get_db)` like the v1 routers, but write through
`with transaction(db):` (`tradurre.domain.history`), not `with db:`, because the domain needs deferred foreign
keys.
- `POST /books` (multipart: `source`, `target` as `UploadFile`; form fields `title` (optional: defaults to the
  source filename without extension, SPEC §3.1.1 "pre-filled"), `source_lang` default `fr`, `target_lang`
  default `it`), `async def` like `api/import_.py`:
  - format = the lowercased extension without the dot. `extract` both files first; `NotImplementedError` (PDF)
    → 415 "PDF import is not available yet"; `ValueError` → 400 with its message; an extraction with no block
    whose kind is outside `EXCLUDED_KINDS` → 400 "no text found in <filename>". All checked **before** anything
    is written.
  - Then in one `transaction`: insert the `projects` row (`uuid4` id, `created_at`/`updated_at` as `_now()` in
    `api/projects.py`) and `build_book`.
  - 201, returns `{id, title, bead_count, warnings}`; `warnings` = both extractions' warnings, each prefixed with
    `"source: "` / `"target: "` (not stored yet: see Stage 3).
- `GET /books`: the projects that have documents, newest `updated_at` first, each `{id, title, source_lang,
  target_lang, bead_count, reviewed_count}`.
- `GET /books/{id}` (404 if the project doesn't exist or has no documents): `{id, title, source_lang,
  target_lang, beads, excluded}`.
  - `beads`: every bead in `ord` order, `{id, confidence, method, reviewed, source, target}`; each side a list of
    `{segment_id, block_id, block_kind, text}` in document order (`block_kind` so the client can show headings and
    paragraph breaks, SPEC §3.3).
  - `excluded`: the excluded blocks of both documents, `{block_id, side, kind, page, segments: [{segment_id,
    text}], after_bead_id}`, where `after_bead_id` is the bead of the last included segment before the block in
    the same document (null if none), so the client can reveal them in place.
- `GET /books/{id}/check`: `check_project`'s list (the debug endpoint of SPEC §4); 404 as above.
- Nothing under `/api/v1` changes. (A book also shows up in the old project list with 0 pairs until "Correction
  screen" routes it; deleting it there cascades correctly through `ON DELETE CASCADE` and the index triggers.)
- `tests/test_books_api.py`, with a `client` fixture like `tests/test_pairs_api.py` (monkeypatched `DB_PATH`):
  import a txt pair and read it back (bead texts and order); import a docx pair with a heading (`block_kind`
  `heading` in the read); title defaults to the source stem; `GET /books` lists only books, with counts; an
  excluded block's `after_bead_id` (build it by importing, then `exclude_block` on a middle block through the
  domain); `.pdf` → 415 and an empty `.txt` → 400, each leaving `GET /books` empty; unknown id → 404 on both GETs;
  check returns `[]`.

### Book API: corrections
Status: done
**Done when:** `tests/test_books_corrections_api.py` passes; `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — 12 correction endpoints in `api/books.py` via one `_correct` helper (transaction, `updated_at`, DomainError → 409, ValueError → 400), `_read_book` shared with `GET`, `can_undo`/`can_redo`, `Book…Request` models; `tests/test_books_corrections_api.py` 15 passed; pytest 247 passed (232 before).
Verified (/pauli, 2026-10-03, `05ddd35`): matches the task; pytest 247 passed. A no-op success also bumps
`updated_at`: harmless, left as is.

Every SPEC §3.3 correction over HTTP, in `tradurre/api/books.py`; request models in `models.py` (`Book…Request`).
The domain functions do all the work and all the checking; the endpoints only translate.
- **Pattern, every endpoint:** `POST`, 404 if the book doesn't exist (`_book_row`), then one
  `with transaction(db):` that calls the domain function and sets the project's `updated_at` to `_now()`;
  `DomainError` → 409 with its message (this includes ids that belong to another book or don't exist: the domain
  checks them), `ValueError` → 400. Success → 200 with the whole book, the same body as `GET /books/{id}` (factor
  the read into a helper `_read_book(db, book_id)`; a 2,000-bead book is a few hundred kB, fine until Stage 4).
- **Endpoints** (paths under `/api/v2/books/{book_id}`, domain function in brackets):
  - `beads/{bead_id}/move`, body `{side: "source"|"target", to: "previous"|"next"}` → `move_first_to_previous`
    if `to` is previous, else `move_last_to_next`;
  - `beads/{bead_id}/merge-next` (`merge_with_next`);
  - `beads/{bead_id}/split`, body `{source_at: int | null, target_at: int | null}` (`split_bead`; segment ids
    where the new bead starts);
  - `reviewed`, body `{bead_ids: list[int], reviewed: bool, skim: bool = false}` (`set_reviewed`);
  - `segments/{segment_id}/edit`, body `{text: str}` (`edit_text`);
  - `segments/{segment_id}/split`, body `{offset: int}` (`split_segment`; offset in the segment's current text);
  - `segments/{segment_id}/join-next` (`join_with_next`);
  - `blocks/{block_id}/exclude`, `blocks/{block_id}/include` (`exclude_block`, `include_block`);
  - `undo`, `redo` (`undo`/`redo` from `history`; when they return None → 409 "Nothing to undo" / "Nothing to
    redo", and `updated_at` is not touched).
- **Undo availability:** add `can_undo: bool` and `can_redo: bool` to `BookResponse` (so also to `GET
  /books/{id}`): whether the project has an operation with `undone = 0` / `undone = 1`. The screen greys its
  buttons with them.
- No-op successes (an edit to the same text, reviewed marks already set) return 200 with the unchanged book.
- `tests/test_books_corrections_api.py` (import a small txt pair through the API, as in `test_books_api.py`, then
  act through the API only): each endpoint once with the effect visible in the returned book; after each, `GET
  /books/{id}/check` is `[]`; a refused correction (e.g. `merge-next` on the last bead, `edit` with empty text) →
  409 and an unchanged book; a bead id from another book → 409; unknown book → 404; `skim: true` with
  `reviewed: false` → 400; `undo` then `redo` round-trips an edit; `undo` on a fresh book → 409 and `can_undo`
  false; `updated_at` moves after a correction (via `GET /books` order with two books).

### Correction screen
The first screen the translator uses on the new model (SPEC §3.3, minus what Stage 4 adds: virtualization,
confidence highlighting, skim pass, cut/paste, re-align range). Plain text, no TipTap, Tailwind like the other
views. Shared design, decided here so the tasks don't each reinvent it:
- **Client:** in `frontend/src/api/client.ts`, a second fetch wrapper for `/api/v2` (`booksApi`) whose errors are
  `Error(detail)` with the server's `detail` message, so 409 messages from the domain reach the translator;
  TypeScript types mirroring the `Book…` models in `tradurre/models.py`. `/api/v1` code is not touched.
- **Layout (`frontend/src/views/BookView.vue`, route `/book/:id`, name `book`):** one scrolling column of rows,
  one row per bead, source cell left, target cell right (a CSS grid with two equal columns). In a cell, segments
  run on as text; a new block starts on a new line, and a `heading` block is bold. A one-sided bead has an empty
  cell with a light grey background. A reviewed bead shows a green left border. A header bar shows title,
  "reviewed X / N", Undo/Redo buttons (disabled from `can_undo`/`can_redo`), the correction buttons for the
  current bead (see "Segment editing", decision) and a "Show excluded" toggle. Rows never change height when the
  selection moves.
- **Selection:** a current bead (outlined), a current side (`source`|`target`, its cell tinted) and a current
  segment (underlined) inside the current cell. Clicking a segment selects all three. Keys (ignored while a text
  field has focus): ↑/↓ previous/next bead (current segment = first of the cell), ←/→ side, Tab/Shift+Tab next/
  previous segment within the cell. The current row is kept visible (`scrollIntoView({block: "nearest"})`).
- **After every correction** the returned book replaces the local one; the current bead stays if it still exists,
  else the bead now at the same index (clamped). An error shows its message in a status line under the header
  for 5 s.
- **Tests:** Playwright specs in `frontend/e2e/`, against a throwaway backend (next task). Each spec imports its
  own book through `POST /api/v2/books`.

#### E2E harness
Status: done
**Done when:** `npm run test:e2e` (in `frontend/`) runs `frontend/e2e/books.spec.ts` green against a backend on a
throwaway database, with the user's `~/.tradurre/tradurre.db` untouched (its mtime unchanged); `uv run pytest`
unchanged; `npm run type-check` passes.
Report: 2026-10-03 — `TRADURRE_DB` in `config.py` (+ `tests/test_config.py`), Vite proxy from `TRADURRE_API`, Playwright on two throwaway servers (:8001 `.e2e.db`, Vite :5174) with `channel: 'chromium'`, `books.spec.ts` smoke test, scroll-sync spec made relative (passes); Chromium installed with `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64`; e2e 2 passed, `~/.tradurre/tradurre.db` mtime unchanged; pytest 249 passed (247 before); type-check passes.
Verified (/pauli, 2026-10-03, `8496545`): reran pytest (249 passed) and `npm run test:e2e` (2 passed); the user's
database mtime is unchanged. Both environment workarounds are sound and recorded in "Current state".

Today `npm run test:e2e` can't run (no Chromium) and would write into the user's real database through
whatever backend is on :8000.
- `tradurre/config.py`: `DB_PATH` comes from the environment variable `TRADURRE_DB` when it is set, else the
  current default. Test in `tests/test_main.py` or a new `tests/test_config.py` (reload the module with the
  variable set via `monkeypatch`).
- `frontend/vite.config.ts`: the proxy target is `process.env.TRADURRE_API ?? 'http://127.0.0.1:8000'`.
- `frontend/playwright.config.ts`: `baseURL` `http://localhost:5174`; `webServer` becomes two servers, both
  `reuseExistingServer: false`: (1) the backend, `command: 'rm -f ../.e2e.db && uv run uvicorn tradurre.app:app
  --port 8001'`, `env: {TRADURRE_DB: '<repo>/.e2e.db'}` (absolute, from `path.resolve`), `url:
  'http://127.0.0.1:8001/api/v2/books'`; (2) `npx vite --port 5174 --strictPort` with `env: {TRADURRE_API:
  'http://127.0.0.1:8001'}`. `.e2e.db*` goes in `.gitignore`.
- `frontend/e2e/scroll-sync.spec.ts`: its `API` constant becomes relative (`/api/v1`, resolved against
  `baseURL`). Run it and report whether it passes; if it fails, don't fix it (it tests the old editor, removed in
  Stage 7): mark it `test.fixme` with a one-line comment giving the failure.
- `frontend/e2e/books.spec.ts`: a smoke test only: `POST /api/v2/books` with two small txt files (Playwright
  `request` multipart), then `GET /api/v2/books` lists it. (The UI specs come with the next tasks.)
- Install the browser once: `npx playwright install chromium` (in `frontend/`). If the download is impossible in
  this environment, stop and report (`blocked`).
- `CLAUDE.md` "Commands": one line saying e2e runs on a throwaway backend (:8001, `.e2e.db`) and Vite :5174.

#### Book list and import
Status: done
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes including the new cases in
`frontend/e2e/books.spec.ts`; `uv run pytest` unchanged.
Report: 2026-10-03 — `booksApi` + `Book…` types in `client.ts` (errors carry the server's `detail`), routes `/book/import` and `/book/:id`, `BookImport.vue`, minimal `BookView.vue` (header + rows), `ProjectList.vue` routes books and offers the import; e2e 5 passed (4 in `books.spec.ts`, incl. a warnings case beyond the task's list); type-check passes; pytest 249 passed (unchanged).
Verified (/pauli, 2026-10-03, `3742c75`): type-check passes, e2e 5 passed. The extra warnings test is welcome.

- `client.ts`: `booksApi` (see the design) with `importBook(source: File, target: File, title: string,
  sourceLang: string, targetLang: string)` (multipart; no JSON content-type header), `listBooks()`, `getBook(id)`.
- `frontend/src/router/index.ts`: route `/book/:id` (name `book`, props) to `BookView.vue`, and `/book/import`
  (name `book-import`) to a new `BookImport.vue`. For this task `BookView.vue` shows only the header (title,
  "reviewed X / N") and the plain list of rows (no selection, no keys): the next task fills it in.
- `ProjectList.vue`: loads `listBooks()` alongside `listProjects()`. A project whose id is a book shows "N
  beads, X reviewed" instead of the paragraph count and opens `/book/:id`; others behave as today. A button
  "Import a book (txt/docx)" next to "New Project" opens `/book/import`.
- `BookImport.vue`: two file inputs (`accept=".txt,.docx"`), labelled "Original (French)" and "Translation
  (Italian)"; title input pre-filled from the original's filename without extension when it is chosen (editable);
  languages pre-filled `fr`/`it` (SPEC §3.1.1); "Import" button disabled until both files are chosen and while
  importing. On error, the server's message in red. On success with no warnings, go to `/book/:id`; with
  warnings, show them in a list with a "Continue" button that goes there.
- `books.spec.ts` (UI, with `page.setInputFiles` and in-memory buffers): import through the form → lands on
  `/book/:id` showing the title and as many rows as beads; back on `/`, the book shows its bead count and opens
  the book view; importing a `.pdf` shows the server's 415 message.

#### Reading and navigation
Status: done
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes including `frontend/e2e/book-view.spec.ts`;
`uv run pytest` unchanged.
Report: 2026-10-03 — `components/BeadRow.vue` (blocks on new lines, bold headings, grey empty cell, green reviewed border, selection via props), `BookView.vue` (shallowRef book, current bead/side/segment, ↑ ↓ ← → Tab Shift+Tab click `n`, status line, "Show excluded" rows after their bead); `e2e/book-view.spec.ts` 6 tests (heading case via a routed response, since txt import has no headings); 10,000-bead book: load 1.56–1.77 s, 20 ArrowDown 1.42–1.46 s (3 runs); e2e 11 passed; type-check passes; pytest 249 passed (unchanged).
Verified (/pauli, 2026-10-03, `5231269`): type-check passes, e2e 11 passed (10k: load 1573 ms, 20 ↓ 1443 ms),
pytest 249. Navigation costs ≈72 ms a press because the parent still rebuilds 10,000 row vnodes per selection
change; acceptable now, and Stage 4's virtualization removes it. The routed-response trick for headings is fine.

`BookView.vue` gets the layout and selection of the design: block starts and headings, empty one-sided cells,
reviewed border, current bead/side/segment, the keys ↑ ↓ ← → Tab Shift+Tab, clicking, keeping the current row
visible; plus `n`: jump to the next unreviewed bead after the current one, wrapping to the first (SPEC §3.3 "a
shortcut to the next unreviewed bead"; with none left, the status line says "Every bead is reviewed"). "Show excluded" (off by default, SPEC §3.3 "hidden by default and can be revealed in place"): each
excluded block appears, greyed and italic with its kind as a small label, as an extra row right after the row of
its `after_bead_id` (before the first row if null), in its side's column; several after the same bead keep API
order. Excluded rows can't be selected yet. Spec: `n` skips a reviewed bead (mark it through the API first);
arrows move the outline and side tint as described (assert with
`data-` attributes: `data-bead-id`, `data-current`, `data-side`); a heading renders bold; the toggle reveals a
block excluded through the API (`POST .../blocks/{id}/exclude`) at the right place.

**Scale** (added by /pauli after measuring, 2026-10-03): SPEC §1 puts a book at 3,000–10,000 sentences per side,
and this screen is meant for real books before Stage 4 virtualizes it. The backend is not the problem (a
10,000-bead book: `GET /books/{id}` 2.6 MB in 0.14 s, a correction 0.12 s); rendering is. So:
- One row = a child component `frontend/src/components/BeadRow.vue` with props `bead`, `current: boolean`,
  `currentSide: Side | null` and `currentSegmentId: number | null` (null on non-current rows), so moving the
  selection changes the props of two rows only and Vue skips the rest. Hold the book in a `shallowRef`.
- `book-view.spec.ts` also imports a generated 10,000-bead book (one sentence per paragraph per side, via the
  API) and records: time from `page.goto` to the last row being in the DOM, and the time for 20 ↓ presses (each
  awaited on `data-current` moving). Thresholds: load under 5 s, 20 presses under 2 s. Put both numbers in the
  `Report:`. If a threshold fails with this structure, report it (`blocked`) rather than inventing a different
  architecture: virtualization is Stage 4's, and /pauli would pull it forward.

#### Bead corrections
Status: done
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes including `frontend/e2e/book-corrections.spec.ts`;
`uv run pytest` unchanged.
Report: 2026-10-03 — `booksApi` correction functions (`client.ts`), button bar in the current cell (`BeadRow.vue`), `BookView.vue`: Alt+↑/↓ m s r x Ctrl+Z/Y/Shift+Z, Include on excluded rows, Undo/Redo in the header, `busy`, selection rule, `reconcile`, guard narrowed to text entry; `book-corrections.spec.ts` 8 tests; 10k book: `r` to border 274–487 ms, 20 ↓ now 1638–1736 ms (was ≈1440); e2e 19 passed; type-check passes; pytest 249 passed (unchanged).
Verified (/pauli, 2026-10-03, `b5193ab`): type-check passes, pytest 249, e2e 19 (rerun by Braun serially; the
code is what was tested). Every case the task listed is covered. Two things carried into "Segment editing":
`correct()` captures side and segment before the request but reads the current bead after it, so ↓ pressed
during a slow request mixes old and new selection; and 20 ↓ on the 10k book rose to ≈1650 ms (limit 2 s).

Keyboard first (SPEC §3.3); keys ignored while a text field has focus:
- Alt+↑: move the current side's first segment to the previous bead (`move`, `to: previous`); Alt+↓: its last
  segment to the next bead (`to: next`). Not `[`/`]`: on the Italian keyboard the translator uses on Windows they
  need AltGr.
- `m`: merge the current bead with the next (`merge-next`).
- `s`: split the current bead at the current segment: `{source_at: seg, target_at: null}` on the source side,
  mirrored on the target side. The current segment and everything after it on that side go to the new bead; the
  other side stays.
- `r`: toggle the current bead's reviewed mark (`reviewed` with `bead_ids: [current]`, `skim: false`).
- `x`: exclude the current segment's block (`blocks/{block_id}/exclude`). On a revealed excluded row, an
  "Include" button (`include`).
- Ctrl+Z: undo; Ctrl+Shift+Z and Ctrl+Y: redo. Compare `event.key` case-insensitively (with Shift it is `Z`).
  Cmd on macOS is not needed.

Code:
- `client.ts`: `booksApi` gains one function per endpoint, each returning `Promise<Book>`: `move(id, beadId,
  side, to)`, `mergeNext(id, beadId)`, `splitBead(id, beadId, sourceAt, targetAt)`, `setReviewed(id, beadIds,
  reviewed)`, `excludeBlock(id, blockId)`, `includeBlock(id, blockId)`, `undo(id)`, `redo(id)`. (Segment
  functions come with the next task.)
- `BookView.vue` key handler: today it returns on any Ctrl/Meta/Alt modifier (`BookView.vue:103`). Handle
  Alt+↑/↓ and Ctrl+Z/Y/Shift+Z before that guard (and `preventDefault` them); plain keys keep the guard, so
  Ctrl+R still reloads.
- The text-field guard (`BookView.vue:102`) also swallows keys while the "Show excluded" checkbox has focus,
  which it has right after a click: the translator toggles it and then ↓ does nothing. Narrow the guard to text
  entry: `textarea`, `select`, content-editable, and `input` unless its `type` is checkbox, radio or button.
- **One correction at a time:** a `busy` flag set while a request is in flight; correction keys and buttons do
  nothing while it is set (navigation still works). Otherwise a fast double `m` sends a second request built from
  the stale book.
- **Selection after a correction** (refines the shared design): the current bead stays if it still exists, else
  the bead now at the old index (clamped); the side stays; the current segment stays if it is still in that cell,
  else the cell's first segment. One exception: after `s` the current bead is the new bead (old index + 1), so
  the current segment stays the one the translator split at.
- **Keep the 10k book fast:** the returned book is fresh JSON, so every `BeadRow` would get new props and
  re-render. Before assigning it, reuse the old bead object for each new bead whose `id` exists in the old book
  and whose `JSON.stringify` is equal (a small `reconcile(old, next)` in `BookView.vue`), and do the same for the
  `excluded` entries by `block_id`. Then only changed rows re-render.
- **Buttons:** `BeadRow.vue`, on the current row only, shows a small button bar in the current side's cell:
  "↑ first", "↓ last", "Merge", "Split", "Reviewed"/"Unreviewed", "Exclude", each with a `title` naming its key
  and `data-action` (`move-previous`, `move-next`, `merge`, `split`, `reviewed`, `exclude`), emitting
  `correct(action)` with `@click.stop` (the cell's click selects). Undo/Redo buttons in the header, disabled from
  `can_undo`/`can_redo` (and while `busy`).
- Errors: the server's message in the status line (`say`), as in the shared design.

Spec `book-corrections.spec.ts`, on the book of `book-view.spec.ts` (copy its helpers):
- Alt+↓ then Alt+↑ on a source side: rows after each (compare cell texts);
- `m` on B, `s` back at the same segment (and the current bead is the new one);
- `r` sets and clears `data-reviewed`; the header progress follows;
- `x` hides the block; with "Show excluded" the Include button brings it back; after clicking the checkbox,
  ↓ still moves the current bead;
- `m` on the last bead shows "There is no next bead to merge with" in the status line;
- Ctrl+Z after a correction restores the rows and Ctrl+Y (and, after another Ctrl+Z, Ctrl+Shift+Z) redoes it;
  the header Undo button is disabled on a fresh book;
- one button click (`[data-action="merge"]`) does the same as `m`;
- on a 10,000-bead book (as in `book-view.spec.ts`), the time from pressing `r` on bead 20 to its reviewed
  border appearing: recorded in the `Report:`, under 1.5 s, else `blocked` (as in the previous task).

#### Segment editing
Status: done
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes including `frontend/e2e/segment-editing.spec.ts`
and the existing 10k navigation limit (20 ↓ under 2 s); `uv run pytest` unchanged.
Report: 2026-10-03 — inline editor (Enter/double-click; Enter saves, Escape cancels, Ctrl+Enter splits, blur saves), `j`, segment client functions, `correct()` reads the selection after the request, selection injected (`selection.ts`, `currentRow` map), correction buttons moved to a header bar (`BeadActions.vue`, injects the selection so the list doesn't re-render), header buttons disabled while editing; `segment-editing.spec.ts` 8 tests, button case moved to the header bar plus a no-layout-shift case; 10k: 20 ↓ 1144–1358 ms (was ≈1650), `r` 298–580 ms, load 1.8–2.3 s (was 1.6–1.7); e2e 28 passed; type-check passes; pytest 249 passed (unchanged).
Report: 2026-10-03 — blocked on a layout shift: the button bar ("Bead corrections") lives in the current cell, so when a click moves the selection down, the old row loses its bar and everything below rises by its height; a double-click's second click then lands on the new row's "↑ first" button and moves a segment (event log: `click SPAN`, then `mousedown/click/dblclick BUTTON ↑ first`). Needs a decision on where the bar goes. Everything else is in place, uncommitted: editor, `j`, client functions, the `correct()` fix, the selection via `provide`/`inject`; segment-editing 7/8 pass, the rest of e2e passes. Scale: the tripwire's "`current` a computed comparing its bead id" made 20 ↓ slower (1964–2083 ms; 10k computeds all depend on one ref); a per-id `shallowReactive` map (`currentRow`, only two rows woken) brought JS per press from ≈60 to ≈25 ms and 20 ↓ to 1633 ms in the full parallel run (dev-mode Vite).
Answered (/pauli, 2026-10-03): resume from the uncommitted tree; it is sound. Decisions:
- **The correction buttons move to the sticky header**, one bar acting on the current bead and side, right of the
  title (same labels, `title`s and `data-action`s; `data-testid="bead-actions"` on the bar). `BeadRow.vue` loses
  its bar and the `correct` emit; `BookView.vue` calls `runCorrection` directly. Reason: nothing in a row may
  change height with the selection (see the shared design), and a bar per row was the only thing that did. The
  header is already sticky, so the buttons stay in reach; the screen is keyboard-first anyway (SPEC §3.3). The
  Reviewed/Unreviewed label follows the current bead. In `book-corrections.spec.ts`, the button case clicks
  `getByTestId('bead-actions').locator('[data-action="merge"]')`.
- **Header buttons (corrections and Undo/Redo) are disabled while a segment is being edited** as well as while
  `busy`. A click on them still blurs and saves the editor, and the click itself does nothing, visibly, instead
  of silently racing the save.
- **The `currentRow` map is accepted** and replaces the tripwire's "computed comparing its bead id", which wakes
  every row: keep `selection.ts` as it is. A note on its design goes in the "Scale" paragraph below.
- **Window blur saving an open edit is accepted** (it saves, it never loses text).
- Spec additions: in `segment-editing.spec.ts`, a double-click on a row below the current one opens the editor
  (the existing case starts on bead A and double-clicks B's target, so it already covers this once the bar
  moves); in `book-view.spec.ts` or `book-corrections.spec.ts`, one check that selecting a row leaves the
  bounding box of the row below it unchanged (`boundingBox().y` before and after a click on the row above).

SPEC §3.3: "split a segment at the cursor, join with the next segment; edit segment text inline (plain text)".
- **Opening:** `Enter` on the current segment, or a double-click on a segment (the first click selects it),
  replaces its span with a `textarea` holding its text, focused, caret at the end, as wide as the cell and
  growing with the text. State: `editingSegmentId` in `BookView.vue`, passed to `BeadRow.vue` as a prop that is
  null on every row but the current one (same scale rule as the selection props). While editing, the window key
  handler already ignores keys (the target is a textarea).
- **In the textarea:** Enter saves; Escape cancels; Ctrl+Enter splits at the caret; **blur saves** (changed from
  "blur cancels": clicking elsewhere must not throw away typed text; Escape sets a cancel flag before the
  textarea goes, so its blur doesn't save). Saving sends `edit` only if the text changed (newlines replaced by
  spaces first, which keeps offsets); the server refuses an empty text and its message goes to the status line,
  with the textarea closed and the old text shown. Ctrl+Enter: if the text changed, `edit` then `split` at the
  caret's offset (two requests inside one `busy` period, two undo steps; if `edit` fails, no split); else only
  `split`. After either, the current segment is the first part (it keeps its id).
- `j`: join the current segment with the next (`join-next`); the current segment stays.
- `client.ts`: `editSegment(id, segmentId, text)`, `splitSegment(id, segmentId, offset)`, `joinNext(id,
  segmentId)`, each returning `Promise<Book>`. The `busy`, selection and `reconcile` rules of "Bead corrections"
  apply.
- **Fix in `correct()` (`BookView.vue`):** read the selection (bead, side, segment) after the request returns,
  not before, and take the fallback index from the old book; so navigation during a request is respected.
- **Scale:** the selection is provided by `BookView.vue` and injected by `BeadRow.vue` (`frontend/src/
  selection.ts`); a row knows it is current from `currentRow[bead.id]`, a `shallowReactive` map with one key, so a
  move wakes two rows; side, segment and editing are read only by the current row. (Comparing every row's id
  with one ref was tried and was slower: it wakes all 10,000.) Report the 20 ↓ timing.
Spec `segment-editing.spec.ts` (book and helpers as in `book-corrections.spec.ts`): Enter, type, Enter saves
(rows); Escape cancels (no change, Undo still disabled); clicking another row saves; Ctrl+Enter splits at the
caret (two segments in the cell; one Ctrl+Z restores one segment); `j` joins; saving an empty text shows "A
segment can't be empty; join it with its neighbour instead"; a double-click opens the editor.

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
