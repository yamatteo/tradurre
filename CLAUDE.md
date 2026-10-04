# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`tradurre` is a local-first workbench for aligning a literary corpus: a FastAPI backend and a Vue 3 frontend that
import a book and its translation (.txt/.docx/.pdf), align them sentence by sentence into beads, let the
translator review and correct the alignment, and search every book at once (SQLite + FTS5). `SPEC.md` describes the
product; `PLAN.md` holds the staged plan from the code to that spec. The architecture notes below describe the code
as it is.

## Workflow

Work is split between two roles, each available as a skill:

- **`/pauli` — planner/reviewer.** Reads `SPEC.md`, reviews the code against it, and updates `PLAN.md`: stages
  (`##`), split into steps (`###`) and further sub-steps as needed, until each leaf is a task one agent can finish
  and verify in a single session. Reviews what `/braun` reported. Edits only `PLAN.md` (and `SPEC.md` when the
  user agrees to a change); never touches code.
- **`/braun` — implementer.** Reads `PLAN.md`, takes **one** task (the next `todo` one, or the one named), carries
  it out, verifies it, records a `Report:` line under the task in `PLAN.md` and reports back. Stops and asks
  instead of improvising when the task is unclear or reality doesn't match the plan.

`SPEC.md` changes only with the user's agreement. Task format and statuses are defined under "Conventions" at
the top of `PLAN.md`. Without an explicit role, keep the same discipline: if a change doesn't fit the plan, say
so rather than silently diverging from it.

## Commands

Backend (run from repo root, Python 3.14, managed with `uv`):
```sh
uv run tradurre --dev        # start the app with auto-reload (http://127.0.0.1:8000); takes no database snapshots
uv run tradurre              # end-user mode: no reload, opens the browser
uv run pytest                # run all backend tests (`-m library` ones run only where library/contrefeu.*.pdf exists)
uv run pytest tests/test_search.py                         # single test file
uv run pytest tests/test_books_corrections_api.py -k undo  # tests by name
```

Frontend (run from `frontend/`):
```sh
npm run dev          # Vite dev server on :5173, proxies /api to :8000 (see vite.config.ts)
npm run build         # type-check (vue-tsc) + production build into ../tradurre/static
npm run type-check    # vue-tsc --build only (covers e2e/ too)
npm run test:e2e      # Playwright e2e tests (e2e/*.spec.ts) on a throwaway backend (:8001, .e2e.db) and Vite :5174;
                      # the timing tests (e2e/scale.spec.ts) run last, alone
```

In production, `tradurre/app.py` serves the built SPA from `tradurre/static/` (gitignored) directly off the
FastAPI process — run `npm run build` before relying on the backend to serve frontend routes. `tradurre/static/`
is included in the wheel via hatch `artifacts`; `.github/workflows/release.yml` builds and publishes the wheel
(plus the self-installing Windows launcher `packaging/start-tradurre.bat`, with the wheel URL substituted
for `__WHEEL_URL__`) to a GitHub Release when a `v*` tag is pushed.

## Architecture

```
Browser ── Vue 3 SPA ──/api/v2──▶ FastAPI ──▶ SQLite (~/.tradurre/tradurre.db) + FTS5
```

### Backend (`tradurre/`)

- `__main__.py` — the `tradurre` command (`--dev`, `--no-browser`, `--port`). `config.py` — `DB_PATH`
  (`TRADURRE_DB` overrides it), host and port.
- `app.py` — FastAPI app, CORS (allows `localhost:5173` for dev), the books router under `/api/v2`, SPA static
  mount. Its lifespan takes a database snapshot (`backup.py`, skipped when `TRADURRE_DEV` is set, which `--dev`
  does) and then runs `init_db`.
- `backup.py` — `snapshot()`: copies the database into `backups/` next to it at each start, keeping the last 10.
- `db.py` — raw `sqlite3` connection (no ORM). Schema lives here as inline SQL strings. Schema changes are
  migrations: append a function to `MIGRATIONS` in `db.py` (never edit an applied one); `init_db` runs the pending
  ones, each in its own transaction, and records the count in `PRAGMA user_version`. Use `_run_script`, not
  `executescript`, inside a migration. Migration 1 builds the v0.1 schema and migration 6 drops it: keep both.
- `models.py` — all Pydantic request/response models in one file.
- `api/books.py` — the whole HTTP API: import (`POST /books`), library (`GET /books`), read a book, the
  corrections (`/books/{id}/beads/…`, `/segments/…`, `/blocks/…`, `/reviewed`, `/undo`, `/redo`), search
  (`/search`, `/search/books`, `/books/{id}/beads/{bead}/context`), exports (edition, bundle), bundle restore
  (`POST /books/bundle`), `DELETE /books/{id}`, `/check` and `/runs`. Handlers get a per-request connection via
  `db: sqlite3.Connection = Depends(get_db)`; write handlers run the domain inside `with transaction(db):`
  (`domain/history.py`).
- `domain/` — the model's operations, independent of HTTP:
  - `layer.py` — building a book's text and alignment layers in bulk (import, restore, tests); `GAP` spacing.
  - `ordering.py` — sparse integer `ord`s for sibling rows (insert between neighbours, renumber when full).
  - `beads.py`, `segments.py`, `blocks.py` — the corrections: move a segment across a bead boundary, merge/split
    beads, mark reviewed, edit/split/join/restore segment text, exclude/include blocks and ranges.
  - `replace.py` — replace a run of beads in bulk (re-align).
  - `history.py` — the operation log: every write goes through a `Recorder`; `undo`/`redo` replay row snapshots.
    `transaction(conn)` starts `BEGIN IMMEDIATE` with deferred foreign keys.
  - `invariants.py` — `check_project`: the alignment invariants I1–I5 (see its docstring).
  - `search.py` — FTS5 query building (word beginnings, sides) and search/count over `bead_index`, grouped by
    book in library order (`BOOK_ORDER`).
- `services/` — the import pipeline and the files in and out:
  - `extract.py` — files in, kinded blocks out (.txt, .docx, layout-aware .pdf), with OCR/ligature cleanup;
    `matter.py` — front and back matter; `glyph_resolver.py` — characters a PDF's font mapping mangles.
  - `segment.py` — French/Italian sentence segmentation; `align.py` — the local aligner (anchors plus sentence
    length); `build.py` — two extractions to a book; `realign.py` — re-run the aligner on a stretch of beads.
  - `edition.py` — one side's reviewed text as .txt/.docx; `bundle.py` — one book as a versioned zip, and
    restore; `gold.py` — the gold book the pipeline is scored against.
- `scripts/` — `gold_export.py`, `gold_score.py` (score the pipeline against the gold), `search_scale.py` (search
  timing on a synthetic library).

### Data model

`projects` (one per book; a book always has both its `documents`) → `documents` (one per side) → `blocks`
(`kind`, `excluded`, `ord`) → `segments` (`text`, `original_text` as extracted, `bead_id`). `beads` (`ord`,
`confidence`, `method`, `reviewed`) belong to the project; a segment points at its bead, and a segment has a bead
iff its block is not excluded. Order is by sparse `ord` columns (see `domain/ordering.py`), unique per parent.
`operations` holds the undo log; `runs`/`warnings` record what each import did. All of a book's rows go when its
`projects` row is deleted (`ON DELETE CASCADE`).

The `bead_index` FTS5 table is kept in sync with `segments` and `beads` by SQL triggers — never write to it
directly; change segments and beads and the triggers handle it.

### Frontend (`frontend/src/`)

- `views/` — one component per route, wired in `router/index.ts`: `ProjectList` (`/`, the library), `BookImport`
  (`/book/import`), `BookView` (`/book/:id`, the review screen), `BookSearch` (`/search`).
- `components/` — the book screen's parts: `BeadRow`, `BeadActions`, `BookPosition`, `BookStatus`, `KeysPanel`,
  `MoreMenu`, `OriginalPopover`.
- `keys.ts` (every key the book screen handles, for the shortcuts panel and the key handler; the e2e specs read it
  too), `selection.ts` (the current bead and selected runs, provided by `BookView`), `review.ts` (which beads are
  likely problems); `composables/` (`useDebounce`).
- `api/client.ts` — `booksApi`, the fetch wrapper for `/api/v2`, and its types (mirroring `models.py`).
- Tailwind v4 via `@tailwindcss/vite` (no separate `tailwind.config.js`); the design tokens (design variant A) are
  in `assets/main.css` `@theme`.
