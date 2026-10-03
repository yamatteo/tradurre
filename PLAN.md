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
- The new model exists below the API, unused by it yet: migrations 2–3 (documents/blocks/segments/beads,
  operations) and `tradurre/domain/` (layer builder, invariant checker, every SPEC §3.3 correction with
  persistent undo/redo, replace beads), covered by unit tests and a randomized round trip.
- Python 3.14 only (`.python-version`, `requires-python`, launcher). Stage 0 is complete.
- `uv run pytest`: 173 passed, 1 skipped, also on a fresh clone (tests read only committed synthetic fixtures).
- `uv.lock` is tracked; `pytest`/`httpx` are in the `dev` group. The Windows launcher's `uv tool install` resolves
  from PyPI and never reads the lock.
- `npm run type-check` passes; releases build with `npm run build`. Playwright's Chromium is not installed on the
  dev machine, so `npm run test:e2e` and browser checks can't run here until `npx playwright install chromium`.
- No user data needs migrating: the new model can start from an empty database.
- A real book pair is available **locally only**: `library/contrefeu.fr.pdf` / `contrefeu.it.pdf` (gitignored,
  copyrighted: never commit it or excerpts of it; the repo is public). See "Reference book" in Stage 2.

---

## Stage 0 — Groundwork

Make the repo a safe place to rebuild in, without changing product behaviour.

### Fix aligner recursion
Status: done
**Done when:** `align` / `_align_gap` in `tradurre/services/aligner.py` always terminate, a new regression test
proves it, and the only failures left in `uv run pytest` are tests that read the new fixtures (expected: none).
Report: 2026-10-03 — `_align_gap` recurses only on anchors that are singletons on both sides, else pads; docstring fixed; added `test_repeated_anchors_terminate`; pytest 70 passed, 1 skipped (was 9 failed).

Found while doing "Test fixtures": `align(["Hello Marie.", "Bye Marie."], ["Ciao Marie.", "Addio Marie."],
["Marie"])` raises `RecursionError`. `align` (`aligner.py:483`) only turns anchors occurring **once per side**
into constraints; when every anchor repeats, the only gap is the whole input, and `_align_gap` (`:448-450`) finds
the same anchors and calls `align` on identical lists, forever. The termination argument in `_align_gap`'s
docstring is false. This is live code: `importer.py:70` (`smart_align`) and `api/pairs.py` (`_align_units`)
call it, so any import whose only shared names repeat crashes.

- Fix in `_align_gap` only: after `find_anchors(s_gap, t_gap)`, keep the anchors that occur in exactly one unit
  of `s_gap` and exactly one unit of `t_gap`; call `align(s_gap, t_gap, those)` only if at least one remains,
  otherwise `return _pad_align(s_gap, t_gap)`. (A singleton constraint always survives `align`'s monotonic filter
  as the first one, so every recursion strictly shrinks the gaps.) Rewrite the docstring's termination
  argument to match.
- Don't change `align`, `find_anchors` or any existing test.
- Add `TestAlign::test_repeated_anchors_terminate` in `tests/test_aligner.py`: the call above returns
  `[("Hello Marie.", "Ciao Marie."), ("Bye Marie.", "Addio Marie.")]`.
- Leave the uncommitted fixture work from "Test fixtures" (`tests/fixtures/`, `tests/test_aligner.py` path
  change) in place; it is needed to run the module.

### Test fixtures
Status: done
**Done when:** on a fresh clone, `uv run pytest` collects every test file and passes, with no file read
from `library/`.
Verified (/pauli, 2026-10-03): `git clone` into a scratch dir, `uv run pytest` → 70 passed, 1 skipped. The
`.gitignore` step was not done; moved to "Repo hygiene".
Report: 2026-10-03 — blocked: fixtures written and `test_aligner.py` now collects (60 passed, 1 skipped), but 9 aligner tests fail with RecursionError in `aligner.py` (`align` ↔ `_align_gap`), including fixture-free ones (`test_align_sentences`, `test_align_sections_equal_count`): when every anchor repeats, `align` builds no constraints and `_align_gap` re-calls `align` on the same lists. Pre-existing bug, hidden by the collection error; fixing it is outside this task.
Resolution (/pauli, 2026-10-03): fixture files and the `LIBRARY` change were reviewed and are kept. After "Fix
aligner recursion", what remains is the `.gitignore` step, then the full suite. If one of the 9 formerly
crashing tests then fails because of the fixture text, adjust the fixtures, not the assertion.

Today `tests/test_aligner.py:24-26` reads `library/easy.source.txt` / `easy.target.txt` at import time, so
the whole module fails to collect (the other 26 tests pass; 1 is skipped). The repo is **public** on GitHub and
`library/` does not exist locally, so excerpts of the real books are neither possible nor allowed: write
**synthetic** French/Italian text.

- Add `tests/fixtures/easy.source.txt` (French) and `tests/fixtures/easy.target.txt` (its Italian translation),
  UTF-8, a few dozen lines each. Required properties, taken from the current assertions:
  - prose already clean (≥ 90% of non-blank lines survive `clean_lines`), no standalone chapter numbers or
    headings, so `_detect_sections` sees one section;
  - more than 5 paragraphs (blank-line separated, with some paragraphs wrapped over several lines) and more than
    20 sentences per side;
  - source starts with "Le premier incendie", target with "Il primo incendio";
  - "Guillaume", "Pontorgueil", "Sainte-Guénulphe" and "Sibylle Stoltz" occur the **same number of times** on
    both sides, and at least one source sentence and its aligned target sentence both contain "Guillaume";
  - "Ligné" occurs only in the source, "Ardent" only in the target;
  - the two sides have different sentence counts (so padding occurs).
- In `test_aligner.py` change only `LIBRARY` (to `Path(__file__).parent / "fixtures"`) and the docstring/comments
  that mention `library/` or "MarieAnge"/PDF artefacts. Do not change any assertion or `aligner.py`; if the
  fixture can't satisfy an assertion, stop and report which one and why.
- `.gitignore` ignores `*.json` and `*.pdf`, which would also hide future fixtures (Stage 2 needs PDF fixtures):
  add `!tests/fixtures/**` after those lines and check with `git check-ignore -v tests/fixtures/x.pdf` (no
  output = not ignored).

### Repo hygiene
Status: done
**Done when:** `uv run pytest` passes with the same counts (70 passed, 1 skipped); `npm run type-check` passes in
`frontend/`; `git check-ignore -v tests/fixtures/x.pdf tests/fixtures/x.json uv.lock` prints nothing; `uv lock --check`
passes and `uv.lock` is committed (`git ls-files uv.lock` prints it); `grep -rn
"import/preview\|ImportPreviewResponse\|importPreview" tradurre frontend/src` finds nothing; `uv tree
--no-dev` (or `uv export --no-dev`) lists neither `pytest` nor `httpx`.

- **Dev dependencies.** In `pyproject.toml` move `pytest` and `httpx` out of `[project] dependencies` into
  `[dependency-groups] dev = [...]` (same version specifiers). `uv run pytest` installs the dev group by default;
  check it. Nothing under `tradurre/` imports either (verified with grep), so the wheel loses nothing.
- **Dead endpoint.** In `tradurre/api/import_.py` delete the "Legacy preview" block: the comment, the
  `ImportPreviewResponse` model (defined locally at `:61`) and `import_preview` (`:66`). In
  `frontend/src/api/client.ts` delete `export interface ImportPreviewResponse` (`:62`) and `importPreview`
  (`:146`). No view calls it (the wizard uses `importSections`/`importParagraphs`/`importSentences`).
- **Unreachable code.** In `import_artifact` delete the dead `return {"id": project_id, …}` dict after the
  `return ImportArtifactResponse(...)` (`import_.py:~348`). Remove any import that becomes unused.
- **Fixture ignores.** In `.gitignore` add `!tests/fixtures/**` after the `*.json` and `*.pdf` lines (it must come
  after them to win). Check with the `git check-ignore` command above.
- **Lockfile.** Remove the `uv.lock` line from `.gitignore`. After the `pyproject.toml` change run `uv lock` (it
  moves `pytest`/`httpx` into the dev group; no other version should change: check `git diff --stat` is limited
  to that, and report any upgrade it made) and commit `uv.lock` with the rest of the task.
- Don't touch the `pdf`/`ocr`/`align` extras or any other endpoint.
Report: 2026-10-03 — pytest/httpx moved to dev group, `uv.lock` tracked (relock moved only those two, no version changes); removed `/import/preview` (+ now-dead `_extract` helper and its imports), the unreachable return, `importPreview` in client.ts; `!tests/fixtures/**` added; pytest 70 passed, 1 skipped. `npm run type-check`: 10 errors in `ImportWizard.vue`/`ProjectEditor.vue`, identical before this task (checked on `ad0c8e1`), none from it.
Verified (/pauli, 2026-10-03): every check holds except the type-check, which moves to "Frontend type-check"
below. (`git check-ignore -v` prints the `!tests/fixtures/**` negation match; without `-v` it prints nothing, exit
1: not ignored, as intended.) `httpx` still appears in `uv tree --no-dev`, but only under `huggingface-hub` from the
`align` extra: fine. Side effect: with `_extract` gone, nothing imports `tradurre/services/importer.py` any more;
it is dead code, removed in Stage 6.

### Frontend type-check
Status: done
**Done when:** `npm run type-check` (in `frontend/`) exits 0; `npm run build` succeeds; `release.yml` runs `npm run
build` with the TODO comment gone; `uv run pytest` unchanged (70 passed, 1 skipped); the wizard's "+"/"x" buttons
work (see below).

Why now: two of the 10 errors are a **runtime bug**, not type noise. In `ImportWizard.vue` `currentSourceArr` /
`currentTargetArr` (`:177-186`) are computeds returning a ref; the template unwraps the computed, so
`currentSourceArr.value` there is already the array, and `insertBlank`/`removeRow` (`:168-174`) then call
`arr.value.splice` on an array: `TypeError`, so "Insert blank above" and "Remove" in the alignment step never
worked. A green type-check also lets every later frontend task say "type-check passes" instead of diffing an error
list.

- `ImportWizard.vue`: change `insertBlank` and `removeRow` to take `arr: ImportUnit[]` and splice `arr` directly
  (the array reached through the ref is reactive, so the splice re-renders). Leave the template calls (`:321-333`)
  as they are; they then type-check. Don't restructure the computeds.
- `ProjectEditor.vue` (`:163`, `:228`, `:234`, `:451`): "possibly undefined" from indexed access where the index is
  in range by construction (`i > 0`, `gi > 0`, a group always has a first pair). Add non-null assertions (`!`) at
  those accesses; no other change. Don't touch `tsconfig*.json`.
- `.github/workflows/release.yml:28`: `npm run build-only  # TODO…` → `npm run build`.
- Check the bug fix by hand: `uv run tradurre --dev` + `npm run dev`, import two small `.txt` files, and in the
  sentence step press "+" and "x" once each; the row count shown above the table changes by +1 and −1 and the
  browser console shows no error. Say in the Report that you did (or, if you could not run a browser, say so; the
  type-check alone then stands as the evidence). No e2e test: the wizard is deleted in Stage 6.
Report: 2026-10-03 — `insertBlank`/`removeRow` take `ImportUnit[]`, `!` at the 4 `ProjectEditor.vue` sites (6 errors), `release.yml` runs `npm run build`; type-check 0 errors (was 10), `npm run build` ok, pytest 70 passed, 1 skipped. Browser check not done: no browser installed (Playwright's Chromium missing, no system Chrome); type-check is the evidence.
Verified (/pauli, 2026-10-03, `9e5584f`): type-check 0 errors, `release.yml:28` is `npm run build`, pytest 70
passed, 1 skipped. The wizard fix is sound without the browser check: the six arrays are deep `ref`s
(`ImportWizard.vue:23-32`), so the array reached in the template is a reactive proxy and `splice` re-renders.
Accepted; the developer may still click "+"/"x" once.

### Database access
Status: done
**Done when:** no code reads `app.state.db`; every request uses its own connection; every write handler runs in
one transaction that rolls back on error; the new test `test_failed_insert_leaves_positions_intact` passes and
fails on the pre-task code; `uv run pytest` passes otherwise unchanged.

Why: today one `check_same_thread=False` connection (`app.py:19-21`) is shared by sync handlers running in
FastAPI's threadpool, and handlers commit only at the end (`pairs.py:90`, etc.). An exception between the
negative-position shift and the `INSERT` in `create_pair` (`pairs.py:48-89`) leaves the shift pending on the
shared connection, visible to every later request and committed by the next `db.commit()` of any request.

- `tradurre/db.py`: add `get_db(request: Request)`, a generator dependency: opens
  `get_connection(request.app.state.db_path)`, yields it, closes it in `finally`. `get_connection` stays as is
  (it sets `foreign_keys=ON`, which is per connection, so every new connection gets it).
- `tradurre/app.py` lifespan: open a connection, `init_db` it, close it; set `app.state.db_path = DB_PATH`
  instead of `app.state.db`. (Reading `DB_PATH` at lifespan time keeps the test fixture's monkeypatch working.)
- Every handler in `tradurre/api/*.py` that uses the DB takes `db: sqlite3.Connection = Depends(get_db)` instead
  of `request: Request` + `request.app.state.db` (keep `request` only where it is used for something else).
- Every handler that writes wraps all its reads-for-write and writes in one `with db:` block (sqlite3 commits on
  success, rolls back on exception) and drops its explicit `db.commit()`. `HTTPException`s raised inside the
  block roll back too, which is correct. Read-only handlers need no block.
- The first statement inside each such block is `db.execute("BEGIN IMMEDIATE")`. Reason: in sqlite3's default
  (legacy) transaction mode the implicit `BEGIN` comes only before the first `INSERT`/`UPDATE`/`DELETE`, so the
  reads that precede it (`create_pair`'s `MAX(position)`, the 404 checks) would sit outside the transaction, and
  with one connection per request two concurrent writers could both compute the same position. `BEGIN IMMEDIATE`
  takes the write lock up front; the other request waits (sqlite3's default 5 s `timeout`). Don't change
  `isolation_level` or `autocommit` on the connection.
- A final read that builds the response (e.g. `create_pair`'s `SELECT * … WHERE id = ?`, `pairs.py:92`) may stay
  after the block.
- Keep `check_same_thread=False` in `get_connection` (`db.py:68`): FastAPI may run a sync generator dependency
  and the sync handler that uses it on different threadpool threads. Each connection is still used by one
  request at a time.
- The test fixtures in `tests/test_pairs_api.py` and `tests/test_import_artifact.py` monkeypatch
  `tradurre.app.DB_PATH`; they must keep working unchanged.
- Don't change SQL, response shapes, or `init_db`'s schema/migration code; keep the negative-position shift.
- Test in `tests/test_pairs_api.py`: create pairs "a","b","c" at positions 0–2; monkeypatch
  `tradurre.api.pairs.strip_html` to raise `RuntimeError`; POST a pair at `position: 1` with `source_text`
  but **without** `target_text` (so `strip_html` runs on the target after the shift); expect a 500 (use a `TestClient(app,
  raise_server_exceptions=False)` or `pytest.raises(RuntimeError)`); undo the monkeypatch; GET the pairs and
  assert positions `[0, 1, 2]` with texts `a, b, c`. Before writing the fix, run the test against the old code
  and confirm it fails; say so in the Report.
Report: 2026-10-03 — `get_db` dependency (`db.py`), lifespan stores `app.state.db_path`; every DB handler in `projects`/`pairs`/`import_`/`export`/`search` uses `Depends(get_db)`, the 9 write handlers run in `with db:` + `BEGIN IMMEDIATE`, no `db.commit()` left outside `init_db`; `test_failed_insert_leaves_positions_intact` failed on the old code (`[0, 2, 3]`), passes now; pytest 71 passed, 1 skipped. Deviation: the test sends `source_text` and omits `target_text` (`PairCreate.source_text` is required, `models.py:31`).
Verified (/pauli, 2026-10-03, `b5fb19d`): no `app.state.db` left; all 10 write handlers (not 9: projects 3, pairs 6,
`import_confirm` 1) open `BEGIN IMMEDIATE` inside `with db:`, and every `INSERT`/`UPDATE`/`DELETE` in `tradurre/api/`
sits inside one; pytest 71 passed, 1 skipped. The test deviation was correct (the task text was wrong, now fixed
above). Braun also ran 100 concurrent appends from 16 threads: all 201, positions exactly 0–99.

### Python 3.14
Status: done
**Done when:** `.python-version` says `3.14`; `pyproject.toml` has `requires-python = ">=3.14"`; `uv lock --check`
passes and the only `uv.lock` changes are dropped pre-3.14 markers/wheels (no version bumps; report any);
`uv run pytest` passes with the same counts as before; `grep -rn "3\.12" CLAUDE.md SPEC.md pyproject.toml
packaging/` finds nothing.

Decision (user, 2026-10-03, SPEC §4): Python 3.14 only, Colab included. Colab gets 3.14 through uv (`uv venv` /
`uv sync` honour `.python-version` and download a managed interpreter); every package of the `align` extra has
`cp314` or pure/abi3 Linux wheels in `uv.lock` (checked: torch 2.14.1, numba, lingua-language-detector), and every
runtime dependency has `cp314`/`abi3` `win_amd64` wheels (checked: pymupdf, pydantic-core, httptools, watchfiles,
lxml, websockets, pyyaml).
- Add `.python-version` containing `3.14` at the repo root.
- `pyproject.toml`: `requires-python = ">=3.14"`; then `uv lock`, and commit `uv.lock` with the change (it is
  tracked from "Repo hygiene" on).
- `packaging/start-tradurre.bat`: add `--python 3.14` to the `uv.exe tool install --force` line (`:56`), so the
  translator's environment doesn't depend on which Python uv happens to find. Existing installs move to 3.14 on
  the next upgrade, because `--force` rebuilds the tool environment.
- `CLAUDE.md`, "Commands": "Python 3.12" → "Python 3.14".
- `CLAUDE.md`, "Backend": the sentence "Handlers access the DB via `request.app.state.db` (a single shared sqlite3
  connection, not a session/pool)." is stale since "Database access". Replace it with: "Handlers get a
  per-request connection via `db: sqlite3.Connection = Depends(get_db)` (`db.py`); write handlers wrap their work
  in `with db:` starting with `db.execute("BEGIN IMMEDIATE")`." Follow that pattern for new handlers.
  (Doc-only, bundled here because this task already edits `CLAUDE.md`.)
- Note: the local `.venv` already runs Python 3.14.4 (uv picked the newest allowed interpreter), so the suite is
  already green on 3.14; the risk in this task is the lock and the launcher, not the code.
Report: 2026-10-03 — `.python-version` 3.14, `requires-python >=3.14`, relock (−356 lines: only cp312/cp313/graalpy312 wheels and the `typing-extensions` edge marked `< '3.13'` dropped; no name/version changes), `--python 3.14` on the launcher's install line (`:56`, CRLF kept), `CLAUDE.md` Python version and per-request connection note; `uv lock --check` ok, grep for 3.12 empty, pytest 71 passed, 1 skipped on 3.14.4. The `.bat` change is not exercised here: check it by hand on the next release.
- Report that the `.bat` change can't be exercised here; the developer checks it by hand on the next release.

---

## Stage 1 — New data model

Separate text from alignment (SPEC §2). Built alongside the old `pairs` model, which stays working until
Stage 6 removes it.

### Schema
Decided (user, 2026-10-03): "reviewed" is a **per-bead flag** in storage, editable one bead at a time; no "reviewed
up to here" position. Bulk marking comes from **skim review**, a pass the translator starts deliberately (typically
once, after import), not a default mode: beads scrolled past during the pass are marked reviewed (Stage 3).
Consequences for this stage: the flag is a column on the bead; marking many beads at once is one operation with one
inverse (one undo reverses the marks made since the last correction in a skim pass; a single step for the whole pass
would break the linear undo order once corrections are interleaved); beads made by a correction inherit the flag
(merge: reviewed only if all merged beads were). SPEC §3.3 now says this ("Reviewed marks", "Skim
review").

Decided (user, 2026-10-03): a schema-version mechanism replaces the ad hoc `ALTER TABLE … try/except` pattern,
because SPEC §4 requires automatic migration on upgrade and that pattern can't express table rebuilds or data moves.

Design decisions for the whole stage (/pauli, 2026-10-03):
- **A segment points to its bead** (`segments.bead_id`), instead of a bead storing source/target segment ranges.
  Coverage "exactly once" is then structural for every segment that has a bead; what the checker (step
  "Invariants") still verifies is contiguity, monotonicity, and that a segment has a bead iff its block is not
  excluded. Moving a boundary is one `UPDATE` of one segment; merging beads re-points the segments of one bead.
  Ranges would make every segment split/join and exclude/include rewrite bead endpoints.
- **Beads store their order** (`beads.ord`): it can't be derived from segment order, because the order of a 1:0
  bead next to a 0:1 bead is not determined by either side.
- **Ordering is sparse integers**: `ord` columns, `UNIQUE` per parent, assigned with gaps; the domain layer
  (step "Domain operations") owns the spacing policy and the renumbering when a gap runs out. The schema only
  stores them.
- **New tables use `INTEGER PRIMARY KEY`** (local ids, ~20k segments per book); `projects.id` stays a TEXT uuid
  because the old model shares the table.
- **Not in the schema step**: the operation log (added by its own migration in "Domain operations", where its
  payload is designed), the search index (step "Search index"), and import runs/warnings (Stage 2, "Import API").
  With migrations in place, each lands with the code that uses it.

#### Migration mechanism
Status: done
**Done when:** `init_db` runs an ordered list of migrations keyed on `PRAGMA user_version`; the new
`tests/test_migrations.py` passes (cases below); `uv run pytest` otherwise unchanged (71 passed, 1 skipped);
`CLAUDE.md` describes the new mechanism and no longer prescribes `ALTER TABLE … try/except`.

All in `tradurre/db.py`:
- `_run_script(conn, script)`: runs a multi-statement SQL string **statement by statement** with `conn.execute`,
  so it stays inside the caller's transaction (`executescript` would commit first). Split by accumulating lines
  until `sqlite3.complete_statement(buffer)` is true (this keeps `CREATE TRIGGER … BEGIN … END;` whole); raise
  `ValueError` if a non-blank remainder is left.
- `_m001_pairs(conn)`: today's schema as migration 1. `_run_script` on `_SCHEMA`, `_FTS_SCHEMA`, `_FTS_TRIGGERS`
  (all `IF NOT EXISTS`, so a pre-migration database at `user_version` 0 passes through), then add `section` and
  `paragraph` only if `PRAGMA table_info(pairs)` lacks them (same column definition as today). No `try/except`.
- `MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_m001_pairs]`.
- `init_db(conn)`: read `user_version`. If it is greater than `len(MIGRATIONS)`, raise `RuntimeError("database
  schema version N is newer than this version of Tradurre supports (M); upgrade Tradurre")`. Otherwise, for each
  pending migration in order: `with conn:` → `conn.execute("BEGIN IMMEDIATE")` → migration →
  `conn.execute(f"PRAGMA user_version = {n}")`. One transaction per migration, so a failure leaves the database at
  the last good version. Drop the final `conn.commit()`.
- Leave `get_connection`, `get_db` and the SQL strings unchanged.
- `tests/test_migrations.py`:
  - fresh database: `user_version == len(MIGRATIONS)`, the `pairs` table has `section`/`paragraph`;
  - `init_db` twice: no error, same version;
  - **legacy database**: build one the way v0.1 did (`executescript` of the three SQL strings, `ALTER TABLE` for
    the two columns, one project and one pair inserted, `user_version` left at 0); `init_db` brings it to the
    current version and the pair and its FTS row are still there;
  - **failing migration**: monkeypatch `tradurre.db.MIGRATIONS` to `[_m001_pairs, bad]` where `bad` creates a
    table then raises; `init_db` raises, `user_version` is 1, the table `bad` created does not exist;
  - **newer database**: `PRAGMA user_version = 99` then `init_db` raises `RuntimeError`.
- `CLAUDE.md`, the `db.py` bullet: replace the sentence on ad hoc `ALTER TABLE` migrations with: "Schema changes
  are migrations: append a function to `MIGRATIONS` in `db.py` (never edit an applied one); `init_db` runs the
  pending ones, each in its own transaction, and records the count in `PRAGMA user_version`. Use `_run_script`,
  not `executescript`, inside a migration."
Report: 2026-10-03 — `_run_script`, `_m001_pairs` (columns via `PRAGMA table_info`), `MIGRATIONS`, `init_db` with one `BEGIN IMMEDIATE` transaction per migration and a newer-version refusal; `CLAUDE.md` `db.py` bullet rewritten; `tests/test_migrations.py` 6 passed (the 5 listed plus `_run_script` rejecting an incomplete statement); pytest 77 passed, 1 skipped. A copy of the local `~/.tradurre/tradurre.db` (empty, user_version 0) migrated to 1 cleanly.
Verified (/pauli, 2026-10-03, `e1f4f65`): code matches the task; pytest 77 passed, 1 skipped. Checked by hand that
`_run_script` keeps `--` comments containing `;` inside one statement, and that two statements on one line fail
loudly (`ProgrammingError`) rather than silently: so SQL given to it must end each statement at a line end.

#### Text and alignment tables
Status: done
**Done when:** migration 2 creates the tables below; the new `tests/test_schema.py` passes; `uv run pytest`
otherwise unchanged; the old `pairs` API and its tests untouched.

`_m002_text_alignment` in `tradurre/db.py`, appended to `MIGRATIONS`, via `_run_script` on a new `_TEXT_SCHEMA`
string with exactly:

```sql
CREATE TABLE documents (
    id         INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    side       TEXT NOT NULL CHECK (side IN ('source', 'target')),
    filename   TEXT NOT NULL,
    format     TEXT NOT NULL CHECK (format IN ('pdf', 'docx', 'txt')),
    UNIQUE (project_id, side)
);
CREATE TABLE blocks (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('paragraph', 'heading', 'footnote', 'running_head',
                    'page_number', 'front_matter', 'back_matter', 'other')),
    excluded    INTEGER NOT NULL DEFAULT 0 CHECK (excluded IN (0, 1)),
    page        INTEGER,            -- logical page in the edition, for diagnostics; NULL if unknown
    UNIQUE (document_id, ord)
);
CREATE TABLE beads (
    id         INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ord        INTEGER NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    method     TEXT NOT NULL CHECK (method IN ('anchor', 'length', 'embedding', 'llm', 'manual')),
    reviewed   INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0, 1)),
    UNIQUE (project_id, ord)
);
CREATE TABLE segments (
    id            INTEGER PRIMARY KEY,
    block_id      INTEGER NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    ord           INTEGER NOT NULL,
    text          TEXT NOT NULL,
    original_text TEXT NOT NULL,    -- as extracted; text edits never change it
    bead_id       INTEGER REFERENCES beads(id),   -- NULL iff the block is excluded
    UNIQUE (block_id, ord)
);
CREATE INDEX idx_segments_bead ON segments(bead_id);
```

- SPEC §2 gives every bead a confidence, so it is `NOT NULL`; beads made by hand get `1.0` (rule owned by
  "Domain operations"). What a segment split/join does to `original_text` is also decided there, not here.
- `segments.bead_id` deliberately has no `ON DELETE` action: deleting a bead that still has segments must fail,
  so no domain bug can silently orphan text. (Deleting a project still works: the cascade removes beads and
  segments in the same statement, and SQLite checks the constraint at statement end.)
- `tests/test_schema.py`, on a fresh `init_db`'d temp database (with `PRAGMA foreign_keys=ON`, i.e. via
  `get_connection`): insert a project, two documents, a block per document, two beads, segments pointing at them;
  then assert:
  - deleting a bead that a segment points to raises `sqlite3.IntegrityError`;
  - deleting the project removes every row in `documents`, `blocks`, `segments`, `beads`;
  - a duplicate `(block_id, ord)` and a duplicate `(project_id, ord)` raise `IntegrityError`;
  - `kind = 'chapter'`, `method = 'magic'`, `confidence = 1.5`, `confidence = NULL`, `side = 'left'` each raise
    `IntegrityError`;
  - `user_version` is 2 after `init_db`.
- Don't touch `pairs`, the FTS table or the API.
Report: 2026-10-03 — `_TEXT_SCHEMA` (SQL copied verbatim from this task) and `_m002_text_alignment` appended to `MIGRATIONS`; `tests/test_schema.py` 10 passed (user_version 2, bead delete blocked, project cascade, two duplicate `ord`s, five CHECK cases); pytest 87 passed, 1 skipped; `pairs`/FTS/API untouched.
Verified (/pauli, 2026-10-03, `4e16101`): `_TEXT_SCHEMA` is byte-identical to the SQL above; pytest 87 passed,
1 skipped. Accepted.

### Domain operations
A service layer, independent of HTTP, implementing every SPEC §3.3 correction as a transactional operation with
undo/redo that survives restarts (SPEC §2 "History"), plus the bulk primitive that import (Stage 2), re-align
range (Stage 3) and loading a Colab alignment (Stage 4) build on. Code lives in a new package `tradurre/domain/`;
nothing in `tradurre/api/` or the old `pairs` model changes in this step. HTTP endpoints come with the stages that
use them.

Design (/pauli, 2026-10-03), binding for every task below:
- **Undo is generic, by row snapshots.** Every write an operation makes goes through a `Recorder` that stores, per
  touched row, `(table, id, before, after)` (`before` is `None` for an insert, `after` is `None` for a delete; rows
  as dicts of all columns). An operation's change list is stored as JSON in the operation log. Undo applies the
  `before`s, redo the `after`s. No per-operation inverse code, so undo can't drift from the operation.
- **Ids are stable across undo/redo**: a re-inserted row gets its old id back. History is linear: recording a new
  operation deletes the project's undone operations (the redo stack), so ids recreated by redo are always free.
- **Applying a change list** (undo or redo), in one transaction, with `PRAGMA defer_foreign_keys = ON` (checked
  at commit; verified in SQLite 3.46: a violation at commit rolls everything back): (1) every row that is updated
  and whose target `ord` differs gets `ord = -id`; (2) delete the rows to delete; (3) write the target values of
  updated rows; (4) insert the rows to insert. Every `UNIQUE (parent, ord)` holds at each step, because the
  target state is one that existed and ords are never negative outside step (1).
- **Ordering**: `ord` values are non-negative integers, spaced by `GAP = 1024` when created in bulk. A single
  insert between siblings `a` and `b` takes `(a + b) // 2`; at the end `last + GAP`; at the start `first // 2`. If
  the result equals a neighbour (no integer room), the siblings are first renumbered `GAP, 2·GAP, …` through the
  Recorder (so the renumbering is undone with the operation), then the midpoint is taken again.
- **Rules for corrections** (SPEC §2, §3.3):
  - a bead whose segment membership changes through an **alignment** correction (move, merge, split bead, and the
    bead merge of a cross-bead segment join) becomes `method = 'manual'`,
    `confidence = 1.0`; its `reviewed` flag is kept (a merge: reviewed only if all merged beads were; a split: both
    halves keep the original's flag). A bead left with no segment on either side is deleted.
  - **segment split** at a character offset of the current `text`: first part `text[:offset].rstrip()`, second
    `text[offset:].lstrip()`, both non-empty or the split is refused. `original_text` is split at the offset mapped
    from `text` to `original_text` through `difflib.SequenceMatcher(None, text, original_text, autojunk=False)`
    opcodes (inside an `equal` run: shifted linearly; inside any other run: the start of its original range), with
    the same strip rule. Unedited text therefore splits identically on both. The new segment follows in the same
    block and bead.
  - **segment join** with the next segment of the same block: `text = a.text + " " + b.text`, likewise for
    `original_text`; it keeps `a`'s id. If the two segments are in **different beads, the beads are merged too**
    (same rule as a bead merge: `manual`, `1.0`, reviewed only if both were), so text and alignment move
    together. Decided (user, 2026-10-03): "when you join, you join both the beads and the texts". SPEC §2 updated
    accordingly (user agreed, 2026-10-03). Still refused
    across blocks (paragraph structure); revisit if real books need it.
  - **exclude block**: `excluded = 1`, its segments' `bead_id = NULL`, beads left empty deleted. Exclude and
    include are text-layer decisions, not alignment judgments: they never change an existing bead's `method`,
    `confidence` or `reviewed` (/pauli, 2026-10-03, revising the first version, which marked them `manual`/`1.0`:
    that claimed the translator had checked an alignment they had not, and hid a now-misaligned bead from the
    low-confidence highlighting).
  - **include block**: `excluded = 0`. With `P` the nearest preceding and `N` the nearest following non-excluded
    segment on the same side: if both exist and share a bead, the block's segments join that bead; otherwise they
    form one new bead with the other side empty, placed right after `P`'s bead (or first, if there is no `P`),
    `method = 'manual'`, `confidence = 0.0`, `reviewed = 0` (unmatched material the translator should look at). Confirmed by the user, 2026-10-03.
  - **review marks**: setting one bead's flag is its own operation. Marks made by skim review coalesce: a skim mark
    is appended to the latest operation if that operation is a not-undone skim-review operation, otherwise it
    starts a new one; so one undo removes the marks since the last correction (SPEC §3.3).
  - **replace beads** (bulk): replaces a contiguous run of beads (or, for a project with no beads yet, nothing)
    with new beads given as source/target segment-id lists with confidence and method; new beads start
    `reviewed = 0`. Refused unless the new beads cover exactly the segments the old ones covered, in order.
- **Every write to a project's documents/blocks/segments/beads after it is built goes through a Recorder** (undo
  assumes the database is exactly as the last operation left it). The layer builder is for building only.
- **Operations** are functions `op(conn, project_id, …)` in `tradurre/domain/`, one module per area; each validates
  its arguments, writes through one `Recorder`, calls `record` once, and returns the operation id (or what the
  task says). A refused operation raises `DomainError` (defined in `tradurre/domain/__init__.py`) before writing
  anything. Operations don't open transactions: callers use `history.transaction(conn)`.
- **Invariants** (checked in tests after every operation, and by Stage 2's debug endpoint): (I1) a segment has a
  bead iff its block is not excluded; (I2) a bead and the segments pointing at it belong to the same project;
  (I3) every bead has at least one segment; (I4) on each side, the beads' `ord`s, read along non-excluded segments
  in document order (block `ord`, then segment `ord`), never decrease (this is contiguity and monotonicity
  together); (I5) no negative `ord`.

#### Text-layer builder and invariant checker
Status: done
**Done when:** `tests/test_domain_invariants.py` passes: a project built with the builder passes the checker, and
each of the five corruptions below is reported with its invariant's code; `uv run pytest` otherwise unchanged.

- `tradurre/domain/__init__.py` (empty) and `tradurre/domain/layer.py`:
  - dataclasses `NewBlock(kind: str, segments: list[str], excluded: bool = False, page: int | None = None)` and
    `NewBead(source: list[int], target: list[int], confidence: float, method: str)` (segment ids);
  - `GAP = 1024`;
  - `create_document(conn, project_id, side, filename, format, blocks: list[NewBlock]) -> list[list[int]]`: inserts
    the document, its blocks (`ord = i * GAP`) and segments (`ord = j * GAP`, `original_text = text`,
    `bead_id = NULL`); returns the segment ids per block;
  - `append_beads(conn, project_id, beads: list[NewBead]) -> list[int]`: inserts beads after the project's last
    bead (`ord` continuing in steps of `GAP`), `reviewed = 0`, and points their segments at them; returns bead ids.
  - Both are plain inserts for building a project (import, tests): not recorded, not undoable. They don't commit;
    the caller owns the transaction.
- `tradurre/domain/invariants.py`: `check_project(conn, project_id) -> list[str]`, one message per violation,
  each starting with its code (`"I1: segment 12 …"`); empty list = valid. Rules I1–I5 above. Implement with plain
  queries; a 10,000-bead project must check in well under a second (load the segments of both documents in one
  query each, ordered, and walk them in Python).
- `tests/test_domain_invariants.py`: a fixture builds a project with two documents (source: 3 blocks, one of them
  `excluded=True`; target: 2 blocks), 1:1, 2:1 and 0:1 beads covering every non-excluded segment; `check_project`
  returns `[]`. Then one test per corruption, each done with a direct `UPDATE`/`INSERT` on the fixture, asserting
  the code appears: I1 (point an excluded block's segment at a bead), I2 (point a segment at a bead of a second project), I3 (an
  extra bead with no segments), I4 (swap two beads' `ord`s), I5 (set one segment `ord` negative, freeing the
  slot first if needed).
- Don't touch `tradurre/db.py`, `tradurre/api/`.
Report: 2026-10-03 — `tradurre/domain/` with `layer.py` (`NewBlock`, `NewBead`, `GAP`, `create_document`, `append_beads`) and `invariants.py` (`check_project`, I1–I5; I2 checked in both directions); `tests/test_domain_invariants.py` 7 passed (valid fixture, bead `ord` continuation, one test per invariant); pytest 94 passed, 1 skipped. A 10,000-bead project checks in 0.026 s.
Verified (/pauli, 2026-10-03, `a9e9b70`): matches the task; I4's walk catches both an interleaved bead and a swapped
order; pytest 94 passed, 1 skipped. Braun's note (a project missing a document, or with no beads) needs no new
invariant: segments without a bead already fail I1, and a missing document is the import's to prevent (Stage 2).

#### Recorder and operation log
Status: done
**Done when:** `tests/test_domain_history.py` passes (cases below); `uv run pytest` otherwise unchanged.

- Migration 3 in `tradurre/db.py` (`_m003_operations`, appended to `MIGRATIONS`), via `_run_script`:

  ```sql
  CREATE TABLE operations (
      id         INTEGER PRIMARY KEY,
      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      kind       TEXT NOT NULL,
      changes    TEXT NOT NULL,                -- JSON list of [table, id, before, after]
      undone     INTEGER NOT NULL DEFAULT 0 CHECK (undone IN (0, 1)),
      created_at TEXT NOT NULL
  );
  CREATE INDEX idx_operations_project ON operations(project_id, id);
  ```
  (`tests/test_schema.py`'s `user_version == 2` assertion becomes `== len(MIGRATIONS)`.)
- `tradurre/domain/history.py`:
  - `TABLES = {"blocks", "segments", "beads"}`: the only tables a Recorder may touch, and `insert`/`delete` only on
    `segments` and `beads` (raise `ValueError` otherwise). Reason: deleting a block or document cascades to its
    segments outside the Recorder, so undo would lose them; no SPEC §3.3 correction creates or deletes either.
  - `class Recorder`: `__init__(self, conn)`; `insert(table, values: dict) -> int`; `update(table, id, **fields)`;
    `delete(table, id)`. Each reads the full row before (`SELECT *`), performs the write, reads it after, and
    appends `[table, id, before, after]` to `self.changes`. Updating a row twice in one operation records two
    entries; that's fine.
  - `record(conn, project_id, kind, rec: Recorder, coalesce: bool = False) -> int | None`: does nothing and returns
    `None` if `rec.changes` is empty. Otherwise deletes the project's operations with `undone = 1`; then, if
    `coalesce` and the project's latest operation has the same `kind` and `undone = 0`, appends the changes to it;
    else inserts a new operation. Returns the operation id.
  - `undo(conn, project_id) -> int | None`: the project's latest operation with `undone = 0`; apply its changes
    reversed, using `before` as target; set `undone = 1`. `None` if there is nothing to undo.
  - `redo(conn, project_id) -> int | None`: the project's earliest operation with `undone = 1`; apply its changes
    in order, using `after` as target; set `undone = 0`.
  - Applying follows the four-step procedure in the design above. The target of a row touched several times in
    one change list is the **last** `after` (redo) or the **first** `before` (undo) for that row; compute the net
    per row first, then classify it against the current database row: target `None` and row present → delete;
    target present and row absent → insert (with its old id); both present → update (all columns).
  - None of these commit; the caller owns the transaction (`with conn:` + `BEGIN IMMEDIATE`), and calls
    `PRAGMA defer_foreign_keys = ON` itself, right after `BEGIN`. Say so in the module docstring.
- `tests/test_domain_history.py`, on a project built with the layer builder (2 beads × 2 segments per side), with a
  helper `snapshot(conn)` = all rows of the four tables, sorted:
  - a recorded operation that updates a segment's text, inserts a bead, re-points a segment to it, and deletes
    nothing: undo → snapshot equals the one before; redo → equals the one after; ids unchanged;
  - an operation that re-points all segments of bead 2 to bead 1 and deletes bead 2 (a merge done by hand): undo
    restores bead 2 with its old id (needs deferred FKs);
  - an operation that swaps two beads' `ord`s through the Recorder (two updates, via a temporary negative `ord`):
    undo and redo don't hit the `UNIQUE` constraint;
  - recording a new operation after an undo deletes the undone one (redo returns `None`);
  - `coalesce=True` with the same `kind` appends to the latest operation (one undo reverts both), but not after
    that operation was undone, and not when the kinds differ;
  - undo/redo survive closing and reopening the connection;
  - `check_project` returns `[]` after every step.
- Don't touch `tradurre/api/`.
Report: 2026-10-03 — migration 3 (`operations`), `tradurre/domain/history.py` (`Recorder`, `record` with coalescing, `undo`/`redo` via net-per-row four-step apply); `test_schema.py` version assertion now `len(MIGRATIONS)`; `tests/test_domain_history.py` 9 passed (the listed cases plus Recorder table restrictions); pytest 103 passed, 1 skipped. Deviation: the ord-swap test also swaps the two beads' segments, else the swapped state itself breaks I4 and "`check_project` after every step" can't hold. Checked ad hoc: undoing a merge without `defer_foreign_keys` raises `IntegrityError`, so the docstring's requirement is real.
Verified (/pauli, 2026-10-03, `8ea5e97`): matches the task; pytest 103 passed, 1 skipped. Both deviations accepted
(the swap test as written in the plan could not have passed `check_project`). Operation-id reuse is harmless: nothing
refers to an operation by id across an undo; revisit only if something must.

#### Ordering helpers
Status: done
**Done when:** `tests/test_domain_ordering.py` passes (cases below); `uv run pytest` otherwise unchanged.

- `tradurre/domain/__init__.py`: `class DomainError(Exception)` ("operation refused"; message for the translator).
- `tradurre/domain/history.py`: `transaction(conn)`, a `contextlib.contextmanager`: `with conn:` →
  `BEGIN IMMEDIATE` → `PRAGMA defer_foreign_keys = ON` → `yield`. Replace the local `tx` helper in
  `tests/test_domain_history.py` with it.
- `tradurre/domain/ordering.py`:
  - `_PARENT = {"beads": "project_id", "segments": "block_id"}` (the only tables that get new rows).
  - `ord_after(rec: Recorder, table: str, parent_id, after_id: int | None) -> int`: an `ord` for a new row placed
    right after the sibling `after_id` (`None` = before every sibling). With `prev` = `after_id`'s `ord` (or none)
    and `next` = the smallest sibling `ord` greater than `prev` (or than −1 when there's no `prev`): no siblings →
    `0`; no `next` → `prev + GAP`; no `prev` → `next // 2`; otherwise `(prev + next) // 2`. If the result equals
    `prev` or `next` (no room), call `renumber` and compute again.
  - `renumber(rec, table, parent_id)`: siblings in `ord` order get `GAP, 2·GAP, 3·GAP, …` (`(i + 1) * GAP`, so
    there is always room before the first) through `rec.update`, in two passes (first `-(i + 1)`, then
    `(i + 1) * GAP`) so no step collides with `UNIQUE`.
  - `GAP` imported from `layer.py`. Raise `ValueError` for a table not in `_PARENT` or an `after_id` that isn't a
    sibling (programming errors, not `DomainError`).
- `tests/test_domain_ordering.py`, on the beads of a project built with the layer builder (ords `0, 1024, 2048`),
  each call inside a recorded operation:
  - after the first → `512`; after the last → `3072`; in an empty project → `0`;
  - `None` (before the first, whose `ord` is `0`): `0 // 2 == 0` collides, so siblings are renumbered to
    `1024, 2048, 3072` and the result is `512`;
  - siblings at ords `0, 1` (set directly): after the first → renumbered to `1024, 2048`, result `1536`;
  - the operation that renumbered is undone exactly (snapshot equal) and redone;
  - `ValueError` for `table="blocks"` and for an `after_id` from another project.

Report: 2026-10-03 — `DomainError`, `history.transaction`, `domain/ordering.py` (`ord_after`, `renumber`); history tests use `transaction`; 6 new tests, 109 passed, 1 skipped.
Verified (/pauli, 2026-10-03, `8d12a36`): matches the task; pytest 109 passed, 1 skipped. Two harmless deviations:
the `0, 1` siblings are set up by a recorded operation (so the project stays valid), and undo is checked on the
project's `(id, ord)` list rather than a full snapshot (renumbering touches nothing else).

#### Bead operations
Status: done
**Done when:** `tests/test_domain_beads.py` passes (cases below); `uv run pytest` otherwise unchanged.

`tradurre/domain/beads.py`. Helpers (module-level, reused by the segment operations): `_segments(conn, bead_id,
side) -> list[int]`, a bead's segment ids on one side in document order (block `ord`, segment `ord`);
`_previous(conn, bead_id)` / `_next(conn, bead_id) -> int | None`, the adjacent bead in the same project by `ord`;
`_corrected(rec, bead_id)` = set `method = 'manual'`, `confidence = 1.0`. Every function checks that the bead belongs to `project_id`
(`DomainError` otherwise). `side` is `"source"` or `"target"`.
- `move_first_to_previous(conn, project_id, bead_id, side) -> int`: the bead's first segment on `side` moves to
  the previous bead. Refused if there is no previous bead or the bead has no segment on `side`. Both beads
  `_corrected`; if the bead is left with no segments it is deleted. Kind `"move_segment"`.
- `move_last_to_next(conn, project_id, bead_id, side) -> int`: mirror image.
- `merge_with_next(conn, project_id, bead_id) -> int`: the next bead's segments move to this bead, the next bead
  is deleted, this one is `_corrected` and `reviewed = 1` only if both were. Refused if there is no next bead.
  Kind `"merge"`. Factor the body into `_merge(rec, bead_id, next_id)` so the segment join (next task) can reuse
  it.
- `split_bead(conn, project_id, bead_id, source_at: int | None, target_at: int | None) -> int`: the segments of
  each side from `*_at` onward (in document order) move to a new bead placed right after this one
  (`ordering.ord_after`); returns the **new bead's id**. `*_at` must be a segment of this bead on that side.
  Refused if both are `None`, or if either resulting bead would have no segments. Both beads `_corrected`; the new
  bead copies `reviewed`. Kind `"split"`.
- `set_reviewed(conn, project_id, bead_ids: list[int], reviewed: bool, skim: bool = False) -> int | None`: sets
  the flag on each bead whose value differs. `skim=True` requires `reviewed=True` and records kind
  `"skim_review"` with `coalesce=True`; otherwise kind `"review"`, no coalescing. Returns `None` if nothing
  changed.
- `tests/test_domain_beads.py`: a fixture project (layer builder) with beads A `(s1 | t1)`, B `(s2, s3 | t2)`,
  C `(s4 | t3, t4)`, all `reviewed = 0` except A. For each operation: the resulting bead contents (segment ids per
  side, `method`, `confidence`, `reviewed`), `check_project == []`, undo restores the snapshot, redo restores the
  post-state. Plus: moving A's first source segment back (no previous) raises `DomainError` and changes nothing;
  `move_last_to_next(A, "source")` then `move_last_to_next(A, "target")` empties A, which is deleted (B becomes
  `(s1, s2, s3 | t1, t2)`; one undo brings A back with its id, a second undo restores the start); merge A+B gives `reviewed = 0`, merge after marking B reviewed gives `1`; split B at `s3` with
  `target_at=None` → new bead `(s3 | )`; `split_bead` with both `None` raises; two skim marks then one undo clears
  both, while a `review` mark in between stops the coalescing; a bead of another project raises `DomainError`.
Report: 2026-10-03 — `tradurre/domain/beads.py` (helpers `_segments`/`_previous`/`_next`/`_corrected`/`_merge`; move, merge, split, `set_reviewed`); `tests/test_domain_beads.py` 16 passed (each op with invariants + undo/redo snapshots, refusals leave no trace); pytest 125 passed, 1 skipped.
Verified (/pauli, 2026-10-03, `4c5d15f`): matches the task; pytest 125 passed, 1 skipped. All listed cases are
covered, plus refusals checked to leave no snapshot change and no operation row. `ValueError` for a bad `side` and
for skim-unmarking is right (programming errors).

#### Segment operations
Status: done
**Done when:** `tests/test_domain_segments.py` passes (cases below); `uv run pytest` otherwise unchanged.

`tradurre/domain/segments.py`. Every function checks that the segment belongs to `project_id` (through its block
and document; `DomainError` otherwise). Segments of excluded blocks may be edited, split and joined too (their
`bead_id` stays `NULL`). Text corrections leave beads alone, except the cross-bead join (SPEC §2).
- `edit_text(conn, project_id, segment_id, text) -> int | None`: sets `text`; `original_text` never changes.
  Refused if `text.strip()` is empty (to get rid of a segment, join it). Returns `None` (records nothing) if the
  text is unchanged. Kind `"edit_text"`. Reverting is `edit_text(…, original_text)`; no separate operation.
- `_map_offset(text, original, offset) -> int`: per the design rule above. Opcodes come from
  `SequenceMatcher(None, text, original, autojunk=False).get_opcodes()`; use the opcode with `i1 <= offset < i2`
  (so empty `insert` runs never match): `equal` → `j1 + (offset - i1)`, any other tag → `j1`.
- `split_segment(conn, project_id, segment_id, offset) -> int`: returns the new segment's id. Parts per the design
  rule; refused unless `0 < offset < len(text)` and both `text` parts are non-empty after stripping (the
  `original_text` parts may be empty: text the translator added). The new segment goes right after the old one
  in its block (`ordering.ord_after(rec, "segments", block_id, segment_id)`), with the same `bead_id`; the bead is
  not touched. Kind `"split_segment"`.
- `join_with_next(conn, project_id, segment_id) -> int`: `b` = the next segment of the same block by `ord`;
  refused if there is none (joining across blocks is not supported). `a` gets the joined `text` and
  `original_text` (`" "`-separated), `b` is deleted. If `a` and `b` are in different beads, merge **the whole run
  of beads from `a`'s bead to `b`'s bead**, not just those two: beads between them (e.g. a 0:1 bead holding only
  target segments) would otherwise break I4. Do it with `beads._next` and `beads._merge` in a loop on `a`'s bead
  until `b`'s bead is absorbed, then delete `b`. Same-bead join: bead untouched. Kind `"join_segments"`.
- `tests/test_domain_segments.py`, fixture (layer builder): source blocks S1 `[s1 "Il partit.", s2 "Il marcha.",
  s3 "Puis il revint."]`, S2 footnote `[f1 "Une note."]` excluded, S3 `[s4 "Il mar- cha. Fin."]`; target block T1
  `[t1, t2, t3, t4]`; beads A `(s1 | t1)`, X `( | t2)`, B `(s2, s3 | t3)`, C `(s4 | t4)`, A and B reviewed. For each
  operation: the resulting rows, `check_project == []`, undo restores the snapshot, redo the post-state. Cases:
  - `_map_offset`: identical strings → same offset; `("Il marcha. Fin.", "Il mar- cha. Fin.")`: `11 → 13`,
    `6 → 8`; `("Il fut là. Fin.", "Il fnt lâ. Fin.")`: `4 → 4` (inside a `replace`).
  - `edit_text(s1, "Il partit!")`: `original_text` unchanged, bead A's `method`/`confidence` unchanged; same text →
    `None` and no operation row; `"  "` → `DomainError`.
  - `split_segment(s3, 4)` → `"Puis"` / `"il revint."` on both `text` and `original_text`, new segment in bead B
    right after `s3`; offsets `0`, `len(text)` and one leaving a whitespace-only part → `DomainError`. After
    `edit_text(s4, "Il marcha. Fin.")`, `split_segment(s4, 11)` gives texts `"Il marcha."` / `"Fin."` and
    originals `"Il mar- cha."` / `"Fin."`.
  - `join_with_next(s2)` (same bead): `"Il marcha. Puis il revint."`, `s3` gone, bead B unchanged.
  - `join_with_next(s1)` (A, X, B): one bead with A's id, `(s1, s3 | t1, t2, t3)`, `manual`, `1.0`, `reviewed = 0`
    (X wasn't); X and B gone; one undo restores everything with the old ids.
  - `join_with_next(s3)` (last of its block) → `DomainError`; a segment of another project → `DomainError`.
Report: 2026-10-03 — `tradurre/domain/segments.py` (`edit_text`, `_map_offset`, `split_segment`, `join_with_next` merging the bead run via `beads._next`/`_merge`); `tests/test_domain_segments.py` 11 passed (listed cases, plus editing an excluded segment and refusals for another project's segment on every op); pytest 136 passed, 1 skipped.
Verified (/pauli, 2026-10-03, `0edd8b1`): matches the task; pytest 136 passed, 1 skipped. The join loop relies on I4
(`b`'s bead follows `a`'s), which every operation preserves. Minor, accepted: joining onto an empty `original_text`
part (text the translator added) yields an original with a leading space; harmless, revisit only if the review
view shows it. Braun's note on `"Bon-" + "jour"` joining as `"Bon- jour"`: correct per the rule; the translator
fixes it with an edit, and real hyphenation is repaired at extraction (Stage 2).

#### Block operations
Status: done
**Done when:** `tests/test_domain_blocks.py` passes (cases below); `uv run pytest` otherwise unchanged.

`tradurre/domain/blocks.py`. Every function checks that the block belongs to `project_id` (through its document;
`DomainError` otherwise).
- `exclude_block(conn, project_id, block_id) -> int`: refused if already excluded. Sets `excluded = 1` and
  `bead_id = NULL` on its segments; each bead that lost a segment is deleted if left empty, otherwise
  `beads._corrected`. Kind `"exclude_block"`.
- `include_block(conn, project_id, block_id) -> int`: refused if not excluded. Sets `excluded = 0`; if the block
  has segments, finds `P` / `N` (nearest preceding / following segment of a non-excluded block on the same side,
  in document order) and applies the design rule: same bead → the block's segments join it and it is
  `beads._corrected`; otherwise a new bead (`ordering.ord_after(rec, "beads", project_id, P's bead or None)`,
  `method = 'manual'`, `confidence = 0.0`, `reviewed = 0`) gets them. Kind `"include_block"`.
- `tests/test_domain_blocks.py`, same fixture as the segment tests (copy it; no shared conftest needed yet). For
  each operation: the resulting rows, `check_project == []`, undo/redo snapshots. Cases:
  - `exclude_block(S3)`: C deleted, `s4.bead_id` NULL; undo brings C back with its id.
  - `exclude_block(S1)`: A becomes `( | t1)`, B `( | t3)`, both `manual`/`1.0`, reviewed kept; X unchanged.
  - `include_block(S2)` (P = s3 in B, N = s4 in C): new bead `(f1 | )` with `ord` between B's and C's, `manual`,
    `0.0`, unreviewed.
  - `beads.merge_with_next(B)` then `include_block(S2)`: f1 joins the merged bead.
  - `exclude_block(S1)` then `include_block(S1)` (no P): new bead `(s1, s2, s3 | )` placed first (A sits at `ord`
    0, so this renumbers); the project stays valid.
  - excluding an excluded block / including an included one → `DomainError`; a block of another project →
    `DomainError`.
Report: 2026-10-03 — `tradurre/domain/blocks.py` (`exclude_block`, `include_block`); `tests/test_domain_blocks.py` 7 passed; pytest 143 passed, 1 skipped. Deviation: with this fixture C is `(s4 | t4)`, so excluding S3 leaves C as `( | t4)` (tested so); the emptied-bead case is tested by excluding target block T1, which deletes X, and undo restores it with its id.
Verified (/pauli, 2026-10-03, `2b664cf`): matches the task; pytest 143 passed, 1 skipped. The deviation fixes my
error in the task (C keeps `t4`) and tests the intended rule. Braun's note on surviving beads being marked
`manual`/`1.0` is right: the rule is revised above and the follow-up task below implements it.

#### Exclude/include leave beads' confidence alone
Status: done
**Done when:** `tests/test_domain_blocks.py` passes with the updated expectations below; `uv run pytest` otherwise
unchanged.

Per the revised rule under "Rules for corrections": in `tradurre/domain/blocks.py`, `exclude_block` no longer calls
`beads._corrected` on beads that keep segments (empty ones are still deleted), and `include_block` no longer calls
it on the bead the block's segments join. New beads made by `include_block` are unchanged (`manual`, `0.0`,
unreviewed). Drop the now-unused `_corrected` import. In `tests/test_domain_blocks.py`, survivors keep their
fixture values: excluding S3 leaves C `( | t4)` as `anchor`/`0.8`; excluding T1 leaves A `(s1 | )` as
`anchor`/`0.9`; excluding S1 leaves A `( | t1)` as `anchor`/`0.9` and B `( | t3)` as `length`/`0.7`. In the
include-into-bead case, after `merge_with_next(B)` set the merged bead's `confidence` to `0.4` through a recorded
operation (`Recorder.update` + `record`, kind `"test"`), so the check can tell; after `include_block` it is still
`manual`/`0.4`.
Report: 2026-10-03 — `blocks.py` no longer calls `_corrected` (import dropped, docstring states the rule); block tests updated to the fixture values and the `0.4` include case; 7 passed; pytest 143 passed, 1 skipped.
Verified (/pauli, 2026-10-03, `a73cc65`): matches the task; pytest 143 passed, 1 skipped.

#### Replace beads
Status: done
**Done when:** `tests/test_domain_replace.py` passes (cases below); `uv run pytest` otherwise unchanged.

The bulk primitive behind re-align range (Stage 3) and loading a Colab alignment (Stage 4). It replaces a run of
beads; which runs may be replaced (e.g. only unreviewed ones) is the caller's rule, not this function's.
- `tradurre/domain/ordering.py`: `ords_after(rec, table, parent_id, after_id: int | None, count: int) ->
  list[int]`, `count` strictly increasing ords for new rows placed right after `after_id` (`None` = before every
  sibling), in one go, so a long run never renumbers more than once. `ValueError` for `count < 1` and the same
  cases as `ord_after`. With `prev` / `next` as in `ord_after`:
  - no siblings → `[i * GAP for i in range(count)]`; no `next` → `[prev + (i + 1) * GAP …]`;
  - otherwise, with `lower = prev` (or `-1` without `prev`) and `d = next - lower`: if `d >= count + 1`, return
    `[lower + (i + 1) * d // (count + 1) …]`;
  - else make room: siblings up to and including `after_id` get `(i + 1) * GAP`, the following ones
    `(i + 1 + count) * GAP` (two passes through `rec.update`, negatives first, as in `renumber`), and the result is
    `[base + (i + 1) * GAP …]` with `base` = `after_id`'s new ord, or `0` without `after_id`.
  `ord_after` stays as it is.
- `tradurre/domain/replace.py`:
  - `_replace(rec, project_id, first: int | None, last: int | None, beads: list[NewBead]) -> list[int]` (`NewBead`
    from `layer.py`), so Stage 4 can replace several runs in one operation; and
    `replace_beads(conn, project_id, first, last, beads, kind: str = "replace_beads") -> list[int]`, which
    validates, calls `_replace` with one Recorder, records once and returns the new bead ids.
  - The run is the beads with `ord` from `first`'s to `last`'s, inclusive. `first`/`last` both `None` = the project
    has no beads yet and the run is empty; then the "old coverage" is every segment of a non-excluded block, per
    side, in document order. Otherwise it is, per side, the concatenation of `beads._segments` of the run's beads
    in `ord` order.
  - Refused (`DomainError`, before writing anything): `first`/`last` not beads of the project, only one of them
    `None`, both `None` while the project has beads, `first` after `last`; a new bead with no segment on either
    side; per side, the concatenation of the new beads' segment lists differing from the old coverage (this also
    catches duplicates, foreign and excluded segments, and wrong order). `ValueError` for a `confidence` outside
    `[0, 1]` or a `method` outside the schema's list (callers' bugs, caught before the `CHECK` fires).
  - Writes: note the bead before `first` (`beads._previous`), delete the run's beads (segments dangle until the
    end of the operation; this relies on `defer_foreign_keys`, i.e. on `history.transaction`), take
    `ords_after(rec, "beads", project_id, that previous bead, len(beads))`, insert the new beads (`reviewed = 0`,
    given `confidence`/`method`) and point their segments at them.
- `tests/test_domain_replace.py`. Fixture (layer builder): beads A `(s1 | t1)`, B `(s2, s3 | t2)`,
  C `(s4 | t3, t4)`, D `(s5 | t5)`, plus a source block excluded holding `f1`, plus a second project. Every
  successful call: invariants, undo restores the snapshot, redo the post-state. Cases:
  - replace B..C with `(s2 | t2)`, `(s3, s4 | t3)`, `( | t4)`: B and C gone; three new beads in that order
    between A and D (by `ord`), `reviewed = 0`, given method/confidence;
  - replace B..B with one bead equal in content: allowed (a re-align that changes nothing still makes new beads);
  - refusals, each leaving the snapshot and the operation count unchanged: coverage missing `s4`; source order changed
    (`(s2 | t2)`, `(s4 | t3)`, `(s3 | t4)`); including `s1` (outside the run) or `f1` (excluded); an empty new bead;
    `first` = C, `last` = B; a bead of the other project; `first` given and `last` `None`; `None`/`None` here;
  - an empty project (documents built, no beads): `None`/`None` with beads covering every non-excluded segment →
    ords `0, 1024, …`; one undo leaves the project with no beads;
  - `ords_after` on bead siblings: ords `0, 1024`, after the first, `3` → `256, 512, 768`; ords `0, 1`, after the
    first, `3` → siblings renumbered to `1024, 5120`, result `2048, 3072, 4096`; ords `0, 1`, `None`, `2` →
    siblings `3072, 4096`, result `1024, 2048`; after the last, `2` → `last + 1024, last + 2048`; `count = 0` →
    `ValueError`.
Report: 2026-10-03 — `ordering.ords_after` (prev/next lookup factored into `_neighbours`, shared with `ord_after`, behaviour unchanged); `tradurre/domain/replace.py` (`_replace`, `replace_beads`); `tests/test_domain_replace.py` 10 passed (listed cases plus `ValueError` for bad confidence/method); pytest 153 passed, 1 skipped.
Verified (/pauli, 2026-10-03, `4cdda47`): matches the task; pytest 153 passed, 1 skipped. The `_neighbours`
refactor is inside the module and keeps `ord_after`'s tests green; accepted. Coverage is checked before any write,
so a refused replace leaves no trace (tested).

#### Randomized round trip
Status: done
**Done when:** `tests/test_domain_roundtrip.py` passes for 20 seeds in under 10 s total; `uv run pytest` otherwise
unchanged. A failure found here is fixed in the operation at fault only if the fix is a few lines and clearly
within the design above; otherwise stop and report it (with the seed and step) as `blocked`.

A property test of the whole step: every operation keeps the invariants, and the history round-trips exactly
whatever the mix. Test code only; no new production code.
- `tests/test_domain_roundtrip.py`, `@pytest.mark.parametrize("seed", range(20))`, each with its own
  `random.Random(seed)` and a fresh project built with the layer builder: source blocks P1 (5 segments), F
  (footnote, 1 segment, `excluded=True`), P2 (4 segments); target blocks Q1 (4 segments), Q2 (5 segments); nine 1:1
  beads over the non-excluded segments in order. Segment texts are three or four short words (`"w1 w2 w3"`), so
  random split offsets often succeed.
- 60 steps. Each step picks, uniformly, one of: `edit_text`, `split_segment`, `join_with_next`,
  `move_first_to_previous`, `move_last_to_next`, `merge_with_next`, `split_bead`, `set_reviewed` (random flag;
  `skim=True` half the time when setting), `exclude_block`, `include_block`, `replace_beads`, `undo`, `redo`, with
  random arguments drawn from the current database (any segment / bead / block of the project, any side, any
  offset in `1 .. len(text) - 1`, `split_bead` points drawn from the bead's own segments or `None`). For
  `replace_beads`: a random run of 1–3 consecutive beads; per side, cut the run's coverage (`beads._segments` of
  each bead, concatenated) at random points into `k = randint(1, 3)` parts, pair the parts index by index, drop
  pairs empty on both sides; `method = "length"`, `confidence = rng.random()`.
- Every step runs in its own `history.transaction`. A `DomainError` is a legal outcome: the snapshot and the
  number of operation rows must then be unchanged. After every step, `check_project(conn, "p1") == []`.
- At the end: redo until `redo` returns `None` (state R); undo until `undo` returns `None` → snapshot equals the
  initial one; redo all → snapshot equals R. Assert also that at least 20 of the 60 steps changed something (so a
  test where everything is refused can't pass silently).
- On failure, the assertion message names the seed, the step number and the operation with its arguments.
Report: 2026-10-03 — `tests/test_domain_roundtrip.py` (20 seeds × 60 steps, all operations plus undo/redo); passed first time, no production change; 1.1 s for all seeds; per seed at least 33 steps changed something; across seeds every operation succeeded 12–94 times (redo least, since new operations drop the redo stack) and was refused many times too; pytest 173 passed, 1 skipped.
Verified (/pauli, 2026-10-03, `c59178c`): matches the task; pytest 173 passed, 1 skipped (round trip 1.1 s). Braun's
outcome counts show every operation both succeeding and being refused, so the test isn't vacuous. Accepted
limitation: mid-sequence redo succeeds rarely (12 times over all seeds); long redo chains are covered by the final
redo-all / undo-all / redo-all.

### Search index
FTS5 over beads (SPEC §3.4): one row per bead, its source and target text. The old `translation_memory` table and
`api/search.py` stay as they are until Stage 6; the search API and UI over beads come in Stage 5.

Design (/pauli, 2026-10-03):
- **Kept in sync by SQL triggers** on `segments` and `beads`, not by the domain operations: triggers also fire
  for undo/redo's raw writes, the layer builder and cascading deletes, so nothing can forget to reindex.
  Excluded segments have no bead (I1), so they are never indexed, with no extra rule.
- **Bead text** on a side = its segments' `text` in document order joined with `" "` (empty string if none).
- **Folding**: tokenizer `unicode61 remove_diacritics 2` (case and accents: `é`→`e`, `à`→`a`; verified in SQLite
  3.46). Ligatures are not diacritics, so the indexed text is also folded `œ`→`oe`, `Œ`→`OE`, `æ`→`ae`, `Æ`→`AE`
  (in the trigger SQL, with nested `replace`), and queries get the same folding in Python. "desoeuvrement" then
  finds "désœuvrement". Apostrophes (`'` and `’`) are token separators, so `"l homme"` finds "l’homme" (verified).
- Search results show the **real** text: highlights are computed on the folded index text and mapped back onto
  the unfolded bead text in Python (folding only ever turns one character into two, so the map is a simple walk).

#### Bead index
Status: done
**Done when:** `tests/test_bead_index.py` passes; the randomized round trip also checks the index after every
step; `uv run pytest` otherwise unchanged.

- Migration 4 in `tradurre/db.py` (`_m004_bead_index`, appended to `MIGRATIONS`), via `_run_script`:
  - `CREATE VIRTUAL TABLE bead_index USING fts5(source, target, project_id UNINDEXED, tokenize = 'unicode61
    remove_diacritics 2')`; `rowid` = bead id.
  - "Reindex bead `X`" = `DELETE FROM bead_index WHERE rowid = X;` then `INSERT INTO bead_index (rowid, source,
    target, project_id) SELECT b.id, <fold>(<side text 'source'>), <fold>(<side text 'target'>), b.project_id FROM
    beads b WHERE b.id = X;` with `<side text>` = `coalesce((SELECT group_concat(s.text, ' ' ORDER BY bl.ord,
    s.ord) FROM segments s JOIN blocks bl ON bl.id = s.block_id JOIN documents d ON d.id = bl.document_id WHERE
    s.bead_id = b.id AND d.side = '…'), '')` and `<fold>(x)` = the four nested `replace`s above. A bead that
    doesn't exist yet (undo/redo re-points segments before re-inserting the bead) simply gets no row; its insert
    trigger indexes it.
  - Triggers: `segments_bi_ai` AFTER INSERT ON segments → reindex `new.bead_id`; `segments_bi_ad` AFTER DELETE →
    reindex `old.bead_id`; `segments_bi_au` AFTER UPDATE OF text, ord, bead_id → reindex `old.bead_id`, then
    `new.bead_id`; `beads_bi_ai` AFTER INSERT ON beads → reindex `new.id`; `beads_bi_ad` AFTER DELETE ON beads →
    `DELETE FROM bead_index WHERE rowid = old.id`. (Reindexing `NULL` is a no-op.) Bead `UPDATE`s (ord,
    confidence, method, reviewed) change no text and need no trigger.
  - Finally reindex every existing bead (`INSERT … SELECT` over all beads), so the migration is correct on a
    database that already has beads.
- `tradurre/domain/search.py` (new): `fold(text) -> str`, the same four replacements in Python (the module the
  next task extends). Nothing else yet.
- `tests/test_bead_index.py`: a helper `expected_index(conn)` that rebuilds, in Python from `segments`/`blocks`/
  `documents`/`beads`, the set `{(bead_id, fold(source), fold(target), project_id)}`, and compares it with
  `SELECT rowid, source, target, project_id FROM bead_index`. Cases (layer builder fixture with an excluded block
  and a `"désœuvrement"` segment):
  - after building: index == expected; the excluded segment's text is not in the index;
  - after each of `edit_text`, `split_segment`, `join_with_next` (cross-bead), `merge_with_next`, `split_bead`,
    `exclude_block`, `include_block`, `replace_beads`, and after undoing and redoing each: index == expected;
  - `MATCH 'desoeuvrement'`, `MATCH 'DESŒUVREMENT'` folded through `fold` → `'DESOEUVREMENT'`, and a
    `MATCH 'source : (…)'` / `'target : (…)'` column filter each find the right bead;
  - deleting the project leaves no row for its beads in `bead_index` (cascade fires the triggers);
  - `test_migrations.py`'s legacy case still passes; and a database at `user_version = 3` holding beads, then
    `init_db`, has them indexed;
  - building a 10,000-bead project (one segment per side per bead) with the layer builder takes under 5 s
    including triggers; put the measured time in the Report.
- `tests/test_domain_roundtrip.py`: after every step, also assert the index equals `expected_index` (import the
  helper from `tests/test_bead_index.py`, or move it to a small `tests/helpers.py`; either is fine).
- `test_schema.py`/`test_migrations.py` use `len(MIGRATIONS)`, so they need no change.
Report: 2026-10-03 — migration 4 (`bead_index` FTS5 + 5 triggers + backfill, SQL generated by small helpers in `db.py`); `domain/search.py` with `fold`; `tests/helpers.py` (`expected_index`/`actual_index`), used by `tests/test_bead_index.py` (14 passed) and by the round trip after every step; 10,000-bead build 1.53 s; pytest 187 passed, 1 skipped (suite 1.8 s → 4.4 s, mostly the 10k build). Note: a segment split leaves the bead's index text unchanged (the parts re-join with the same space), so that case asserts sync only.

#### Search function
Status: todo
**Done when:** `tests/test_search.py` passes; `uv run pytest` otherwise unchanged.

`tradurre/domain/search.py`, read-only (no Recorder, no transaction):
- `fts_query(text: str, side: str = "both") -> str | None`: turns what the translator typed into an FTS5
  expression. Double-quoted stretches are phrases; every other whitespace-separated word is one term; each phrase
  or term is folded, has internal `"` doubled, and is wrapped in `"…"`; they are joined with spaces (implicit AND);
  wrapped as `source : (…)`, `target : (…)` or `{source target} : (…)` for `side` `"source"`, `"target"`,
  `"both"`. Returns `None` if nothing is left (empty or only quotes/whitespace). `ValueError` for another `side`.
  Typed FTS operators (`OR`, `NEAR`, `*`, `-`) are therefore literal words, never syntax: a query can't raise an
  FTS syntax error.
- `_unfold_highlight(display: str, highlighted: str) -> str`: `highlighted` is `fold(display)` with marker
  characters `\x02` (start) / `\x03` (end) inserted (FTS5 `highlight()` output); return `display` with the
  markers at the corresponding positions (a marker never splits the two characters a ligature folded into:
  a start marker goes before the original character, an end marker after it).
- `search_beads(conn, text, side="both", project_id=None, limit=50) -> list[dict]`: `[]` if `fts_query` gives
  `None`. Matches `bead_index` (restricted to `project_id` if given), ordered by `bm25`, at most `limit` results,
  each `{"bead_id", "project_id", "title", "position", "source", "target", "reviewed"}`: `title` from `projects`,
  `position` = 1-based index of the bead in its project by `ord`, `source`/`target` = the real bead text (same
  joining as the index) with highlight markers via `_unfold_highlight`, `reviewed` a bool.
- `tests/test_search.py` (fixture: two projects built with the layer builder, one with `"Le désœuvrement de
  l’homme."`, one with `"Été"`, some beads reviewed, an excluded block containing a word found nowhere else):
  `fts_query` cases (plain words, a phrase, a stray quote, `OR`/`*`/`-` as literals, each `side`, empty →
  `None`, bad side → `ValueError`); `_unfold_highlight` with a ligature inside, at the start and at the end of a
  highlighted word; `search_beads`: "desoeuvrement" finds the bead and highlights `désœuvrement` in the real text;
  `"l homme"` matches; "ete" finds "Été"; `side="target"` doesn't find a source-only word; `project_id` restricts;
  `position` and `reviewed` correct; the excluded word finds nothing; an FTS-hostile query (`"a" OR NEAR(`) returns
  without error.

---

## Stage 2 — Import into the new model

### Reference book
(Context for the whole stage, not a task.) `library/contrefeu.fr.pdf` (Emmanuel Venet, *Contrefeu*) and `library/contrefeu.it.pdf` (*Sacro fuoco*), both
born-digital, ~38,000 words per side. Local only (see "Current state"). How every task in this stage uses it:
- **Opt-in tests.** `tests/test_library.py`, every test marked `library` and skipped when the files are missing,
  so a fresh clone stays green. They assert structural facts (logical page count, first and last sentence of
  the body, no page-number text in included blocks, reading order across page boundaries), never long excerpts.
- **Failures become committed fixtures.** A problem found on the real book gets a short synthetic reproduction in
  `tests/fixtures/` before it is fixed (same rule as Stage 0 "Test fixtures").
- **Gold chapter.** One chapter whose alignment the translator has checked by hand; see the step "Gold
  chapter" below. It is how the baseline aligner (here) and the Colab aligner (Stage 4) are compared, by numbers
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

### Structured extraction
`doc_adapter` returns blocks with kinds instead of flat text. PDF: use PyMuPDF layout (position, font size,
repetition across pages) to classify running heads, page numbers and footnotes as excluded blocks; keep the
existing glyph/ligature/hyphenation fixes. Detect two-up spreads (landscape page, text in two columns split near
the middle) and split each into two logical pages, left first; the IT reference book requires it.

### Segmentation
French/Italian sentence splitter (abbreviations, dialogue dashes, guillemets, ellipses), with regression tests
from real failure cases.

### Baseline local aligner
The current anchor heuristic plus a length-based (Gale–Church-style) cost, producing beads with confidence,
fast enough to run on import and on an arbitrary sub-range (for "re-align range").

### Gold chapter
Not a task yet: becomes one once "Baseline local aligner" is done. The translator works **outside the app**: the
developer hands out a draft, the translator corrects it, the developer brings it back to `/pauli`. Decided now so
the earlier steps don't fight it:

- **Hand-out:** a script `scripts/gold_handout.py` aligns one chapter of the reference book with the baseline
  aligner and writes `library/contrefeu.gold-draft.xlsx`: one bead per row, columns `#`, `Français`, `Italiano`,
  `Note`, one sentence per line inside a cell. The translator fixes the alignment by **moving sentences between
  cells and inserting/deleting rows**, never by changing words; anything else (an extraction error, a doubt) goes
  in `Note`. A short instruction sheet (Italian) is the first worksheet. Default chapter: the first chapter of the
  body; the developer may pick another, ~200–400 sentences, with some 1:2/2:1 and unmatched material.
  (`.xlsx` because it is what a non-technical translator can edit by cut/paste on Windows; `openpyxl` goes in the
  dev dependency group only, not at runtime.)
- **Intake:** the developer saves the corrected file as `library/contrefeu.gold.xlsx`; `scripts/gold_intake.py`
  converts it to `library/contrefeu.gold.tsv` (`source<TAB>target` per bead) after validating it: the
  concatenated text of each side, whitespace-normalized, must equal the draft's exactly (nothing lost, duplicated,
  reordered or reworded). Violations are listed by row so the developer can ask the translator; notes are
  printed for `/pauli` (they are likely extraction or segmentation bugs).
- **Format independent of segmentation:** a gold bead is stored as text, and scoring maps every bead to a
  character span of each side's normalized chapter text. Metrics are bead-boundary precision/recall/F1 on those
  spans, so the gold stays valid when the segmenter or extractor changes later.
- **Scoring:** `scripts/gold_score.py <aligner>` prints the metrics plus the worst-scoring stretches. Its result
  is recorded in the `Report:` of every aligner task from then on.

### Import API and minimal UI
Upload two files → project created and aligned → opens in the project page. Until Stage 3 exists, that page is
a plain read-only bead list (no virtualization), so every task here leaves a working app. Warnings and run
metadata (counts, timings; SPEC §4 "Debuggable") stored on the project, in tables added here by a migration. A debug endpoint
returns `check_project`'s result for a project.

---

## Stage 3 — Review view

Decided (user, 2026-10-03): the review screen permits **cut/copy/paste between rows** ("the user is king and
responsible"). A cut at one row's edge pasted at the adjacent edge of the neighbouring row leaves the edition's
text unchanged and is recorded as a bead-boundary move; any other paste is a text edit (original text kept,
undoable). SPEC §3.3 gets a line for it when this stage is planned (wording to agree with the user then).

The main screen (SPEC §3.3): virtualized bead list, confidence and unmatched highlighting, next-problem
navigation, skim-review pass and per-bead reviewed toggle, keyboard corrections, inline plain-text segment editing, excluded blocks
revealable, undo/redo, re-align range. Plain text editing; TipTap is not used here.

---

## Stage 4 — Colab round trip

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

## Stage 5 — Search and export

Search UI on the new index with context expansion and jump-to-bead (SPEC §3.4). Exports: TMX/TSV corpus,
per-edition .txt/.docx, project bundle as backup (SPEC §3.5).

---

## Stage 6 — Retire the old model

Remove the `pairs` table and its API, the old import wizard, `resplit`, the TipTap per-pair editor, the
old artifact format and `services/importer.py` (unused since "Repo hygiene"); update `CLAUDE.md`, `README.md` and the e2e tests. Release v0.2.0.
