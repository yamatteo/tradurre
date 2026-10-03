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
- One connection per request; every write handler is one `BEGIN IMMEDIATE` transaction. No undo/history.
- Python 3.14 only (`.python-version`, `requires-python`, launcher). Stage 0 is complete.
- `uv run pytest`: 71 passed, 1 skipped, also on a fresh clone (tests read only committed synthetic fixtures).
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

#### Text and alignment tables
Status: todo
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
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    method     TEXT NOT NULL CHECK (method IN ('anchor', 'length', 'embedding', 'llm', 'manual')),
    reviewed   INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0, 1)),
    UNIQUE (project_id, ord)
);
CREATE TABLE segments (
    id            INTEGER PRIMARY KEY,
    block_id      INTEGER NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    ord           INTEGER NOT NULL,
    text          TEXT NOT NULL,
    original_text TEXT NOT NULL,    -- as extracted; never changed after import
    bead_id       INTEGER REFERENCES beads(id),   -- NULL iff the block is excluded
    UNIQUE (block_id, ord)
);
CREATE INDEX idx_segments_bead ON segments(bead_id);
```

- `segments.bead_id` deliberately has no `ON DELETE` action: deleting a bead that still has segments must fail,
  so no domain bug can silently orphan text. (Deleting a project still works: the cascade removes beads and
  segments in the same statement, and SQLite checks the constraint at statement end.)
- `tests/test_schema.py`, on a fresh `init_db`'d temp database (with `PRAGMA foreign_keys=ON`, i.e. via
  `get_connection`): insert a project, two documents, a block per document, two beads, segments pointing at them;
  then assert:
  - deleting a bead that a segment points to raises `sqlite3.IntegrityError`;
  - deleting the project removes every row in `documents`, `blocks`, `segments`, `beads`;
  - a duplicate `(block_id, ord)` and a duplicate `(project_id, ord)` raise `IntegrityError`;
  - `kind = 'chapter'`, `method = 'magic'`, `confidence = 1.5`, `side = 'left'` each raise `IntegrityError`.
- Don't touch `pairs`, the FTS table or the API.

### Domain operations
A service layer, independent of HTTP, implementing every SPEC §3.3 correction (segment split/join/edit, block
exclude/include, bead boundary moves, merge/split, review mark) as transactional operations that record an
inverse in the operation log (its table and payload format are designed here and added as a migration);
also the `ord` spacing policy and gap renumbering. Undo/redo on top of it. Also one bulk primitive, "replace the beads covering a
segment range with a new bead list", which import (Stage 2), re-align range (Stage 3) and loading a Colab
alignment file (Stage 4) all build on.

### Invariants
A checker for bead coverage and monotonicity (every non-excluded segment in exactly one bead, in order), run in
tests after every operation and available as a debug endpoint.

### Search index
FTS5 over beads (concatenated source / target text of each bead), kept in sync by the domain operations; excluded
blocks not indexed. Tokenizer `unicode61 remove_diacritics 2` so matching ignores case and accents (SPEC §3.4);
test with "desoeuvrement"/"désœuvrement" (note œ is not a diacritic: decide folding explicitly).

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
metadata (counts, timings; SPEC §4 "Debuggable") stored on the project, in tables added here by a migration.

---

## Stage 3 — Review view

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
