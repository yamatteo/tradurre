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

## Current state, in brief (2026-10-04)

- **Two models coexist until Stage 7.** The v0.1 `pairs` table, its `/api/v1` API, import wizard, TipTap pair
  editor and `aligner.py` still exist, unused by the new path. The new model (migrations 2–5: documents, blocks,
  segments, beads, operations, `bead_index`, runs, warnings) is served by `/api/v2/books` (`api/books.py`) and the
  book screen (`BookView.vue`, `/book/:id`).
- **Import** (Stage 3): .txt/.docx/.pdf pairs. Layout-aware PDF extraction, front/back matter by publishing
  markers, French/Italian segmentation, the length aligner; the run's stats and warnings are stored and shown
  under "Import log". Reference book: ~5 s, 1232 beads, 2 one-sided, 9 below confidence 0.5; against the gold,
  alignment F1 0.995, exclusion P 1.000 R 0.902.
- **Book screen** (Stage 2): reading and keyboard navigation, `n` next unreviewed, `r` reviewed, "Show excluded",
  every SPEC §3.3 single-bead correction (keys and header buttons), inline segment editing, persistent undo/redo.
  No problem highlighting, ranges, original text or re-align yet (Stage 4).
- **Re-planned with the user (2026-10-04), SPEC changed accordingly:** review is one mode, problem-first: jump to
  the next likely problem, correct, mark one bead, a selected run, or everything up to here as reviewed. The
  timed scroll "skim review" is dropped. The Colab aligner is **parked** (SPEC §3.2, §5): it returns only if a
  gold book scores below 0.95. A typical book is 1,000–5,000 sentences a side; performance targets are at 5,000
  beads. Order: Stage 4 → Stage 6 → Stage 7 (v0.2). Then the translator reviews *Contrefeu* in v0.2 for a true
  gold (the current one was made by the user, the developer), and maybe a second book, to score the aligner again.
- `uv run pytest`: 391 passed, also on a fresh clone (tests read only committed synthetic fixtures; `-m library`
  tests run only where `library/contrefeu.*.pdf` exists, and assert counts only).
- `npm run type-check` passes; releases build with `npm run build`. `npm run test:e2e` (29 tests) runs on its own
  backend (:8001, throwaway `.e2e.db`) and Vite (:5174), never the user's database. Setup per machine: `npx
  playwright install chromium` (on Ubuntu 26.04 with `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64`); tests
  use the full Chromium headless (`channel: 'chromium'`).
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

The correction screen of Stage 2 grows into the review screen of SPEC §3.3 (as changed 2026-10-04): one mode,
problem-first. Plain text editing; TipTap is not used here. Steps in order; only the first three are tasks yet.

Decisions carried into this stage:
- (user, 2026-10-03) `reviewed` and `confidence` stay separate signals. A correction sets the touched beads to
  `manual`/1.0 but leaves their reviewed mark as SPEC §3.3 says; "done with the book" = every bead reviewed.
- (Pauli, 2026-10-04, measured) the length aligner seldom emits 1:0/0:1; a sentence with no counterpart usually
  lands in a 2:1/1:2 bead of confidence ~0.4–0.45, against ≥ 0.78 for an ordinary 1:1. So "low confidence" is
  **< 0.5**, and the multi-segment toggle shows the rest.
- (user, 2026-10-03) cut/copy/paste between rows: a cut at one row's edge pasted at the adjacent edge of the
  neighbouring row is a bead-boundary move; any other paste is a text edit (original text kept, undoable). SPEC
  §3.3 gets a line for it when that step is planned (wording to agree with the user then).
- Keys must work on an Italian Windows layout: letters, Shift+letters, arrows, Enter, Tab, Ctrl+Z/Y only (no `[`,
  `]`, `/`, `\` and the like, which need AltGr or move around). Rare range commands get header buttons, no key.

### Problem navigation
Status: done
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes, including the new
`frontend/e2e/review.spec.ts`; `uv run pytest` is unchanged (391 passed).
Report: 2026-10-04 — `src/review.ts` (`LOW_CONFIDENCE`, `isProblem`); `BookView.vue`: `p`/`P`, "Next problem", "Highlight multi-segment", `problems N`; `BeadRow.vue`: `data-problem`, amber border, absolute `s:t · c.cc` badge; `e2e/review.spec.ts` 4 tests; type-check passes, e2e 33 passed (29 + 4), pytest 391 passed.

Frontend only (the API already returns each bead's `confidence`). SPEC §3.3: "Low-confidence beads and unmatched
(1:0, 0:1) beads stand out visually; there are shortcuts to jump to the next one", and the multi-segment toggle.
- New `frontend/src/review.ts`: `export const LOW_CONFIDENCE = 0.5` and `export function isProblem(bead: BookBead,
  multi: boolean): boolean`, true when the bead is **not reviewed** and (`confidence < LOW_CONFIDENCE`, or either
  side is empty, or `multi` and either side holds more than one segment). Reviewed beads are never problems: a
  bead the translator checked and accepted as it is stops coming back. A corrected bead is `manual`/1.0, so it
  stops being a problem unless it is one-sided.
- `BookView.vue`:
  - `showMulti` ref, a header checkbox "Highlight multi-segment" (`data-testid="show-multi"`), next to "Show
    excluded".
  - `problemCount` computed, shown in the header before the progress as `problems {n}`
    (`data-testid="problem-count"`).
  - Keys: `p` jumps to the next problem after the current bead, `P` (Shift+p, `event.key === 'P'`) to the
    previous one; both wrap around like `n` and keep the current side; with none, `say('No problems left')`.
    Add them to the `actions` map. A header button "Next problem" (`data-testid="next-problem"`, title "P") does
    what `p` does.
  - Pass `:multi="showMulti"` to every `BeadRow` (toggling re-renders all rows once; that's fine).
- `BeadRow.vue`: prop `multi: boolean`; computed `problem = isProblem(props.bead, props.multi)`; attribute
  `data-problem` on the row; left border `border-amber-400` when `problem` (reviewed stays `border-green-500`,
  otherwise transparent as now); and on problem rows a badge `{source count}:{target count} · {confidence with 2
  decimals}` (`data-testid="problem-badge"`, `text-xs text-amber-700`), **absolutely positioned** in the row's top
  right corner (row `relative`), so marking a bead reviewed never changes the row's height (Stage 2 rule).
- `frontend/e2e/review.spec.ts` (new; import through the API as the other specs do, with the `SOURCE`/`TARGET` texts
  of `tests/test_books_api.py`, which give 3 beads, one of them a 2:1 below 0.5):
  - the low-confidence bead has `data-problem="true"` and a badge `2:1 · 0.xx`; the others have no badge; the
    header shows `problems 1`;
  - `p` from the first bead selects the problem bead; `p` again wraps to it again; `P` likewise;
  - `r` on it: the badge disappears, `problems 0`, the row's height is unchanged; `p` then shows "No problems
    left";
  - after undoing the review mark, merge the first two 1:1 beads with `m` (a 2:2 bead, manual/1.0, not a
    problem): `problems 1` (the 2:1 bead) with the toggle off, `problems 2` with "Highlight multi-segment" on, and
    the 2:2 row gets `data-problem="true"`.
- Don't change the API, the other rows' layout, or the existing keys.

### Reviewed runs and "up to here"
Status: todo
**Done when:** `uv run pytest` passes (skim tests removed, new ones below); `npm run type-check` passes; `npm run
test:e2e` passes with the new tests in `frontend/e2e/review.spec.ts`.

SPEC §3.3 "Reviewed marks": set or clear the mark on one bead, on a selected run of beads, and on every bead from
the top of the book to the current one. The skim review is gone from SPEC, so its code goes too.
- **Remove skim**: `skim` parameter of `domain/beads.py:set_reviewed` (and the `skim_review` operation kind),
  `BookReviewedRequest.skim` (`models.py`), its use in `api/books.py:reviewed` and in `client.ts`
  (`setReviewed` sends `{bead_ids, reviewed}`). Delete `test_skim_marks_coalesce`, `test_skim_unmark_is_an_error`
  (`tests/test_domain_beads.py`), `test_skim_marks_coalesce_into_one_undo`, `test_skim_unmark_is_400`
  (`tests/test_books_corrections_api.py`), and the skim branch of `tests/test_domain_roundtrip.py` (it always
  passes `skim=False` now: drop the third argument). Keep the generic `coalesce` mechanism of `history.py` and its
  tests (`tests/test_domain_history.py` uses its own kind names; leave it).
- **Selected run** (`BookView.vue`): `Shift+↓`/`Shift+↑` extend a run from an anchor (the bead current when the
  run started) to the new current bead; `Shift+click` on a row does the same; any plain move (arrows without
  Shift, `n`, `p`, a click) clears the run. Rows in the run get `data-in-run="true"` and a `bg-blue-50/50`
  background. Keep the Stage 2 scale rule: membership is a `shallowReactive<Record<number, true>>` map updated by
  difference (like `currentRow`), never a per-row computed over indices.
- `r` with a run: if any bead in the run is unreviewed, mark all of them reviewed, else clear all; one request
  (`setReviewed(ids, flag)`), one operation, one undo; the run stays selected. Without a run, `r` is as now.
- `R` (Shift+r, `event.key === 'R'`): mark every bead from the first to the current one reviewed (one request
  with the ids of the unreviewed ones among them; nothing to do → `say('Already reviewed up to here')`); the
  status line says `Reviewed up to here (N beads)`. A header button "Reviewed up to here"
  (`data-testid="reviewed-up-to-here"`, title "Shift+R") does the same.
- Tests: `tests/test_books_corrections_api.py`: marking 3 beads in one request is one undo step; a request with
  `skim` in the body is ignored or rejected as Pydantic does by default (assert whichever, don't add code for it).
  `review.spec.ts`: Shift+↓ twice then `r` marks 3 beads and Ctrl+Z clears all 3; a run with mixed marks → `r`
  marks all; `R` on the third bead marks beads 1–3 and leaves the rest; a plain ↓ clears the run.

### Range exclude/include
Status: todo
**Done when:** `uv run pytest` passes with the new domain and API tests; `npm run type-check` passes; `npm run
test:e2e` passes with the new tests in `frontend/e2e/review.spec.ts`.

SPEC §3.3: "exclude/include every block from the start of the edition up to the current bead, or from it to the
end". Agreed (user, 2026-10-04): one operation, one undo; range *include* skips the layout kinds
(`running_head`, `page_number`, `footnote`), which only single-block Include brings back.
- `tradurre/domain/blocks.py`: factor the bodies of `exclude_block`/`include_block` into `_exclude(rec, conn,
  block)` / `_include(rec, conn, project_id, block)` working on an existing `Recorder`; the two public functions
  keep their behaviour and messages. New:
  - `exclude_range(conn, project_id, bead_id, side, to: Literal["start", "end"]) -> int`: the blocks of that side's
    document with `ord <=` (to start) the ord of the block holding the bead's **last** segment on that side, or
    `ord >=` (to end) that of the block holding its **first**; of those, every block not excluded is excluded, in
    document order, in **one** `Recorder`, recorded as `exclude_range`. A block that straddles the bead goes
    whole (blocks are the unit). DomainError "The bead has no {side} segment" if that side is empty, "Nothing to
    exclude" if no block qualifies.
  - `include_range(...)`, same signature and range, over excluded blocks whose kind is not in `{"running_head",
    "page_number", "footnote"}`, included in document order in one `Recorder`, recorded as `include_range`;
    "Nothing to include" if none. Each block lands as `include_block` places it (inside the surrounding bead or
    as a new unmatched bead).
- `api/books.py` + `models.py`: `POST /books/{id}/blocks/exclude-range` and `/blocks/include-range`, body
  `BookRangeRequest(bead_id: int, side: Side, to: Literal["start", "end"])`, through `_correct` as the other
  corrections. `client.ts`: `excludeRange`, `includeRange`.
- `BookView.vue`/`BeadActions.vue`: four header buttons, no keys: "Exclude to start", "Exclude to end", "Include
  to start", "Include to end" (`data-testid="exclude-to-start"`, …), acting on the current bead and side; after
  success `say('Excluded N blocks (Ctrl+Z to undo)')` / `Included N blocks`, N = the difference in the book's
  excluded-block count.
- Tests (`tests/test_domain_blocks.py`, `tests/test_books_corrections_api.py`):
  exclude to start / to end take the right blocks and leave invariants I1–I5 holding (use the existing checker);
  one undo restores everything; a straddling block goes whole; include to start skips a `page_number` block and
  restores a `front_matter` one; the error cases. `review.spec.ts`: "Exclude to start" on the second bead hides
  the first bead's source text, "Show excluded" reveals it, Ctrl+Z brings it back.
- Don't change the single-block exclude/include behaviour or keys.

### Screen layout and shortcuts
Not ready: waits for the user's design exploration (Claude Design, 2026-10-04, from Pauli's brief: 2–3 layout
variants of the review screen, a shortcuts panel, the row states). Then a Braun task rebuilds the chosen variant
in `BookView.vue`/`BeadRow.vue`/`BeadActions.vue` with Tailwind, keeping the binding rules (rows never change
height, the 5,000-row list stays light, keys valid on an Italian layout). The shortcuts panel is built from the
same table the key handler uses. No book text in the mockups (invented sample content only).

### Original text and revert
Not ready. SPEC §2: the extracted text is kept "so the translator can always compare or revert"; `original_text`
is stored but not in the API. Show edited segments distinctly, their original on demand, and a "revert to
original" (a text edit, undoable).

### Re-align range
Not ready. SPEC §3.3: select a stretch between two trusted beads and re-run the local aligner on just that stretch
(the selected run of "Reviewed runs" is the natural selection; `domain/replace.py` has `replace_beads`).
Decided (user, 2026-10-04): every bead in the stretch is replaced, reviewed or not, and the new beads start
**unreviewed** (SPEC §3.3: "Beads produced by an aligner start unreviewed"); one operation, so one undo restores
the old beads and their marks.

### Cut/copy/paste between rows
Not ready. See the decision above; agree the SPEC wording with the user first.

### Scale check at 5,000 beads
Not ready. Stage 2's e2e checks pass at 10,000 beads (load < 5 s, 20 ↓ < 2 s, `r` < 1.5 s) with whole-book
refetch and no virtualization. Re-measure after the steps above add rows' work; virtualize or go incremental only
if a check at 5,000 fails.

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

Search UI on the new index with context expansion and jump-to-bead (SPEC §3.4). Kept here rather than pulled
forward (user, 2026-10-03): alignment quality first. Exports: TMX/TSV corpus,
per-edition .txt/.docx, project bundle as backup (SPEC §3.5).

---

## Stage 7 — Retire the old model

Remove the `pairs` table and its API, the old import wizard, `resplit`, the TipTap per-pair editor, the
old artifact format and `services/importer.py` (unused since "Repo hygiene"); update `CLAUDE.md`, `README.md` and the e2e tests. Release v0.2.0.
