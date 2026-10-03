# Tradurre — Plan, archived: Stage 0

Completed stage moved out of `PLAN.md` on 2026-10-03; kept as the record of its tasks, reports and
verifications. Stage numbers mentioned below refer to the plan at that date.

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
it is dead code, removed in Stage 7.

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
  type-check alone then stands as the evidence). No e2e test: the wizard is deleted in Stage 7.
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
