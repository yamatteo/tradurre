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
- One shared `sqlite3` connection across FastAPI's threadpool; no undo/history; `tests/test_aligner.py` depends
  on the gitignored `library/` folder and fails to collect.
- No user data needs migrating: the new model can start from an empty database.

---

## Stage 0 — Groundwork

Make the repo a safe place to rebuild in, without changing product behaviour.

### Test fixtures
Status: todo
**Done when:** `uv run pytest` collects and passes with a fresh clone. `test_aligner.py` uses small fixture
files committed under `tests/fixtures/` (short excerpts or synthetic text with the same properties: wrapped
lines, page numbers, shared names), not `library/`.

### Database access
Status: todo
**Done when:** each request gets its own connection (or all access goes through one lock), multi-statement
operations run inside an explicit transaction that rolls back on error, and a test shows that a failing
operation leaves no partial change.

### Dependency hygiene
Status: todo
**Done when:** `pytest` and `httpx` are in a dev dependency group, not runtime dependencies; dead code
(`/import/preview` and its client call, the unreachable `return` in `import_artifact`) is removed; tests pass.

---

## Stage 1 — New data model

Separate text from alignment (SPEC §2). Built alongside the old `pairs` model, which stays working until
Stage 6 removes it.

### Schema
Tables for documents (one per edition), blocks (with kind and excluded flag), segments (text and original
text), beads (source/target segment ranges, confidence, method, reviewed), an operation log, and per-project
warnings/run metadata. Ordering that doesn't require renumbering the whole book on every insert.

### Domain operations
A service layer, independent of HTTP, implementing every SPEC §3.3 correction (segment split/join/edit, block
exclude/include, bead boundary moves, merge/split, review mark) as transactional operations that record an
inverse in the operation log; undo/redo on top of it.

### Invariants
A checker for bead coverage and monotonicity (every non-excluded segment in exactly one bead, in order), run in
tests after every operation and available as a debug endpoint.

### Search index
FTS5 over beads (concatenated source / target text of each bead), kept in sync by the domain operations; excluded
blocks not indexed.

---

## Stage 2 — Import into the new model

### Structured extraction
`doc_adapter` returns blocks with kinds instead of flat text. PDF: use PyMuPDF layout (position, font size,
repetition across pages) to classify running heads, page numbers and footnotes as excluded blocks; keep the
existing glyph/ligature/hyphenation fixes.

### Segmentation
French/Italian sentence splitter (abbreviations, dialogue dashes, guillemets, ellipses), with regression tests
from real failure cases.

### Baseline local aligner
The current anchor heuristic plus a length-based (Gale–Church-style) cost, producing beads with confidence,
fast enough to run on import and on an arbitrary sub-range (for "re-align range").

### Import API and minimal UI
Upload two files → project created and aligned → opens in the (Stage 3) review view. Warnings stored on the
project.

---

## Stage 3 — Review view

The main screen (SPEC §3.3): virtualized bead list, confidence and unmatched highlighting, next-problem
navigation, "reviewed up to here", keyboard corrections, inline plain-text segment editing, excluded blocks
revealable, undo/redo, re-align range. Plain text editing; TipTap is not used here.

---

## Stage 4 — Colab round trip

Project bundle format (text layer) and alignment file format (beads over bundle segments), both versioned.
Adapt `pipeline.py`/`pipeline_cli.py` and the bertalign/LLM-judge stages to consume a bundle and emit native
many-to-many beads. Loading an alignment file replaces only unreviewed regions. A notebook for Colab.

---

## Stage 5 — Search and export

Search UI on the new index with context expansion and jump-to-bead (SPEC §3.4). Exports: TMX/TSV corpus,
per-edition .txt/.docx, project bundle as backup (SPEC §3.5).

---

## Stage 6 — Retire the old model

Remove the `pairs` table and its API, the old import wizard, `resplit`, the TipTap per-pair editor and the
old artifact format; update `CLAUDE.md`, `README.md` and the e2e tests. Release v0.2.0.
