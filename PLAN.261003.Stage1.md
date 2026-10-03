# Tradurre — Plan, archived: Stage 1

Completed stage moved out of `PLAN.md` on 2026-10-03; kept as the record of its tasks, reports and
verifications. Stage numbers mentioned below refer to the plan at that date.

## Stage 1 — New data model
Done (2026-10-03).

Separate text from alignment (SPEC §2). Built alongside the old `pairs` model, which stays working until
Stage 7 removes it.

### Schema
Decided (user, 2026-10-03): "reviewed" is a **per-bead flag** in storage, editable one bead at a time; no "reviewed
up to here" position. Bulk marking comes from **skim review**, a pass the translator starts deliberately (typically
once, after import), not a default mode: beads scrolled past during the pass are marked reviewed (Stage 4).
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
  payload is designed), the search index (step "Search index"), and import runs/warnings (Stage 3, "Import warnings and run metadata").
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
range (Stage 4) and loading a Colab alignment (Stage 5) build on. Code lives in a new package `tradurre/domain/`;
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
fixes it with an edit, and real hyphenation is repaired at extraction (Stage 3).

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

The bulk primitive behind re-align range (Stage 4) and loading a Colab alignment (Stage 5). It replaces a run of
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
    from `layer.py`), so Stage 5 can replace several runs in one operation; and
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
`api/search.py` stay as they are until Stage 7; the search API and UI over beads come in Stage 6.

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
Verified (/pauli, 2026-10-03, `434b8a2`): matches the task; pytest 187 passed, 1 skipped (188 with PyMuPDF installed;
see Stage 3). The narrowed split assertion is right. The 10,000-bead timing test adds ~1.5 s to every run;
acceptable for now.

#### Search function
Status: done
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
Report: 2026-10-03 — `domain/search.py`: `fts_query`, `_unfold_highlight` (markers `START`/`END` exported), `search_beads`; `tests/test_search.py` 18 passed; pytest 206 passed (baseline 188 passed, 0 skipped: PyMuPDF was already in the venv). Detail: terms with no letter or digit (`-`, a lone `"`) are dropped, since FTS5 gives them no tokens; a query of only such terms returns `None`.
Verified (/pauli, 2026-10-03, `9cfd707`): matches the task; pytest 206 passed. Dropping token-less terms is
equivalent to keeping them (FTS5 ignores them in an AND, and alone they match nothing) and makes `None` honest.
The `START`/`END` control characters can't collide with book text: extraction strips control characters
(`normalize_ocr_artifacts`). Stage 6's API turns them into markup.
