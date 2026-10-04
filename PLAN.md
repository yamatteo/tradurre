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
- A test written for a bug fix must fail on the code before the fix: `/braun` checks it (temporarily restoring the
  old code, then the fix) and says so in the `Report:`. A test that passes either way proves nothing.
- Stages are done in order. Within a stage, tasks are done top to bottom unless noted.
- Detail lives where work is imminent: the current stage is broken down to tasks; later stages stay broad until
  `/pauli` refines them.
- Completed stages move to `PLAN.<yymmdd>.Stage<n>.md`, leaving a pointer and a short summary here.

## Current state, in brief (2026-10-05)

- **One model since Stage 7.** The v0.1 code is gone (migration 6 drops `pairs`, `translation_memory` and the
  v0.1 projects; no `/api/v1`, no TipTap, no old Colab aligner). Books (migrations 2–5: documents, blocks, segments,
  beads, operations, `bead_index`, runs, warnings) are served by `/api/v2` (`api/books.py`) to the library
  (`ProjectList.vue`, `/`), import (`/book/import`), book screen (`/book/:id`) and search (`/search`).
- **Import** (Stage 3): .txt/.docx/.pdf pairs. Layout-aware PDF extraction, front/back matter by publishing
  markers, French/Italian segmentation, the length aligner; the run's stats and warnings are stored and shown
  under "Import log". Reference book: ~5 s, 1232 beads, 2 one-sided, 9 below confidence 0.5; against the gold,
  alignment F1 0.995, exclusion P 1.000 R 0.902.
- **Book screen** (Stages 2, 4): reading and keyboard navigation, `n` next unreviewed, `r` reviewed, "Show
  excluded", every SPEC §3.3 single-bead correction (keys and header buttons), inline segment editing, persistent
  undo/redo, problem navigation (`p`/`P`), selected runs (Shift+↑/↓, Shift+click) marked with `r`, and `R` "up to
  here", range exclude/include in the "More" menu, edited sentences marked with their original on `o` and
  "Restore original", re-align of the selection (More menu), cut/copy/paste of whole sentences (Ctrl+X/C/V).
  Restyled to design variant A; smooth at 5,000 beads. Stages 4 and 6 done (search at `/search` and from the
  book; More → Export: edition .txt/.docx and the project bundle; "Restore a bundle" on the library page).
  Stage 7: search grouped by book, the library order, database snapshots (local-time names) and the v1
  retirement (code and docs) done; next the release (fixtures, smoke script, local restore dates, the Windows checklist
  done; rc1 run on Windows: PDF runtime and uv upgrade problems): a clear PDF message, the launcher's
  VC++ runtime and upgrade retry, rc2, and its Windows run (all steps pass) done; next the version bump to
  0.2.0, the developer's tag, and one run of the published launcher. On the reference book the problem flags catch
  none of the 15 real errors: review is reading-first; better signals come after v0.2.
- **Re-planned with the user (2026-10-04), SPEC changed accordingly:** review is one mode, problem-first: jump to
  the next likely problem, correct, mark one bead, a selected run, or everything up to here as reviewed. The
  timed scroll "skim review" is dropped. The Colab aligner is **parked** (SPEC §3.2, §5): it returns only if a
  gold book scores below 0.95. A typical book is 1,000–5,000 sentences a side; performance targets are at 5,000
  beads. Order: Stage 6 → Stage 7 (v0.2), confirmed 2026-10-04. Then the translator reviews *Contrefeu* in v0.2 for a true
  gold (the current one was made by the user, the developer), and maybe a second book, to score the aligner again.
- `uv run pytest`: 387 passed, also on a fresh clone (tests read only committed synthetic fixtures; `-m library`
  tests run only where `library/contrefeu.*.pdf` exists, and assert counts only).
- `npm run type-check` passes; releases build with `npm run build`. `npm run test:e2e` (71 tests; the three timing tests run last, alone, in project `scale`) runs on its own
  backend (:8001, throwaway `.e2e.db`) and Vite (:5174), never the user's database. Setup per machine: `npx
  playwright install chromium` (on Ubuntu 26.04 with `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64`); tests
  use the full Chromium headless (`channel: 'chromium'`).
- `.gitignore` ignores every `*.json` (book-derived data must never be committed; `tests/fixtures/**` excepted):
  a new config JSON is tracked with `git add -f`.
- Python 3.14 only; AGPL-3.0-only (`LICENSE`, so PyMuPDF is a core dependency); `uv.lock` tracked, `pytest`/`httpx`
  in the `dev` group; the Windows launcher's `uv tool install` resolves from PyPI and never reads the lock.
- No user data needs migrating: the new model can start from an empty database.
- A real book pair is available **locally only**: `library/contrefeu.fr.pdf` / `contrefeu.it.pdf`, and the gold
  `library/contrefeu.gold.json` (all gitignored, copyrighted: never commit them or excerpts; the repo is public).

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
Done (2026-10-04). Archived in `PLAN.261004.Stage3.md`. PDF extraction with layout (`services/extract.py`: logical
pages and two-up spreads, page numbers by frequent slot, running heads, chapter-number headings, footnotes,
soft/hard hyphen joins, glyph resolution; non-paragraph blocks never cross a page); PDF import in the app
(PyMuPDF core dependency, extraction in a worker thread); French/Italian segmentation (`services/segment.py`);
the in-app gold book (`services/gold.py`, `scripts/gold_export.py`, `scripts/gold_score.py`, gold in
`library/contrefeu.gold.json`, gitignored); the length aligner (`services/align.py`: banded Gale–Church with an
anchor bonus, adaptive band, method `length`) on import; front/back matter by publishing markers
(`services/matter.py`, applied by `extract`); import runs and warnings (migration 5, `GET …/runs`, "Import log").
On the reference book: import ~5 s, 1232 beads, 2 one-sided, 9 below confidence 0.5; against the gold, alignment
F1 0.995, exclusion P 1.000 R 0.902. Rules decided there and still binding: library tests and plan notes give
counts only, never book text; a real-book problem gets a synthetic fixture before it is fixed; segmentation and
alignment run before the write transaction (`prepare_book`/`write_book`), connections wait 15 s for the lock;
aligner work is capped (no more unless a gold book scores below 0.95); docx and PDF stay first-class (mixed
sources per book).

---

## Stage 4 — Review view
Done (2026-10-04). Archived in `PLAN.261004.Stage4.md`. The book screen of SPEC §3.3, one mode, problem-first:
design variant A (A1 grid, two bars, bottom status, shortcuts panel `h`, import log), problem navigation (`p`/`P`,
low confidence < 0.5 or one-sided, "Highlight multi-segment"), reviewed marks on a bead, a selected run
(Shift+↑/↓, Shift+click) or "up to here" (`R`), range exclude/include and "Re-align the selection" in the More
menu, edited sentences marked with their original (`o`, "Restore original"), cut/copy/paste of whole sentences
(Ctrl+X/C/V). Rules decided there and still binding: the render rule (`BookView`'s template reads nothing that
changes on a move or message; row state changes are paint-only; no late fonts); keys work on an Italian Windows
layout (letters, Shift+letters, arrows, Enter, Tab, Esc, Ctrl+Z/Y/X/C/V); a refused correction changes nothing,
selection included; a test for a bug fix must fail before the fix; timing tests live in `e2e/scale.spec.ts` and run
last, alone. At 5,000 beads: load ~1.5 s, a correction 0.2–0.4 s (a move and its undo the slowest), smooth scroll.

---

## Stage 5 — Colab round trip
**Parked (user, 2026-10-04; SPEC §3.2, §5).** Skipped: after Stage 4 comes Stage 6. It returns only if a gold book
scores alignment F1 < 0.95. The notes below are kept for that case.

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
Done (2026-10-04). Archived in `PLAN.261004.Stage6.md`. SPEC §3.4 and §3.5. Search: `domain/search.py` (every
token a word beginning, quoted phrases, source/target/either, case and accents folded), `GET /api/v2/search`
(paged by 50), bead context (`…/beads/{id}/context`), the page `BookSearch.vue` at `/search` (state in the URL,
book chip, Context, Open → `/book/<id>?bead=<id>`), "Search" in the book's top bar; 100,000 beads: worst query
~145 ms. Export, from More → Export: the edition as reviewed (included blocks, current text) as .txt (UTF-8 BOM)
or .docx (`services/edition.py`), and the project bundle (`services/bundle.py`: a zip with a versioned
`bundle.json`, no ids, no undo history; restore always a new book, refused whole if malformed, "(restored date)"
on a title clash; "Restore a bundle" on the library page). Also: frame-precise timing tests (real corrections at
5,000 beads 150–290 ms), `type-check` covers `e2e/`. Corpus export (TMX/TSV) moved to SPEC §5.

---

## Stage 7 — v0.2: last features, retire the old model, release

Post-Stage-6 review (user, 2026-10-04):
- **Backups:** the app snapshots the database at each start (last 10 kept). No "back up all" button; bundles stay
  per book.
- **Windows:** the developer has a Windows machine with a Claude agent on it: before tagging v0.2, a written
  checklist that agent runs end to end. The translator's reviewed *Contrefeu* comes back to the developer as a
  bundle (the true gold).
- **Edition export:** stays as it is (included blocks only; a footnote is exported only if included).
- **Search:** results grouped by book, books in library order, reading order inside each book.
- **v0.1 data:** none (user, 2026-10-04): retiring v1 drops the `pairs` table outright, no export first.
- **SPEC changed (agreed 2026-10-04):** §4 snapshots at each start, last 10 kept; §3.4 results grouped by book.
Order: the two features, then the old model goes, then the checklist on the final build, then the tag.

### Search results grouped by book
Status: done
**Done when:** `uv run pytest` passes with the new tests; `npm run type-check` passes; `npm run test:e2e` passes
with `e2e/search.spec.ts` updated and the new test; `uv run python scripts/search_scale.py` keeps every median
under 1,000 ms (report them, the counts query included).

SPEC §3.4 (changed 2026-10-04): grouped by book, books in library order
(`projects.updated_at DESC`, then title, as `GET /books` lists them), beads in reading order (`beads.ord`) inside
each book. Relevance (`bm25`) is no longer used.
- `domain/search.py`: `search_beads` orders by `p.updated_at DESC, p.title, b.ord` (join `beads b ON b.id =
  bead_index.rowid` and `projects p`; `highlight()` works across the join); nothing else changes. New
  `count_beads(conn, text, side="either", project_id=None) -> list[dict]`: `{project_id, title, count}` per book
  with a match, in the same book order (`GROUP BY b.project_id`); `[]` when `fts_query` is None.
- API (`api/books.py`): `GET /search/books?q=&side=&book=` → `list[BookSearchCount]` (`models.py`: `book_id`,
  `title`, `count`); same parameter checks as `/search` (404 for an unknown `book`). `client.ts`:
  `booksApi.searchCounts(q, side, book?)`.
- `BookSearch.vue`: a new search fetches the counts and the first page together. Above the results: "N results
  in M books" (`data-testid="search-summary"`; "1 result in 1 book" singular). Results are shown under a group
  header per book (`data-testid="result-group"`, `data-book-id`): "<title> · <count> results" from the counts,
  placed before the first result of each run of results with that `book_id` (a book's results may continue on
  the next page: no second header then, since the runs stay consecutive). Each result keeps "bead N", the pill,
  Context and Open; the per-result title (`result-title`) goes.
- `scripts/search_scale.py`: also time `count_beads` for the one-letter prefix and the full word.
- Tests: `tests/test_search.py`: two books, the second updated later (`UPDATE projects SET updated_at`): results
  come book by book, the later-updated book first, positions ascending inside each; `count_beads` gives both books
  with their counts in that order, and one book with `project_id`. `tests/test_books_search_api.py`: `/search/books`
  shape, `book=` scope, 404. `e2e/search.spec.ts`: replace the `result-title` assertions with group assertions
  (the group header names the book and its count); new: two books with 2 and 1 matches → summary "3 results in 2
  books", two groups, the counts in their headers, each group's results in ascending bead number.
Report: 2026-10-04 — search ordered by book (library order) then bead order; `count_beads` + `GET /search/books`; page shows the summary and a header per book (`result-title` gone); search_scale.py medians d 73.6, de 49.9, word 11.8, phrase 0.9, d source 47.5, d offset 200 74.6, one book 1.2, counts d 81.9, counts word 0.3 ms (worst 81.9); pytest 438, type-check clean, e2e 70.

### Library order: a tie-break, and a restored book on top
Status: done
**Done when:** `uv run pytest` passes with the new tests; each new test fails on the code before the change
(check it by restoring the old line); `npm run test:e2e` passes.

Review of "Search results grouped by book": the library (`GET /books`, `api/books.py:202`) orders by
`p.updated_at DESC` only, the search by `p.updated_at DESC, p.title` (`domain/search.py:92`); and a restored
bundle keeps the bundle's `updated_at` (`services/bundle.py:139`), so a book restored today can land at the bottom
of the library and of the search results, though restoring it is the latest work on it (SPEC §3.4 "most recently
worked on first").
- `domain/search.py`: rename `_BOOK_ORDER` to `BOOK_ORDER` (comment: the library order, shared by `GET /books`
  and the search); `api/books.py` `list_books` uses `ORDER BY {BOOK_ORDER}`. Nothing else in the query changes.
- `services/bundle.py` `import_bundle`: the new book's `updated_at` is now (UTC ISO, as `api/books.py` `_now`);
  `created_at` is still the bundle's. Update the module docstring (one clause). The bundle format does not change.
- Tests: `tests/test_bundle.py`: `_normal` also drops `book.updated_at`; in `test_round_trip`, the restored book's
  `updated_at` is later than the original's `"2026-10-02"` and its `created_at` is `"2026-10-01"`.
  `tests/test_books_export_api.py` `test_bundle_restore`: the restored book is first in `GET /books`.
  `tests/test_books_search_api.py`: two books with the same `updated_at` (set with SQL on the app's database, as
  the fixture's path allows) list in title order in `GET /books`, and `/search/books` gives the same order.
Report: 2026-10-04 — `BOOK_ORDER` (updated_at DESC, title) shared by `GET /books` and the search; a restored bundle's `updated_at` is now, `created_at` kept; 3 new/changed tests, each failing on the old code; pytest 439, e2e 70.

### Database snapshots at start
Status: done
**Done when:** `uv run pytest` passes with the new `tests/test_backup.py`; `npm run test:e2e` passes (its fresh
database means no snapshot). By hand, on a copy of a database in the scratchpad (`TRADURRE_DB=<copy>`): starting
`uv run tradurre --no-browser` twice (stop it with Ctrl+C or a timeout) leaves two files in `backups/` next to the
copy (report their names and sizes); starting `uv run tradurre --dev` adds none.

SPEC §4 "Never lose work" (user, 2026-10-04). Protects against an app bug, a bad migration or a bad correction;
not against losing the disk (the bundle and copying the file do that).
- New `tradurre/backup.py`: `snapshot(db_path: Path, keep: int = 10, now: datetime | None = None) -> Path | None`.
  No file at `db_path` → None, nothing created. Otherwise copy it with the SQLite backup API
  (`sqlite3.connect(src).backup(dst)`, consistent under WAL) to `db_path.parent / "backups" /
  f"{db_path.stem}-{now:%Y%m%d-%H%M%S}.db"` (`now` defaults to UTC now; if that name exists, append `-2`, `-3`…),
  then delete the oldest `"{stem}-*.db"` files in that folder beyond `keep`, sorted by `Path.stem` (not the
  full name: `"…-120000-2.db"` sorts before `"…-120000.db"`, but its stem sorts after). Any `OSError` or
  `sqlite3.Error` → print one line "Tradurre: database snapshot failed: <error>" and return None: a failed
  snapshot never stops the app.
- `app.py` lifespan: `snapshot(DB_PATH)` **before** `init_db`, so a migration that goes wrong can be undone from
  the snapshot taken just before it; skipped when the environment has `TRADURRE_DEV=1` (read at startup with
  `os.environ.get`, not at import).
- `--dev` takes no snapshots (user, 2026-10-04: every auto-reload re-runs the lifespan and would rotate the
  developer's real snapshots out). `__main__.py`: when `args.dev`, set `os.environ["TRADURRE_DEV"] = "1"` before
  `uvicorn.run`; the reload worker inherits it. End-user mode and the e2e server (plain `uvicorn`) don't set it.
- `README.md`: a short "Backups" paragraph: where the snapshots are, how many, and that restoring one means
  closing Tradurre and copying it over `tradurre.db`.
- `tests/test_backup.py`: no database → None and no `backups` folder; a database with a project row → the
  snapshot opens and holds the row; 12 snapshots with increasing `now` → the 10 newest names remain; two in the
  same second → two files; `backups` existing as a plain file → None, no exception; the app's startup on an
  existing database makes a snapshot (`TestClient(app)` with `DB_PATH` monkeypatched, as the API tests do; also
  monkeypatch `tradurre.app.DB_PATH`, which `app.py` imported by name), and none with
  `monkeypatch.setenv("TRADURRE_DEV", "1")`; sorting by stem: `-2` in the same second survives over the plain name
  when `keep` cuts between them.
- `.gitignore`: add `/backups/`. `TRADURRE_DB=./x.db` (a developer's throwaway database) puts the snapshots next
  to it, in the repo root; they hold book text and must never be committed.
Report: 2026-10-04 — `tradurre/backup.py` `snapshot` (backup API, keep 10 by stem, failures print and return None), called before `init_db` unless `TRADURRE_DEV` (set by `--dev`); README "Backups", `/backups/` ignored; manual: two `--no-browser` starts on a scratch copy → `t-20261004-182031.db`, `t-20261004-182039.db`, 143,360 bytes each, `--dev` (reached startup) added none; pytest 447 (8 new), e2e 70.

### Snapshot names in local time
Status: done
**Done when:** `uv run pytest` passes with the new test, which fails on the code before the change (check it by
restoring the old line).

Review of "Database snapshots at start": names use UTC (`tradurre/backup.py`, `datetime.now(timezone.utc)`), so in
Italy the snapshot taken at 20:20 is named `…-182031.db`. The names exist for a person choosing one to restore
(README "Backups": "named by date and time"); they must read as the local clock.
- `backup.py`: the default `now` is `datetime.now()` (local, naive). The `now` parameter, the name format and the
  sort by stem don't change. Accepted: in the hour repeated when daylight saving ends, names can sort out of order;
  at worst the clean-up drops a snapshot from that hour first. Don't add logic for it.
- README "Backups": "named by the date and time they were taken (your computer's clock)".
- `tests/test_backup.py`: `snapshot(db_path)` without `now` gives a name whose `YYYYmmdd-HHMM` is
  `datetime.now()`'s, read just before or just after the call (either one, to survive a minute boundary).
Report: 2026-10-04 — default `now` is `datetime.now()` (local); README says "your computer's clock"; new test fails on the old code under `TZ=Europe/Rome` (on a UTC machine both clocks agree, so it can't fail there); pytest 448.

### Retire the old model
The v0.1 code goes; v0.2 is the books model only (user, 2026-10-04: no v0.1 data to keep, nothing exported). Also
goes (user, 2026-10-04): the parked Colab aligner's old code (`tradurre-align` and its modules), whose output only
the v1 import reads; if it is ever unparked (SPEC §3.2), it is rebuilt on project bundles (Stage 5 notes), and
the old code stays in git history. Order: the screens the translator uses move off v1 first, then the v1
frontend goes, then the backend, then the docs. Each task leaves the app working.

#### Library page on books
Status: done
**Done when:** `uv run pytest` passes with the new tests; `npm run type-check` passes; `npm run test:e2e` passes,
with the new test.

`ProjectList.vue` today lists v1 projects (`api.listProjects`), merges book counts in, offers "New Project" (a v1
pair project) and deletes through v1 `api.deleteProject`.
- Backend: `DELETE /api/v2/books/{book_id}` in `api/books.py`, 204; 404 (as `_book_row`) for an unknown id. In
  `with transaction(db)`: `DELETE FROM projects WHERE id = ?`; the `ON DELETE CASCADE` foreign keys and the
  `bead_index` delete triggers do the rest (`tests/test_schema.py::test_delete_project_cascades` covers the
  schema side). Not undoable (the operation log goes with the book); the start-up snapshots are the safety net.
- `client.ts`: `booksApi.deleteBook(id)`.
- `ProjectList.vue`: books only, from `booksApi.listBooks()` (library order). Heading "Library". Each card:
  title, `FR → IT` (upper-case codes), "N beads, M reviewed"; `data-book-id` (replaces `data-project-id`);
  click opens `/book/<id>`. "Delete" asks `confirm('Delete "<title>"? This can\'t be undone.')`, then
  `deleteBook` and reload. Remove "New Project" and its form. Buttons stay: "Import a book (txt/docx/pdf)",
  "Restore a bundle". Empty: "No books yet. Import one to get started." Keep the current classes; no restyle.
- `App.vue` nav: "Tradurre", "Library" (`/`), "Search" (`/search`); the "Import" link (v1 wizard) goes.
- Tests: `tests/test_books_api.py`: delete → 204, then `GET /books/{id}` 404, the book gone from `GET /books`,
  its words gone from `/search`, and no rows left for it in `documents`, `beads`, `operations`, `runs`
  (read through the app's database file); a second delete → 404. `e2e/books.spec.ts`: `data-project-id` →
  `data-book-id`; new: import a book through the API, open `/`, Delete (accept the dialog with
  `page.once('dialog', d => d.accept())`), the card is gone and `GET /api/v2/books/<id>` is 404.
Report: 2026-10-04 — `DELETE /api/v2/books/{id}` (204/404) and `booksApi.deleteBook` (204 handled in `booksRequest`); library lists books only ("Library", `FR → IT`, `data-book-id`, Delete with confirm; New Project gone); nav: Library, Search; pytest 449, type-check clean, e2e 71.

#### Remove the v1 frontend
Status: done
**Done when:** `npm run type-check` and `npm run build` pass; `npm run test:e2e` passes, with the new test; `grep -rn
"tiptap\|/api/v1\|ProjectEditor\|ImportWizard\|SearchView" frontend/src frontend/e2e frontend/package.json` finds
nothing.
- Delete `views/ProjectEditor.vue`, `views/ImportWizard.vue`, `views/SearchView.vue` (unrouted since Stage 6) and
  their routes (`/project/:id`, `/import`) in `router/index.ts`.
- `client.ts`: remove `BASE`, `request`, the `api` object and the v1 types (`Project`, `Pair`, `SearchResult`,
  `SearchResponse`, `Import*`, `ResplitResponse`); `booksApi` and its types don't change.
- `npm uninstall` the four `@tiptap/*` packages (`package.json` and `package-lock.json`).
- `assets/main.css`: remove the "TipTap editor styles" block; the global `mark` rule becomes `background-color:
  var(--color-current-segment); color: inherit; padding: 0 1px; border-radius: 2px;` (search highlights in the
  A palette instead of v1 yellow).
- `router/index.ts`: the `/` route's name `projects` → `library` (and `App.vue`'s active-link check).
- Review of "Library page on books": `ProjectList.vue` `remove()` has no `catch`, so a failed delete fails
  silently. Rename the `restoreError` ref to `error` and its `data-testid` `restore-error` → `library-error`
  (update `e2e/book-layout.spec.ts`); `remove()` puts a failure's message there, as `restoreBundle()` does. New e2e
  in `books.spec.ts`: `page.route` answers the book's `DELETE` with 500 `{"detail": "Disk full"}` → the card
  stays and `library-error` reads "Disk full".
- The backend is not touched (the v1 API stays until the next task).
Report: 2026-10-04 — v1 views, routes, `api` client and TipTap (4 packages) removed, `mark` in the A palette, `/` route named `library`, library errors in `library-error` (delete included); also removed `e2e/scroll-sync.spec.ts`, which tested only the deleted v1 editor; grep clean, type-check and build pass, pytest 449, e2e 71 (−1 v1, +1 new).

#### Remove the v1 backend and the old Colab aligner
Status: done
**Done when:** `uv run pytest` passes; `npm run test:e2e` passes; `uv run tradurre --version` works; a migration
test shows a database at version 5 holding a v1 project with pairs and a book comes out at version 6 with the
book intact (`check_project` clean, searchable) and no `pairs`, `translation_memory` or v1 project; `grep -rn --exclude-dir=static
"api/v1\|pairs\|translation_memory\|tradurre-align\|doc_adapter" tradurre tests scripts pyproject.toml` (static: the
gitignored build, rebuilt by `npm run build`) finds only
`db.py`'s `_m001_pairs` and its schema strings, the new migration, and the migration tests.
- Migration `_m006_drop_v1` appended to `MIGRATIONS` (never edit `_m001_pairs`): drop the triggers `pairs_ai`,
  `pairs_au`, `pairs_ad`, the table `translation_memory`, the index `idx_pairs_project`, the table `pairs`; then
  `DELETE FROM projects WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.project_id = projects.id)` (v1
  projects; a book always has its documents, import and restore write them in one transaction). Use
  `_run_script`/`execute`, not `executescript`.
- Delete `api/projects.py`, `api/pairs.py`, `api/search.py`, `api/import_.py`, `api/export.py` and their
  `include_router` lines in `app.py`; `services/importer.py`, `html_utils.py`, `exporter.py`, `artifact_io.py`,
  `aligner.py`, `pipeline.py`, `pipeline_cli.py`, `embed_align.py`, `bertalign_align.py`, `llm_judge.py`; the
  models only they use (`Project*`, `Pair*`, `SearchResult`, `SearchResponse`, `Import*` but not
  `BookImportResponse`, `Resplit*`, `Artifact*`, `AlignedArtifact`).
- `doc_adapter.py`: move `normalize_ocr_artifacts` (and what it needs) into `services/extract.py`, update the import
  and the module docstring line that names `doc_adapter`, delete the file. `glyph_resolver.py` stays as it is.
- `pyproject.toml`: remove the `tradurre-align` script and the `align` extra; `uv lock`. Keep `pdf` and `ocr`.
- Tests: delete `test_aligner.py`, `test_pairs_api.py`, `test_import_artifact.py`, `test_pipeline_cli.py`;
  `test_doc_adapter.py`'s `normalize_ocr_artifacts` tests move to `test_extract.py`, the rest go.
  `test_books_api.py`'s two tests that create a v1 project through `/api/v1/projects` insert the document-less
  project row with SQL on the app's database instead (the `EXISTS` filter in `GET /books` stays).
  `test_migrations.py`: tests of `_m001_pairs` alone stay; any that expect `pairs` after the full `init_db` now
  expect it gone; plus the version-5 → 6 test above.
- `README.md`: remove the Colab/`tradurre-align` note and the `align` extra wherever they appear. CLAUDE.md is the
  next task.
- Checked complete (Pauli, 2026-10-04, after "Remove the v1 frontend" found an unlisted v1-only e2e spec): a grep
  for every removed module, model and `/api/v1` outside the files above finds only `app.py`, `models.py`,
  `extract.py` (the `doc_adapter` import), `test_books_api.py` (the two tests above), `pyproject.toml`/`uv.lock`,
  `README.md`, `CLAUDE.md` and the archived `PLAN.*.md` (leave those as they are: history). Other hits are the
  words "pipeline"/"aligner" in prose, not imports. If something else turns up: a file that
  only exercises removed code goes (report it); anything that mixes kept and removed code, stop and report.
Report: 2026-10-04 — `_m006_drop_v1`; 5 v1 routers, 11 services (doc_adapter's cleanup moved into extract.py), the v1 models, `tradurre-align` and the `align` extra (`uv lock`: −987 lines) removed; README Colab note gone; grep as allowed; pytest 384 (449 − 71 in the 5 deleted test files + 4 moved + 2 migration tests), e2e 71, `tradurre --version` ok.

#### CLAUDE.md and README describe v0.2
Status: done
**Done when:** every module, command, route and table named in `CLAUDE.md` exists (check each with `ls`/`grep`,
list the checks in the report); nothing in `CLAUDE.md` or `README.md` names `pairs`, `/api/v1`, TipTap, the import
wizard or translation memory.
- `CLAUDE.md` "Architecture": the code as it is now: `api/books.py` (`/api/v2`), `domain/` (layer, ordering, beads, blocks,
  segments, replace, history/undo, invariants, search), `services/` (extract, matter, segment, align, build, realign,
  edition, bundle, gold, glyph_resolver), `backup.py`; the data model (projects → documents → blocks → segments,
  beads, operations, runs/warnings, `bead_index` kept by triggers: never write to it); the migration rule stays;
  the frontend views (`ProjectList`, `BookImport`, `BookView`, `BookSearch`), components, `composables/` and the
  plain modules (`keys.ts`, `selection.ts`, `review.ts`); `scripts/` (gold export/score, search timing). Drop the v1 data
  model paragraph and the negative-position reindexing note. Keep "Workflow" and "Commands" (fix the example test
  names to existing files). The intro sentence saying the architecture notes describe code "the plan is
  replacing" goes.
- `README.md`: the intro speaks of books (import a source and its translation, review the alignment, search
  everything); no "translation memory" wording, no edit-both-sides-in-an-editor claim.
Report: 2026-10-04 — CLAUDE.md intro, Commands examples and Architecture/Data model/Frontend rewritten for the books model; README intro on books, "projects" → "books"; 127 names checked (files, symbols, tables, columns, routes, commands incl. running both example pytest commands), all present; no forbidden term; pytest 384.

### Windows checklist and release
Decided (user, 2026-10-04): the Claude agent on the developer's Windows machine is **shell only** (Claude Code):
it runs commands, and drives browsers only through a Playwright script; the Italian-layout keys are checked **by
hand** by the developer (Playwright sends keys by name, so it can't test a physical layout). The release candidate
reaches Windows as a **local wheel**, copied over; the launcher is tested with that wheel's `file:///` URL put in
by hand, and the download path only at the final tag. Order: fixtures → browser smoke script → the checklist →
the candidate wheel → the run on Windows → fixes → v0.2.0.

#### Checklist fixtures: a .docx and a .pdf
Status: done
Report: 2026-10-04 — `scripts/make_fixtures.py` writes `easy.source.docx` and a 3-page A5 `easy.target.pdf` (byte-identical on rerun: fixed core properties, zip dates and PDF metadata, no new /ID); `tests/test_fixtures_formats.py`: txt pair 28 beads, 0/0 excluded; docx+pdf 28 beads, 0 source / 6 target excluded (3 running heads, 3 page numbers; none in beads), check clean, search hits both; pytest 385 passed.
**Done when:** `uv run pytest` passes with the new test; `uv run python scripts/make_fixtures.py` rewrites the two
files byte-for-byte reproducibly or, if a format can't be (docx/pdf timestamps), the script sets fixed metadata
and the report says which; the files are committed (`!tests/fixtures/**` in `.gitignore` already lets the PDF in).

The checklist needs one book in every format, with no copyrighted text. `tests/fixtures/easy.source.txt` and
`easy.target.txt` (synthetic, FR/IT, 36 lines) are the text.
- `scripts/make_fixtures.py` (python-docx and pymupdf, both core dependencies): writes
  `tests/fixtures/easy.source.docx` (one Word paragraph per blank-line paragraph of `easy.source.txt`) and
  `tests/fixtures/easy.target.pdf` (A5 pages, ~12 pt, the paragraphs of `easy.target.txt` flowed over at least 3
  pages, each page with the running head "Facile" at the top and its page number at the bottom).
- `tests/test_fixtures_formats.py`, through the API (as `tests/test_books_api.py` does): import
  `easy.source.docx` + `easy.target.pdf` → 201, no error; the bead count is within ±15 % of the
  `easy.source.txt` + `easy.target.txt` import's; `/check` is clean; searching a word of the last paragraph finds
  it. Report the counts (beads, excluded blocks per side) for both imports.
- Nothing else changes; if the PDF's running head or page numbers end up in beads, report it (a finding for the
  extractor, not to fix here).

#### Browser smoke script
Status: done
Report: 2026-10-04 — `packaging/smoke.py` (11 steps, PASS/FAIL per step, exit 0/1; also deletes its books via the API after a failure) and a README line; the fixture book has no bead with two source sentences (27× 1:1, one 1:2), so Alt+↓ falls back to the first bead with two sentences on the target side; passed 3 times with `--channel chromium` on a scratch database on :8123 (twice on an empty library, once beside a book of the same text, left in place); pytest 385 passed.
**Done when:** after `npm --prefix frontend run build` (the installed app serves the built SPA), the script passes
on Linux against `uv run tradurre --no-browser --port 8123` with `TRADURRE_DB` in the scratchpad, with `--channel
chromium` (Playwright's own browser: `uv run --with playwright python -m playwright install chromium` first; Edge
and Chrome use the installed browser, so Windows needs no install step); run twice in a row on the same database
(it must not depend on an empty library, and the library holds the same books after each run as before it);
report its output. Then stop the server and delete the scratch database.

One script the Windows agent runs against the **installed** app, in Edge and in Chrome. Not part of `npm run
test:e2e` (that runs the dev servers); it reuses its `data-testid`s.
- `packaging/smoke.py`, Python Playwright, sync API, run with `uv run --with playwright python
  packaging/smoke.py --url http://127.0.0.1:8000 --channel msedge|chrome|chromium --fixtures <dir>`.
  It prints one line per step, `PASS <step>` or `FAIL <step>: <reason>`, stops at the first failure, exits 0/1.
- Steps (each tied to a unique title with a random suffix, so reruns don't collide): library loads; import the
  .docx + .pdf pair through the form (`/book/import`) and land on the book; `n` moves to an unreviewed bead and
  `r` marks it (progress text changes); Alt+↓ then Ctrl+Z (the bead's segments change, then come back); reload
  the page and Ctrl+Y redoes; search a word from the book (`/search`; earlier runs' books have the same text, so check the
  `result-group` titled with this run's title, and Open on its first result lands on that book and bead); More →
  Export: target .txt and .docx and the bundle download (non-empty files, the .txt starts with a UTF-8 BOM);
  "Restore a bundle" with that bundle opens "<title> (restored …)"; Delete the restored book from the library
  (accept the dialog), it's gone; then delete the imported one the same way, so a run leaves the library as it
  found it.
- How to find and check each thing: the `data-testid`s and assertions of the matching tests in
  `frontend/e2e/*.spec.ts` (import, keys, undo, search, export, restore, delete); the keys from
  `frontend/src/keys.ts`. Alt+↓ goes on the first bead with at least two source sentences (one-sentence beads
  would make the move a different case). Downloads with `page.expect_download()`, the restore through
  `restore-bundle-file`'s `set_input_files`, the delete confirm with a `dialog` handler that accepts.
- No test framework, no new dependency in `pyproject.toml`. `README.md` "Development": one line on how to run it.

#### Restored books dated in local time
Status: done
Report: 2026-10-04 — `bundle.py` dates a restored title with the local date; `test_restored_title_has_the_local_date` (fake clock: 5 Oct local, 4 Oct UTC) failed on the old line and passes; `test_round_trip`, `e2e/book-layout.spec.ts` and `packaging/smoke.py` expect the local date; pytest 386 passed, e2e 71 passed, type-check clean, smoke script passed on a built app with a scratch database.
**Done when:** the new test fails on the current `bundle.py` (check by restoring the old line) and passes after;
`uv run pytest` and `npm --prefix frontend run test:e2e` pass; `packaging/smoke.py` passes once more as in the task
above (built SPA, scratch database, `--channel chromium`).

A restored book is titled "<title> (restored YYYY-MM-DD)" with the **UTC** date (`services/bundle.py:136`): in
Italy, from midnight to 1:00/2:00, the title says yesterday. Snapshot names are already local time (user decision);
the title is for the same person, so it follows.
- `services/bundle.py:136`: `datetime.now().date()` (local). The other `datetime.now(timezone.utc)` uses in the file
  (`exported_at`, `created_at`/`updated_at` stamps) are machine timestamps and stay UTC.
- `tests/test_bundle.py`: a test that monkeypatches `tradurre.services.bundle.datetime` with a `datetime` subclass
  whose `now(tz=None)` returns 2026-10-05 00:30 local when `tz` is None and 2026-10-04 22:30 UTC otherwise, restores
  next to a same-titled book and expects "(restored 2026-10-05)". `test_round_trip` (`tests/test_bundle.py:91`)
  computes `today` in UTC: make it `datetime.now().date()`.
- `frontend/e2e/book-layout.spec.ts:131` and `packaging/smoke.py` (`restore_bundle`): expect the local date (in the
  e2e, from `getFullYear/getMonth/getDate`; in the script, `datetime.now().date()`), and drop the "dates the copy in
  UTC" comment.

#### Windows checklist
Status: done
Report: 2026-10-04 — `packaging/WINDOWS-CHECKLIST.md` (preamble with `Wait-Tradurre`/`Stop-Tradurre` by PID, steps 1–7, `PYTHONUTF8=1` for the smoke output); Linux rehearsal in a scratch `HOME`: v0.1.0 from its release wheel took "Checklist v0.1" (201), the current code then showed `/api/v2/books` `[]` and one snapshot holding it; step 5 against the current code: import 201 (28 beads), reviewed 200, after a restart undo 200 and the bead unreviewed, 2 snapshots, edition .txt BOM + "parola", .docx has it, delete 204; PowerShell, the launcher and Edge/Chrome not run (Linux); no Contrefeu text; pytest 386 passed.
**Done when:** `packaging/WINDOWS-CHECKLIST.md` exists, `grep -ri contrefeu` on it finds nothing, and the
**Linux rehearsal** below passed and is in the report (commands and outputs, shortened).

`packaging/WINDOWS-CHECKLIST.md` is read and run by a Claude Code agent on the developer's Windows 11 machine, in
PowerShell, with no GUI: every step is a command (copyable as is) and its expected result. The agent appends to
`C:\tradurre-rc\RESULTS.md`, per step, `PASS`/`FAIL`, the command's relevant output and anything unexpected; on
a FAIL it goes on with the next independent step and, whatever happens, runs the restore step last. No *Contrefeu*
text, nothing from the developer's library in the results (counts only).

Facts it builds on (checked by Pauli, 2026-10-04):
- The candidate arrives as the folder `C:\tradurre-rc\` (made by "Release candidate wheel"): the wheel; the
  launcher `start-tradurre.bat` with `VERSION=0.2.0rc1` and `WHEEL_URL=file:///C:/tradurre-rc/<wheel name>`;
  `smoke.py`; `fixtures\` (`easy.source.docx`, `easy.target.pdf`, `easy.source.txt`, `easy.target.txt`); the
  checklist itself.
- v0.1.0 is on GitHub: `https://github.com/yamatteo/tradurre/releases/download/v0.1.0/tradurre-0.1.0-py3-none-any.whl`
  (extras `pdf`, `requires-python >=3.12`). Its CLI has `--no-browser` and `--port`, **no** `--version` and **no**
  `TRADURRE_DB` (it always uses `%USERPROFILE%\.tradurre\tradurre.db`). Its API: `POST /api/v1/projects`
  with JSON `{"title", "source_lang", "target_lang"}` → 201.
- The launcher (`packaging/start-tradurre.bat`) passes its arguments to `tradurre.exe` (`--no-browser` works),
  upgrades when `tradurre.exe --version` differs from `VERSION` ("Updating Tradurre from an older version to …"),
  and runs `pause` on errors: start it with input from NUL so a failure can't hang the agent.
- `tradurre.exe` runs in the foreground: start it with `Start-Process` (output to a log file) and stop it by the
  process id of `tradurre.exe` (`Get-Process tradurre`), never by a name pattern that could match the agent's
  shell. Wait for `http://127.0.0.1:8000/api/v2/books` (v0.2) or `/api/v1/projects` (v0.1) to answer before going
  on. `curl.exe`, not PowerShell's `curl` alias.

Steps, in this order:
1. **Prepare and back up.** Edge and Chrome are installed (paths); `uv` present or installed with the official
   PowerShell one-liner. Record whether `tradurre.exe` exists and its `--version` output. Stop any running
   Tradurre. Rename `%USERPROFILE%\.tradurre` to `%USERPROFILE%\.tradurre.before-rc` if it exists.
2. **v0.1.0.** `uv tool install --force --python 3.14 "tradurre[pdf] @ <v0.1.0 wheel URL>"`; start it with
   `--no-browser`; create the project "Checklist v0.1" (fr→it) → 201; stop it.
3. **Upgrade through the candidate launcher.** Run `C:\tradurre-rc\start-tradurre.bat --no-browser` (input from
   NUL, output to a log): the log says it updates to 0.2.0rc1; the app answers; `tradurre.exe --version` →
   `tradurre 0.2.0rc1`; `GET /api/v2/books` → `[]` (migration 6 dropped the v0.1 project); `backups\` holds one
   `tradurre-*.db` whose `projects` table (read with `uv run --python 3.14 python -c "import sqlite3…"`) has
   "Checklist v0.1".
4. **Browsers.** `uv run --python 3.14 --with playwright python C:\tradurre-rc\smoke.py --channel msedge
   --fixtures C:\tradurre-rc\fixtures`, then `--channel chrome`: both exit 0; full output into the results.
5. **API round trip and a restart.** Import the .txt pair with `curl.exe -F` → 201; mark its first bead reviewed
   (`POST /api/v2/books/{id}/reviewed`); stop and restart (the launcher again: this time **no** "Updating" line);
   `POST /api/v2/books/{id}/undo` → the bead is unreviewed again (undo survives a restart); `backups\` now holds
   two snapshots; `GET /api/v2/books/{id}/export/edition` for the target .txt starts with the UTF-8 BOM and
   contains the last word of `easy.target.txt`, the .docx opens with python-docx (`uv run --with python-docx`)
   and contains it too (the query parameters: as `api/books.py` defines them); delete the book → 204.
6. **Restore.** Stop Tradurre. Move `%USERPROFILE%\.tradurre` to `C:\tradurre-rc\rc-data` (kept for the
   developer to inspect), rename `.tradurre.before-rc` back. Put back what step 1 found: no `tradurre.exe` →
   `uv tool uninstall tradurre`; otherwise reinstall that version from its release wheel. Final `--version`
   matches step 1.
7. **By hand, for the developer** (not the agent): on the Italian layout, in the book screen of a fixture book,
   each key of `frontend/src/keys.ts` (letters, Shift+letters, arrows, Enter, Tab/Shift+Tab, Esc,
   Ctrl+Z/Y/X/C/V, Alt+↑/↓, Ctrl+Enter while editing, `h` for the panel) with what should happen, as a table with
   an empty "OK?" column. Also: the edition .docx opens in Word and the .txt in Notepad with accents right.

**Linux rehearsal** (Braun runs it; what can't run on Linux is said so in the report):
- Steps 2–3 for real: `HOME` set to a scratch folder (v0.1 has no `TRADURRE_DB`), v0.1.0 run with
  `uvx --python 3.14 --from "tradurre[pdf] @ <v0.1.0 wheel URL>" tradurre --no-browser --port 8124`, the project
  created with the checklist's request body; then the current code (`uv run tradurre --no-browser --port 8124`,
  same `HOME`): `/api/v2/books` is `[]` and the snapshot holds "Checklist v0.1".
- Step 5's requests, with `curl` (same paths, bodies and expected results as written in the checklist), against
  the current code.
- Every path, endpoint and testid in the checklist exists in the code (grep).

#### Release candidate wheel
Status: done
Report: 2026-10-04 — version 0.2.0rc1 (+ `uv lock`); `scripts/make_rc.py` builds `dist/tradurre-rc/` (wheel, launcher with VERSION and `file:///C:/tradurre-rc/tradurre-0.2.0rc1-py3-none-any.whl`, 98/98 CRLF lines, no placeholder; smoke.py, checklist, 4 fixtures) and `dist/tradurre-rc.zip` (folder at its root); checklist step 7 runs the candidate with `uvx` on `C:\tradurre-rc\by-hand\`, step 6 checks the release exists before reinstalling; smoke.py writes UTF-8; README "Releasing" line; the wheel installed with `uv tool install` into scratch tool folders prints `tradurre 0.2.0rc1` and the folder's smoke.py passed against it (output redirected); `dist/` ignored by uv's own `.gitignore`; pytest 386 passed.
**Done when:** `dist/tradurre-rc/` and `dist/tradurre-rc.zip` exist with exactly the files below; the launcher in
it has CRLF line endings, `VERSION=0.2.0rc1` and the `file:///C:/tradurre-rc/…` URL, and no `__` placeholder
left; the folder's wheel, installed as the launcher would (`uv tool install --python 3.14 "tradurre[pdf] @
file://<absolute path>"`, with `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` in the scratchpad), answers `tradurre --version` →
`tradurre 0.2.0rc1`, and `packaging/smoke.py` passes against it (installed `tradurre --no-browser --port 8123`,
`TRADURRE_DB` in the scratchpad: this is the first run of the SPA from a wheel); `uv run pytest` passes;
`git status` shows only the intended changes (nothing under `dist/`). Then stop the server and delete the scratch
tool folders and database (keep `dist/`).

The folder the developer copies to `C:\tradurre-rc\` for `packaging/WINDOWS-CHECKLIST.md`, plus two fixes to the
checklist from its review.
- **Checklist fixes** (`packaging/WINDOWS-CHECKLIST.md`):
  - Step 7 must not touch the developer's installed Tradurre or data (it ran after step 6, through the launcher:
    the installed tool replaced and their real database migrated). It runs the candidate without installing it, on
    a database of its own: `$env:TRADURRE_DB = "$RC\by-hand\tradurre.db"` then `uvx --python 3.14 --from
    "tradurre[pdf] @ file:///C:/tradurre-rc/$WHEEL" tradurre` (opens the browser; Ctrl+C ends it); afterwards
    `Remove-Item Env:TRADURRE_DB`. Nothing to restore after it; say so instead of "restore your setup".
  - Step 6, case `tradurre X`: if `https://github.com/yamatteo/tradurre/releases/tag/vX` doesn't exist (a
    development install), don't guess: record the step-1 output in the results and leave reinstalling to the
    developer.
- `packaging/smoke.py`: `sys.stdout.reconfigure(encoding="utf-8")` (and stderr) at the start of `main()`, so its
  output survives a redirect on Windows; the checklist keeps `PYTHONUTF8=1` (harmless, and covers uv's own Python
  messages).
- `pyproject.toml` `version = "0.2.0rc1"`; `uv lock` (the lock records the project version).
- `npm --prefix frontend run build`, then `uv build --wheel` → `dist/tradurre-0.2.0rc1-py3-none-any.whl` (uv writes
  a `.gitignore` of `*` into `dist/`; check it's there, so nothing below is ever committed).
- `scripts/make_rc.py` (committed; stdlib only): reads the version from `pyproject.toml` (`tomllib`); refuses
  (exit 1, a message) if `dist/tradurre-<version>-py3-none-any.whl` is missing or lacks
  `tradurre/static/index.html`; rebuilds `dist/tradurre-rc/` from scratch with: the wheel; `start-tradurre.bat`
  from `packaging/` with `__VERSION__` → the version and `__WHEEL_URL__` → `file:///C:/tradurre-rc/<wheel name>`,
  replaced on the **bytes** so the CRLF line endings survive (`.gitattributes`: cmd mis-parses LF batch files);
  `smoke.py` and `WINDOWS-CHECKLIST.md` from `packaging/`; `fixtures/` with the four `tests/fixtures/easy.*`
  files used by the checklist (`.source.docx`, `.target.pdf`, `.source.txt`, `.target.txt`). Then zips the folder
  as `dist/tradurre-rc.zip` (the folder itself at the zip's root, so unzipping into `C:\` gives
  `C:\tradurre-rc\`). Prints the file list.
- `README.md` "Releasing": one line on the candidate (`make_rc.py` and the checklist). No tag, no GitHub release:
  the candidate travels by hand.

#### First Windows run (0.2.0rc1)
Status: done
Report: 2026-10-04 — run by the Windows agent on **Windows 10 Pro 22H2** (not 11), PowerShell 5.1, uv 0.12.22,
Defender on; results in the developer's `RESULTS.md` (not committed). Steps 1, 2, 5, 6 PASS; v0.1 → rc1 upgrade,
snapshot and undo across a restart all good. Two failures, both reaching any user who runs the launcher:
1. **PDF import answers a bare 500**: the machine has no Visual C++ 2015–2022 Redistributable, `pymupdf`'s
   `_extra.pyd` needs `MSVCP140.dll` (Python brings only `vcruntime140*.dll`): `ImportError: DLL load failed while
   importing _extra`. Known PyMuPDF issue; the fix is the redistributable.
2. **uv can't replace an existing tool environment** (`failed to remove directory …\uv\tools\tradurre\Lib`, os
   error 32, every time, nothing running; deleting the folder by hand works; likely Defender scanning while uv
   deletes). The launcher then falls back to the half-deleted old install, which crashes (`cannot import name
   'Doc' from 'annotated_doc'`): the user is left with a broken Tradurre and no hint. The same error broke `uv run
   --with playwright` (greenlet's `.data` folder); the agent ran `smoke.py` from a plain venv instead, and it failed
   at the PDF import (issue 1), so 9 smoke steps didn't run. Step 7 (keys, by hand) not reached.
Checklist nits: v0.1.0 installs 2 executables (`tradurre`, `tradurre-align`), not 1. The browser tab says
"Vite App" (`frontend/index.html:7`).

Decided (user, 2026-10-04): the launcher **installs the VC++ Redistributable** when `MSVCP140.dll` is missing
(Windows asks once for administrator rights; on failure Tradurre starts anyway and prints the link), and the
server answers a missing PDF runtime with a clear message. On a failed install the launcher **deletes Tradurre's uv
tool folder and retries once**, and never falls back to an install that doesn't run.

#### PDF support that can't load: a clear message
Status: done
Report: 2026-10-04 — `extract.py`: `PDF_RUNTIME_MISSING` and `import pymupdf` wrapped so an `ImportError` becomes that `ValueError` (400, nothing written); `test_pdf_runtime_missing_is_explained_and_writes_nothing` failed on the old import (`ModuleNotFoundError` raised through the request) and passes; pytest 387 passed.
**Done when:** the new test fails on the current code (check by restoring it) and passes after; `uv run pytest`
passes.

- `services/extract.py` `_extract_pdf`: `import pymupdf` inside `try`/`except ImportError` → `raise
  ValueError(PDF_RUNTIME_MISSING)`, a module constant: "PDF support can't load on this computer. Install the
  Microsoft Visual C++ Redistributable (https://aka.ms/vs/17/release/vc_redist.x64.exe), then restart Tradurre.
  Text and Word files still work." The existing `ValueError` path of the import (`api/books.py:66`) answers 400 with
  it, and writes nothing. Nothing else changes (`glyph_resolver`'s `import fitz` runs only after this import).
- `tests/test_books_api.py`: `monkeypatch.setitem(sys.modules, "pymupdf", None)` (makes the import raise
  `ImportError`), import a .pdf + .txt pair → 400, `detail` is the constant, `GET /books` is `[]`; a .txt pair
  still imports (201).

#### Launcher: the VC++ runtime and a sturdier upgrade
Status: done
Report: 2026-10-04 — `start-tradurre.bat`: `:uv_install` (uv output to `%TEMP%\tradurre-install.log`, then shown), delete-and-retry only when the log has `failed to remove directory`, `:install_failed`, `:fail_update` starts the old version only if `tradurre.exe --help` runs, else `:fail_broken`; `:run` checks `msvcp140.dll` and calls `:ensure_vcredist` when `EXTRAS` has `pdf`; header comment; 175/175 CRLF lines, `git ls-files --eol` `w/crlf`; the release workflow's sed and placeholder check pass on a copy; `make_rc.py` builds the folder; not run in cmd (Linux), paths walked in the report; pytest 387 passed.
**Done when:** `git ls-files --eol packaging/start-tradurre.bat` still says `w/crlf`; the report walks the three
upgrade paths through the final file (removal failure → retry; offline failure → old install starts; old install
broken → the new message) and the runtime check's paths (present, installed, declined/failed); the release workflow's
substitution still works (run its two `sed` expressions from `.github/workflows/release.yml` on a copy and its
placeholder `grep` finds nothing); `uv run python scripts/make_rc.py` still builds the folder (after a wheel
build); the report quotes the final `:run`, `:install_tradurre` and new labels. cmd can't run here: the real
check is the next Windows run, so keep every new line simple and commented, in the file's style.

`packaging/start-tradurre.bat`:
- **VC++ runtime**, every start, just before `tradurre.exe %*` at `:run`: if `EXTRAS` contains `pdf` and
  `%SystemRoot%\System32\msvcp140.dll` doesn't exist, `call :ensure_vcredist`. It prints what it does and that
  Windows will ask for permission; downloads `https://aka.ms/vs/17/release/vc_redist.x64.exe` to `%TEMP%` with
  `curl.exe -fsSL`; runs it `/install /passive /norestart`; deletes it; exit codes `0`, `3010` (restart
  suggested) and `1638` (a newer one is installed) are success; anything else, or a failed download, prints that PDF
  import won't work until it's installed by hand, with the link, and Tradurre starts anyway (`exit /b 0`). (This
  is the patch the Windows agent dry-ran in `RESULTS.md`; x64 only, which is what uv's Python is.)
- **Upgrade**: run `uv.exe tool install` with its output redirected to `%TEMP%\tradurre-install.log`, then
  `type` the log (so the user still sees it). When it fails **and** the log contains `failed to remove directory`
  (`findstr /c:"failed to remove directory"`: the os error 32 of the Windows run, which leaves the old environment
  half-deleted, so there is nothing left to keep), find uv's tool folder (`for /f "delims=" %%d in ('uv.exe tool
  dir 2^>nul')`), `rmdir /s /q` its `tradurre` subfolder (uv's environment only; the books are in
  `%USERPROFILE%\.tradurre`), print that it is retrying, and run the same install once more (same log handling).
  Any other failure (offline, a bad download) deletes nothing: the old install is still whole, and the existing
  fallback to it stays.
- **No broken fallback**: before `:fail_update`'s "Starting the installed version instead", check that
  `tradurre.exe --help` runs (errorlevel 0; `--help`, not `--version`, which v0.1.0 lacks; both versions' `__main__` import `tradurre.app`, so
  `--help` loads FastAPI, which is what crashed); if it doesn't, a new
  label prints that Tradurre couldn't be installed, that the books are safe in `%USERPROFILE%\.tradurre`, to close
  any Tradurre window and run the file again (and the uv and Tradurre install links), then `pause` and `exit /b 1`.
- The header comment mentions the runtime and the retry.

#### Checklist fixes and candidate rc2
Status: done
**Done when:** as for "Release candidate wheel" above, with `0.2.0rc2`: the folder's wheel installed into
scratch tool folders answers `tradurre 0.2.0rc2`, the folder's `smoke.py` passes against it, the browser tab of
the built SPA reads "Tradurre"; `uv run pytest` passes.

- `frontend/index.html`: `<title>Tradurre</title>`.
- `packaging/WINDOWS-CHECKLIST.md`:
  - "Windows 10 or 11" wherever it says Windows 11.
  - Step 1 also records `Test-Path "$env:SystemRoot\System32\msvcp140.dll"`. If `False`, the **developer must be
    at the machine for step 3**: the launcher (hidden) installs the runtime and Windows' permission prompt waits
    for a click. The agent tells the developer before step 3, records whether it was installed and the launcher's
    lines about it; step 3 then also expects `msvcp140.dll` to exist.
  - Step 2 expects `Installed 2 executables: tradurre, tradurre-align`.
  - Step 3's log check also greps `Retrying` (the uv retry) and records whether it happened.
  - Step 4: if `uv run --with playwright` fails with os error 32, the fallback the agent used: `uv run
    --no-project --python 3.14 python -m venv "$RC\pw"`, `& "$RC\pw\Scripts\python.exe" -m pip install
    playwright`, then run `smoke.py` with that Python; record which way it ran.
  - Step 6: if `uv tool uninstall` fails with os error 32, delete uv's `tradurre` tool folder (`uv tool dir`) and any
    `tradurre*.exe` left in `%USERPROFILE%\.local\bin` that step 1 didn't find.
  - A new step between 5 and 6, **a pdf import through the API** (`curl.exe -F` with `easy.source.docx` +
    `easy.target.pdf`) → 201, 28 beads, then delete it: the runtime check without a browser.
  - Another new step after it, **the launcher's failure paths**, with Tradurre stopped and a copy of the launcher
    (`$RC\logs\launcher-test.bat`, made in PowerShell with `-replace` on `VERSION=…` → `VERSION=0.2.0rc99` and
    the `WHEEL_URL` → `file:///C:/tradurre-rc/missing.whl`, saved with `-Encoding ASCII`, CRLF kept): (a) run it
    `--no-browser` hidden as in step 3 → the log shows "Could not update Tradurre" and "Starting the installed
    version instead" and the app answers (an offline-like failure deletes nothing); stop it. (b) rename uv's
    `tradurre\Lib\site-packages\fastapi` folder (`uv tool dir`) to `fastapi.off`, run the copy again → the log shows
    "Tradurre could not be updated" and "Your books are safe" (each on one line of the launcher's output) and nothing answers on 8000; rename it back, and `tradurre.exe
    --help` exits 0 again. Record both logs' relevant lines.
- `version = "0.2.0rc2"`, `uv lock`, build, `uv build --wheel`, `uv run python scripts/make_rc.py`.

Report: 2026-10-05 — tab title "Tradurre"; checklist: Windows 10 or 11, runtime check in step 1, 2 executables, `Retrying` grep, venv fallback for playwright, new step 6 (PDF import via API) and step 7 (launcher failure paths), uninstall fallback in step 8, the manual keys now step 9; 0.2.0rc2 built and assembled (launcher CRLF 175/175); the folder's wheel in scratch tool folders answers `tradurre 0.2.0rc2`, serves `<title>Tradurre</title>`, the folder's smoke.py passes 11/11; pytest 387 passed.

#### Second Windows run (0.2.0rc2)
Status: done
**Done when:** the developer brings back the rc2 folder's `RESULTS.md` (steps 1–8 by the Windows agent, step 9
by hand on the Italian layout) and `/pauli` records it here, as for the first run (counts and messages only).

- Copy `dist/tradurre-rc.zip` (rc2: `tradurre-0.2.0rc2-py3-none-any.whl`) and unzip it into `C:\`, replacing the
  rc1 folder; move the old `RESULTS.md` out of `C:\tradurre-rc\` first.
- Windows 10, the machine without the VC++ runtime: **be at the machine for step 3** to click Windows' permission
  prompt (the agent asks first). Step 3 is the real test of the runtime install and of uv's retry; step 7 of the
  two failure paths.
- What counts as a pass for v0.2.0: steps 1–8 PASS (a `Retrying` line in step 3 is fine; the `pw` venv fallback in
  step 4 is fine), step 9 all OK. Any FAIL comes back here as a fix task and an rc3.

Report: 2026-10-05 (Pauli, from the developer's `RESULTS.md`, not committed) — run 2026-10-04 on Windows 10 Pro
19045, the machine without the runtime, nothing installed and no data before. **Passes the bar: steps 1–8 PASS,
step 9 all OK.** Step 3: v0.1.0 → rc2 upgrade; uv's os error 32 hit again and the launcher's retry fixed it; the
VC++ runtime was installed (the developer clicked "Yes"; `msvcp140.dll` False → True). Step 4: `uv run --with
playwright` hit os error 32 again (greenlet in uv's build cache), so the `pw` venv fallback; Edge and Chrome 11/11.
Steps 5–6: 28 beads both pairs, PDF through the API fine. Step 7: (a) and (b) as expected. Step 8: `uv tool
uninstall` hit os error 32; the checklist's fallback worked. Small findings, none blocking (see "After v0.2"):
- the upgrade from v0.1.0 by delete-and-retry leaves v0.1's `tradurre-align.exe` in `.local\bin` (the deleted
  folder took uv's record of it); harmless, it only fails if someone types it;
- after the runtime installs, the launcher prints nothing to say it worked;
- the checklist's `Wait-Tradurre` counts passes, not seconds: on Windows a refused localhost connection takes ~2 s,
  so `120` waited ~6 minutes.
Not covered by either run: a **first install** on a machine with no Tradurre, through an `https://` wheel URL;
the post-release check below covers it.
#### Release 0.2.0
Status: done
**Done when:** `pyproject.toml` says `version = "0.2.0"` and `uv.lock` matches (`uv lock --check` exits 0); `git
diff 8362681 -- . ':!PLAN.md'` shows only those two files' version lines (what ships is the code rc2 tested);
`npm --prefix frontend run build` and `uv build --wheel` give `dist/tradurre-0.2.0-py3-none-any.whl`, which,
installed into scratch tool folders (`UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` in the scratchpad), answers `tradurre
0.2.0`; `uv run pytest` passes; committed.

- Ship rc2 as tested: **no other change**, not to the launcher, not to the checklist; the findings of the second
  run wait (see "After v0.2"). Don't run `make_rc.py`.
- Don't merge, tag or push: in the chat report, give the developer these commands, to run from the repo root
  (Pauli's recommendation to the user, 2026-10-05: fast-forward `main`, then tag; `main` is an ancestor of `toward-v0.2`, so no
  merge commit and the tag is on exactly the commit Braun made):

  ```sh
  git checkout main
  git merge --ff-only toward-v0.2
  git push origin main
  git tag v0.2.0
  git push origin v0.2.0
  ```

Report: 2026-10-05 — `version = "0.2.0"`, `uv lock` (`--check` exits 0); since 8362681 only the two version lines changed; `dist/tradurre-0.2.0-py3-none-any.whl` in scratch tool folders answers `tradurre 0.2.0`; pytest 387 passed; committed, and `main` fast-forwarded to it locally at the user's request (not pushed, not tagged).

#### After the tag: the published launcher
Status: todo — **the developer's**, after the `Release` workflow has published v0.2.0: Braun skips it.
**Done when:** the developer reports back, and `/pauli` records it here.

On the Windows machine, which now has no Tradurre and no data (as the second run left it): download
`start-tradurre.bat` from the release page with the browser and double-click it. Expected: SmartScreen's "More
info → Run anyway" (README), uv already there, `Tradurre 0.2.0 is installed.`, no runtime prompt (installed in the
second run), the browser opens on the library; import `easy.source.docx` + `easy.target.pdf` (the rc folder's
`fixtures\`) → 28 beads; close the window; double-click again → it starts without updating. This is the first
install from nothing over `https://`, which neither run covered.

---

## After v0.2

Agreed (user, 2026-10-04), postponed until after v0.2:
- **Better problem signals.** Measured on the reference book (Pauli, 2026-10-04, counts only): of 1232 imported
  beads, 15 differ from the gold; **none** of them is flagged (their confidence is 0.73–1.00), the 9 flagged beads
  are all right, and "Highlight multi-segment" (20 beads) catches 3 of the 15. Problem-first navigation therefore
  finds false alarms and misses the real errors: review stays reading-first. Candidate signals, each scored
  against the gold (errors caught / beads flagged): numbers, names and punctuation (`?`, `!`, guillemets,
  dialogue dashes) that differ across sides; a bead's length ratio out of line with its neighbours.
- **Reading optimization** of the review screen (comfort and speed of a top-to-bottom read).
- The translator's own review of *Contrefeu* (in v0.2) becomes the gold these are scored against.
- **Launcher and checklist touch-ups** from the second Windows run (2026-10-04): after uv's delete-and-retry,
  delete old commands the deleted folder no longer accounts for (v0.1's `tradurre-align.exe` in uv's bin folder);
  echo a line when the VC++ runtime installed; `Wait-Tradurre` waits until a deadline (`(Get-Date).AddSeconds`)
  instead of counting passes. With the next release candidate, not before.
- Small cleanup: `glyph_resolver.py`'s LLM paths (`generate`, `_check_substitution_plausible`,
  `llm_resolve_remaining_markers`) had their only caller in the removed Colab pipeline; `extract.py` never passes
  `generate`. Remove them, or keep them for an unparked aligner.
