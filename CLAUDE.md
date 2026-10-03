# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`tradurre` is a local-first literary translation workbench: a FastAPI backend + Vue 3/TipTap frontend for
paragraph/sentence-aligned source↔target editing, with SQLite+FTS5 powering full-text "translation memory"
search across all past projects. `SPEC.md` describes the product as it **should be** (an alignment/corpus tool
first); `PLAN.md` holds the staged plan from the current code to that spec. The architecture notes below describe
the code **as it is now**, which the plan is replacing.

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
uv run tradurre --dev        # start the app with auto-reload (http://127.0.0.1:8000)
uv run tradurre              # end-user mode: no reload, opens the browser
uv run pytest                # run all backend tests
uv run pytest tests/test_aligner.py            # single test file
uv run pytest tests/test_pairs_api.py -k insert  # single test by name
```

Frontend (run from `frontend/`):
```sh
npm run dev          # Vite dev server on :5173, proxies /api to :8000 (see vite.config.ts)
npm run build         # type-check (vue-tsc) + production build into ../tradurre/static
npm run type-check    # vue-tsc --build only
npm run test:e2e      # Playwright e2e tests (e2e/*.spec.ts); auto-starts `npm run dev`
```

In production, `tradurre/app.py` serves the built SPA from `tradurre/static/` (gitignored) directly off the
FastAPI process — run `npm run build` before relying on the backend to serve frontend routes. `tradurre/static/`
is included in the wheel via hatch `artifacts`; `.github/workflows/release.yml` builds and publishes the wheel
(plus the self-installing Windows launcher `packaging/start-tradurre.bat`, with the wheel URL substituted
for `__WHEEL_URL__`) to a GitHub Release when a `v*` tag is pushed.

## Architecture

```
Browser ── Vue 3 SPA (TipTap editors) ──/api──▶ FastAPI ──▶ SQLite (~/.tradurre/tradurre.db) + FTS5
```

### Backend (`tradurre/`)

- `app.py` — FastAPI app setup, CORS (allows `localhost:5173` for dev), router registration, SPA static mount.
- `db.py` — raw `sqlite3` connection (no ORM). Schema lives here as inline SQL strings (`_SCHEMA`, `_FTS_SCHEMA`,
  `_FTS_TRIGGERS`), applied via `init_db()` on startup. Schema changes are migrations: append a function to `MIGRATIONS` in
  `db.py` (never edit an applied one); `init_db` runs the pending ones, each in its own transaction, and records
  the count in `PRAGMA user_version`. Use `_run_script`, not `executescript`, inside a migration.
- `models.py` — all Pydantic request/response models in one file.
- `api/` — one router module per resource (`projects.py`, `pairs.py`, `search.py`, `import_.py`, `export.py`).
  Handlers get a per-request connection via `db: sqlite3.Connection = Depends(get_db)` (`db.py`); write handlers
  wrap their work in `with db:` starting with `db.execute("BEGIN IMMEDIATE")`.
- `services/aligner.py` — the core text-alignment pipeline: strips artifact lines (page numbers), rejoins
  line-wrapped paragraphs, splits into sentences, finds "anchor" tokens (capitalized names/phrases with matching
  occurrence counts in source and target) and uses them to align source/target sentence sequences. Used by the
  import flow to auto-align raw `.txt`/`.docx` pairs before the user manually adjusts them.
- `services/importer.py` — `.docx`/`.txt` paragraph extraction feeding into the aligner.
- `services/html_utils.py` — HTML↔plain-text conversion (pairs store both `*_html`, for TipTap, and `*_text`,
  for FTS indexing — keep these in sync when creating/updating pairs).

### Data model

`pairs` rows are the atomic unit: one (source_html, target_html) pair per position, scoped to a `project_id`,
ordered by `position`, with `section`/`paragraph` columns tracking hierarchical structure (multiple pairs can
share a section/paragraph). The `translation_memory` FTS5 table is kept in sync with `pairs` via SQL triggers
(`pairs_ai`/`pairs_au`/`pairs_ad`) — never write to `translation_memory` directly, insert/update/delete `pairs`
and the triggers handle it.

Reordering pairs within a project uses a two-step negative-position shift (see `create_pair` in `api/pairs.py`)
to dodge the `UNIQUE(project_id, position)` constraint when shifting a contiguous range — replicate that pattern
for any other operation that reindexes positions.

### Frontend (`frontend/src/`)

- `views/` — one component per route (`ProjectList`, `ProjectEditor`, `ImportWizard`, `SearchView`), wired in
  `router/index.ts`.
- `api/client.ts` — fetch wrapper for the backend.
- `ProjectEditor.vue` hosts the TipTap-based aligned source/target editing surface; `ImportWizard.vue` drives
  the upload → align-preview → confirm import flow, letting the user manually fix up the aligner's output.
- Tailwind v4 via `@tailwindcss/vite` (no separate `tailwind.config.js`).
