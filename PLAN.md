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

## Current state, in brief (2026-10-04)

- **Two models coexist until Stage 7.** The v0.1 `pairs` table, its `/api/v1` API, import wizard, TipTap pair
  editor and `aligner.py` still exist, unused by the new path. The new model (migrations 2–5: documents, blocks,
  segments, beads, operations, `bead_index`, runs, warnings) is served by `/api/v2/books` (`api/books.py`) and the
  book screen (`BookView.vue`, `/book/:id`).
- **Import** (Stage 3): .txt/.docx/.pdf pairs. Layout-aware PDF extraction, front/back matter by publishing
  markers, French/Italian segmentation, the length aligner; the run's stats and warnings are stored and shown
  under "Import log". Reference book: ~5 s, 1232 beads, 2 one-sided, 9 below confidence 0.5; against the gold,
  alignment F1 0.995, exclusion P 1.000 R 0.902.
- **Book screen** (Stages 2, 4): reading and keyboard navigation, `n` next unreviewed, `r` reviewed, "Show
  excluded", every SPEC §3.3 single-bead correction (keys and header buttons), inline segment editing, persistent
  undo/redo, problem navigation (`p`/`P`), selected runs (Shift+↑/↓, Shift+click) marked with `r`, and `R` "up to
  here", range exclude/include in the "More" menu, edited sentences marked with their original on `o` and
  "Restore original", re-align of the selection (More menu), cut/copy/paste of whole sentences (Ctrl+X/C/V).
  Restyled to design variant A; smooth at 5,000 beads. Stages 4 and 6 done (search at `/search` and from the book; More → Export: edition .txt/.docx and the
  project bundle; "Restore a bundle" on the library page). Stage 7: search grouped by book and the library order
  done, and database snapshots (local-time names); next retire v1 (4 tasks), a Windows checklist, then the v0.2 tag. On the reference book the problem flags catch
  none of the 15 real errors: review is reading-first; better signals come after v0.2.
- **Re-planned with the user (2026-10-04), SPEC changed accordingly:** review is one mode, problem-first: jump to
  the next likely problem, correct, mark one bead, a selected run, or everything up to here as reviewed. The
  timed scroll "skim review" is dropped. The Colab aligner is **parked** (SPEC §3.2, §5): it returns only if a
  gold book scores below 0.95. A typical book is 1,000–5,000 sentences a side; performance targets are at 5,000
  beads. Order: Stage 6 → Stage 7 (v0.2), confirmed 2026-10-04. Then the translator reviews *Contrefeu* in v0.2 for a true
  gold (the current one was made by the user, the developer), and maybe a second book, to score the aligner again.
- `uv run pytest`: 448 passed, also on a fresh clone (tests read only committed synthetic fixtures; `-m library`
  tests run only where `library/contrefeu.*.pdf` exists, and assert counts only).
- `npm run type-check` passes; releases build with `npm run build`. `npm run test:e2e` (70 tests; the three timing tests run last, alone, in project `scale`) runs on its own
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
Status: todo
**Done when:** `npm run type-check` and `npm run build` pass; `npm run test:e2e` passes; `grep -rn
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
- The backend is not touched (the v1 API stays until the next task).

#### Remove the v1 backend and the old Colab aligner
Status: todo
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

#### CLAUDE.md and README describe v0.2
Status: todo
**Done when:** every module, command, route and table named in `CLAUDE.md` exists (check each with `ls`/`grep`,
list the checks in the report); nothing in `CLAUDE.md` or `README.md` names `pairs`, `/api/v1`, TipTap, the import
wizard or translation memory.
- `CLAUDE.md` "Architecture": the code as it is now: `api/books.py` (`/api/v2`), `domain/` (layer, beads, blocks,
  segments, history/undo, invariants, search), `services/` (extract, matter, segment, align, build, realign,
  edition, bundle, gold, glyph_resolver), `backup.py`; the data model (projects → documents → blocks → segments,
  beads, operations, runs/warnings, `bead_index` kept by triggers: never write to it); the migration rule stays;
  the frontend views (`ProjectList`, `BookImport`, `BookView`, `BookSearch`) and components. Drop the v1 data
  model paragraph and the negative-position reindexing note. Keep "Workflow" and "Commands" (fix the example test
  names to existing files). The intro sentence saying the architecture notes describe code "the plan is
  replacing" goes.
- `README.md`: the intro speaks of books (import a source and its translation, review the alignment, search
  everything); no "translation memory" wording, no edit-both-sides-in-an-editor claim.

### Windows checklist and release
Not ready (written once the old model is gone; the checklist's "upgrade from v0.1" step means: a v0.1
database opens and loses its v1 projects, as agreed). `packaging/WINDOWS-CHECKLIST.md`, written for the Claude agent
on the developer's Windows machine: each step a command or browser action and its expected result (fresh install
through the launcher from the release candidate's wheel, upgrade from v0.1, Edge and Chrome, the Italian-layout
keys of the book screen, import of a .txt/.docx/.pdf pair, corrections and undo after a restart, search,
edition export, bundle download and restore, a snapshot in `backups`). No *Contrefeu* text in it. Then tag v0.2.0.

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
