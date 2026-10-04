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
  Restyled to design variant A; smooth at 5,000 beads. Stage 4 done; Stage 6 (search, then export) next. On the reference book the problem flags catch
  none of the 15 real errors: review is reading-first; better signals come after v0.2.
- **Re-planned with the user (2026-10-04), SPEC changed accordingly:** review is one mode, problem-first: jump to
  the next likely problem, correct, mark one bead, a selected run, or everything up to here as reviewed. The
  timed scroll "skim review" is dropped. The Colab aligner is **parked** (SPEC §3.2, §5): it returns only if a
  gold book scores below 0.95. A typical book is 1,000–5,000 sentences a side; performance targets are at 5,000
  beads. Order: Stage 6 → Stage 7 (v0.2), confirmed 2026-10-04. Then the translator reviews *Contrefeu* in v0.2 for a true
  gold (the current one was made by the user, the developer), and maybe a second book, to score the aligner again.
- `uv run pytest`: 414 passed, also on a fresh clone (tests read only committed synthetic fixtures; `-m library`
  tests run only where `library/contrefeu.*.pdf` exists, and assert counts only).
- `npm run type-check` passes; releases build with `npm run build`. `npm run test:e2e` (62 tests; the three timing tests run last, alone, in project `scale`) runs on its own
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

Post-Stage-4 review (user, 2026-10-04):
- **Order kept:** Stage 6, Stage 7, v0.2; the translator starts with v0.2 (no earlier preview).
- **SPEC §3.4 changed (agreed 2026-10-04):** a word matches every word it begins (`désœuvr` finds `désœuvrement`,
  `désœuvré`), case and accents folded; a quoted phrase matches those words in sequence, each of them by its
  beginning too; one query, matched against the source, the target, or **either** (a bead matches if its source
  or its target contains the whole query; never terms split across sides).

What exists: `domain/search.py` (`fts_query`, `search_beads`, highlights moved back onto the real text through
ligature folding), the `bead_index` FTS5 table (`unicode61 remove_diacritics 2`, kept by triggers in `db.py`;
excluded segments have no bead, so they are never indexed), `tests/test_search.py`. No `/api/v2` search route,
no search page for books (`SearchView.vue` at `/search` is the v1 pairs search), no export for books. Steps in
order: search, then export (edition export, then the project bundle).

### Search

#### Search: word beginnings, either side, and the API
Status: done
Report: 2026-10-04 — `fts_query` makes every token a prefix (`"tok" * + …` per phrase) with sides `source`/`target`/`either` (`source : (B) OR target : (B)`), `search_beads` takes `offset`; `GET /api/v2/search` with `BookSearchSpan`/`BookSearchResult` (named so beside the v1 `SearchResult`), `booksApi.search`; `fts_query` tests rewritten, 4 new domain tests and 3 API tests (`tests/test_books_search_api.py`), all 7 failing on the old code; pytest 411 passed, type-check clean, e2e 61 passed.
Verified (Pauli, 2026-10-04): Done when holds (commit 47b0404; pytest 411 here). The `BookSearch*` names are
right (the v1 `SearchResult` still exists until Stage 7); the page task below uses them. Checked: with `either`, a
side that doesn't match the whole query gets no stray highlight (`highlight()` marks only the matching column).
**Done when:** `uv run pytest` passes with the updated and new tests below (the new behaviour tests fail on the old
code); `npm run type-check` passes; `npm run test:e2e` unchanged.

Checked (Pauli, 2026-10-04, FTS5 in memory): `source : ("desoeuvr" * + "total" *)` matches "désoeuvrement total"
with the whole tokens highlighted, and `source : (B) OR target : (B)` keeps the terms on one side, unlike
`{source target} : (B)`.
- `domain/search.py:fts_query(text, side="either")`: sides `source`, `target`, `either` (`both` is gone; the
  `ValueError` names the three). Each quoted stretch or bare word is folded (`fold`) and split into tokens by
  `[^\W_]+` (what `unicode61` keeps); a stretch without tokens is skipped; a stretch becomes the FTS phrase of its
  tokens, each a prefix: `"tok1" * + "tok2" *`. The phrases, joined by spaces (all required), form the body `B`;
  the result is `source : (B)`, `target : (B)`, or `source : (B) OR target : (B)`. Tokens are alphanumeric, so
  nothing the translator types is ever parsed as FTS syntax. Update the docstring.
- `search_beads(..., side="either", ..., limit=50, offset=0)`: `LIMIT ? OFFSET ?`; nothing else changes.
- `tests/test_search.py`: rewrite the `fts_query` tests to the new form, e.g. `fts_query("homme partit")` ==
  `'source : ("homme" * "partit" *) OR target : ("homme" * "partit" *)'`, `fts_query('"de l homme" mot',
  "source")` == `'source : ("de" * + "l" * + "homme" * "mot" *)'`, ligature `"Désœuvrement"` → `"Désoeuvrement" *`,
  stray quote `homme "partit` → `"homme" * "partit" *`, operators `a OR b * -c` → `"a" * "OR" * "b" * "c" *`,
  nothing searchable (`"" * -`) → None. Existing behaviour tests move from `both` to `either`. New, on the
  fixture: `désœuvr` (source) finds A with `désœuvrement` highlighted whole; `"part sans"` finds B; `ozio` with
  `either` finds A; `désœuvrement ozio` with `either` finds nothing (split across sides); `offset=1` on a query
  matching A and B returns one bead, not the first one returned without offset.
- API, in `api/books.py` (prefix `/api/v2`): `GET /search?q=&side=either&book=&limit=50&offset=0` →
  `list[SearchResult]`. `side: Literal["source", "target", "either"]`, `limit` 1–200, `offset` ≥ 0; `book`
  optional, 404 if given and unknown. `models.py`: `SearchSpan(text: str, match: bool)`; `SearchResult(bead_id,
  book_id, title, position, source: list[SearchSpan], target: list[SearchSpan], reviewed)`, the spans cut from
  the START/END markers (no markup in strings: the page renders spans, never HTML). `client.ts`:
  `booksApi.search(q, side, book?, offset?)` and the types.
- API tests (`tests/test_books_search_api.py`, new): import two small books (as `tests/test_books_api.py` does),
  search a word beginning across both, with `book=` one of them, `side=target`, spans join back to the bead's text
  with the match marked, unknown book 404, empty `q` → `[]`.
- The v1 search (`api/search.py`, `SearchView.vue`, `translation_memory`) is untouched (Stage 7 removes it).

#### Search at library scale
Status: done
Report: 2026-10-04 — new `scripts/search_scale.py`, no app change. Build 21.1 s, 40 books, 100,000 beads, 101.8 MB. Medians (5 runs): `d` 139.2 ms, `de` 85.2, a full word 11.7, a two-word phrase 1.5, `d` source only 84.4, `d` offset 200 144.1, a full word in one book 1.1 ms; worst 144.1 ms < 1,000 (`d` matches ~80% of beads: 2 of the 30 syllables start with d); pytest 411 passed.
Verified (Pauli, 2026-10-04): Done when holds (commit 199b5db; rerun here: worst median 143.1 ms). Real French
makes `d` match nearly every bead (`de`, `des`, `du`, `dans`) against ~80% here: same order of magnitude, so the
margin (7×) stands. No `prefix=` index needed.
**Done when:** `uv run python scripts/search_scale.py` runs and every query's median is < 1,000 ms (report the
build time and every number); `uv run pytest` unchanged.

SPEC §5: "a search across dozens of books returns in under a second". Prefix queries without an FTS5 `prefix=`
index scan the term range, and `bm25` ranks every match before `LIMIT`: a short prefix on a full library is the
risk. This task only measures: **if a query is over 1 s, don't optimize**: stop (`blocked`) with the numbers.
- New `scripts/search_scale.py` (like `scripts/gold_score.py`: argparse, output to the terminal, nothing stored):
  in a temporary database (`init_db`), 40 books × 2,500 beads, each bead 1:1, 10 sentences per paragraph block
  (`create_document`, `append_beads`, in `transaction`). Sentences: 12 words from `random.Random(0)` over a
  vocabulary of 20,000 pseudo-words of 2–4 syllables (e.g. syllables `de la re mi to pa an ou in ch es`…), source
  and target drawn independently. Then queries through `search_beads(conn, q, side)`, each run 5 times, median
  and max in ms: a one-letter prefix (`d`), a two-letter prefix (`de`), a full vocabulary word, a two-word phrase
  taken from a real sentence, each with `either`; the one-letter prefix also with `source`, and with `offset=200`;
  and the full word scoped to one book. Print the build time, the beads and index size, and one line per query.
- No change to the app code.

#### Search context and opening a book at a bead
Status: done
**Done when:** `uv run pytest` passes with the new tests; `npm run type-check` passes; `npm run test:e2e` passes
with the new test (failing before the change).

SPEC §3.4: "expanding a result shows the surrounding beads; one click opens the project at that bead".
- API (`api/books.py`): `GET /books/{id}/beads/{bead_id}/context?around=2` (`around` 1–10) →
  `list[ContextBead]`: the beads whose `ord` is within `around` beads before and after it (fewer at the book's
  edges), in order, each `{bead_id, position, source, target, reviewed}` with the sides' text joined by spaces as
  `search.py:_bead_text` does. 404 for an unknown book or a bead of another book. `client.ts`:
  `booksApi.context(id, beadId, around?)`.
- Book screen: `/book/:id?bead=<beadId>` makes that bead current on load (source side), scrolled into view with
  `block: 'center'`; a bead that no longer exists → the first bead and `say('That bead no longer exists: the book
  changed since the search')`. Without `bead` nothing changes.
- Tests: `tests/test_books_search_api.py`: context of the second bead with `around=1` is 3 beads, of the first
  is 2, a bead of another book 404. e2e (`book-view.spec.ts`): open `/book/<id>?bead=<fourth bead>` → that row
  is current; with a deleted bead id (`POST beads/{third}/merge-next` deletes the fourth bead: `_merge` keeps
  the first id) → the first bead is current and the status shows the message.
Report: 2026-10-04 — `GET …/beads/{bead_id}/context` (`ContextBead`), `booksApi.context`, BookView `?bead=` (current,
centred; missing bead → first bead and the message); 3 API tests and 1 e2e test, all failing on the old code; pytest
414 passed, type-check clean, e2e 62 passed (one earlier full run failed the 5,000-bead timing test once; two reruns
and five runs of it alone passed, Ctrl+Z after the second move 384–457 ms against 500).
Verified (Pauli, 2026-10-04): Done when holds (commit 1f2ab3e). The occasional 5k failure is the test's clock, not the
app: on a 5,000-bead book the server answers a move or an undo in ~75 ms (1.5 MB of JSON; Pauli, TestClient in a temp
home), and Playwright's `expect` retries a locator assertion at 0, 100, 350 and 850 ms. The logged times sit just
above those steps (m ~200, Alt+↓ ~420), so a step finishing just after the 350 ms check is read as ~900 ms. Next
task.

#### Precise timings in the scale tests
Status: done
**Done when:** `npm run test:e2e` passes; `npx playwright test --project=scale --no-deps` passes 5 times in a row
(report every 5,000-bead line); `uv run pytest` unchanged.

`e2e/scale.spec.ts` only; no app change, the bounds stay (3,000 ms load, 500 ms per correction, 100 ms longest
task, 1,500 ms for `r` on 10,000).
- Every timed wait becomes a frame-precise in-page wait: `page.waitForFunction(fn, arg, { polling: 'raf', timeout:
  10_000 })` checking the same condition with `document.querySelector(All)` (the segment count of the next bead's
  source cell, the row count, `data-current`/`data-reviewed` on the row, the last row attached for the load), in
  place of the `expect(...)` after the key press or `goto`. The `timed` helper takes such a predicate. Untimed
  checks stay `expect`.
- Keep the log lines' format. Report the new numbers against the old (move ~420, merge ~200) in the `Report:`.
Report: 2026-10-04 — `scale.spec.ts`: `until` (`waitForFunction`, `polling: 'raf'`) for every timed wait, `timed(key, selector,
count)`; bounds unchanged. 5,000 beads, 5 runs alone, all passed: load 1330–1397, Alt+↓ 155–177 (was ~420), Ctrl+Z
238–290 (~330), m 149–174 (~200), Ctrl+Z 149–166 (~200), Alt+↓ again 169–188 (~315), Ctrl+Z again 148–176 (~400)
ms, 0 long tasks; 10,000: 20 ↓ ~300 ms, `r` ~250–310. e2e 62 passed; type-check clean; pytest 414 passed.

#### Search page
Status: todo
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes with the new `e2e/search.spec.ts`;
`uv run pytest` unchanged.

SPEC §3.4, from a global page and from inside a book.
- New `frontend/src/views/BookSearch.vue`, routed at `/search` in place of `SearchView.vue` (the file stays until
  Stage 7; the nav link in `App.vue` already points there). The URL holds the state: `?q=&side=&book=`; submitting
  (Enter or the button) does `router.replace` with them and runs the search; loading the URL runs it too. So the
  back button from a book returns to the results.
- Controls: the query input (focused on load), a side select "Either side" / "Source" / "Target", and with `book`
  a chip "In <title>" whose × drops the scope (searches all books).
- Results (design variant A tokens; texts in `font-text`): per result the book title and "bead N", a "Not
  reviewed" pill when `!reviewed`, the source and target side by side with match spans in `<mark>`; buttons
  "Context" (toggles the surrounding beads, `around=2`, the result's own bead tinted) and "Open" (→
  `/book/<book_id>?bead=<bead_id>`). "More results" when the last page had 50, appending the next `offset`. "No
  results" when empty.
- Book screen: a "Search" link in the top bar, before "Keys", to `/search?book=<id>`. A plain link: nothing the
  template reads on a move (render rule 1).
- `e2e/search.spec.ts`, two small books imported through the API: a word beginning finds beads in both books with
  the match marked; "Target" narrows; two words split across sides find nothing; the book chip scopes and its ×
  widens; "Context" shows the neighbours; "Open" lands on that bead (current), and Back returns to the same
  results; a bead marked reviewed through the API shows no pill; 60 matching beads in one book → 50, then "More
  results" → 60.

### Export
Decided (user, 2026-10-04): the translator uses no translation software and won't open spreadsheets; in-app
search is how they use the corpus. So corpus export (TMX/TSV) moved to SPEC §5 "Later" (agreed); edition export
is due with v0.2. The project bundle stays in SPEC §3.5.

#### Edition export
Status: todo
**Done when:** `uv run pytest` passes with the new tests; `npm run type-check` passes; `npm run test:e2e` passes
with the new test.

SPEC §3.5: "the (corrected) text of one side as .txt or .docx, keeping paragraph structure". Decided (Pauli,
2026-10-04): the export is the edition **as reviewed**: the current `text` of every segment (edits included,
never `original_text`) of the blocks that are **not excluded**, in document order; running heads, page numbers,
excluded footnotes and excluded matter are left out (an included block is exported whatever its kind).
- New `tradurre/services/edition.py`: `edition_blocks(conn, book_id, side) -> list[tuple[str, str]]` (block kind,
  the block's segment texts joined by one space; blocks without segments skipped); `edition_txt(blocks) -> bytes`:
  UTF-8 with a BOM (Notepad and Word on Windows read the encoding right), blocks separated by one blank line,
  `\n` line ends, a final newline; `edition_docx(blocks) -> bytes` with `python-docx`: a `heading` block →
  `add_heading(text, level=1)`, any other → `add_paragraph(text)`.
- API (`api/books.py`): `GET /books/{id}/export/edition?side=source|target&format=txt|docx` → the bytes, media
  type `text/plain; charset=utf-8` or the docx one, `Content-Disposition: attachment` with filename
  `<title> (<LANG>).<ext>` (the side's language code uppercased; `/ \ : * ? " < > |` in the title replaced by
  `_`; RFC 5987 `filename*` for non-ASCII). 404 for an unknown book; `side`/`format` as `Literal` (422 otherwise).
- Book screen, `MoreMenu.vue`: a fourth heading "Export" with four items, "Source text (.txt)", "Source text
  (.docx)", "Target text (.txt)", "Target text (.docx)" (`data-testid="export-source-txt"` etc.), plain `<a
  href download>` links to that URL; always enabled; clicking one closes the menu.
- Tests: `tests/test_edition.py` on a synthetic book (as `tests/test_domain_blocks.py` builds one): a heading, two
  paragraphs, an excluded running head and an excluded footnote, one segment edited → txt is BOM + heading +
  blank line + paragraph 1 (segments joined by a space, the edited text) + blank line + paragraph 2 + newline,
  nothing excluded; including the footnote (`include_block`) adds it in its place; docx read back with
  `python-docx`: the heading's style is "Heading 1", then the two paragraphs. `tests/test_books_api.py` (or a new
  `test_books_export_api.py`): content type, disposition filename, 404, 422. e2e (`book-layout.spec.ts`): More →
  "Target text (.txt)" → a download (`page.waitForEvent('download')`) named `<title> (IT).txt` whose content
  holds the target text.
- The v1 export (`api/export.py`) is untouched (Stage 7).

#### Project bundle
Not ready. SPEC §3.5: export/import of one project's text layer and alignment as a full backup. To decide when
planned: the format (versioned JSON, zipped), what it holds (blocks with kinds and exclusion, segments with
`text` and `original_text`, beads with confidence, method and reviewed; the operation history or not), and import
as a new book (never over an existing one).

---

## Stage 7 — Retire the old model

Remove the `pairs` table and its API, the old import wizard, `resplit`, the TipTap per-pair editor, the
old artifact format and `services/importer.py` (unused since "Repo hygiene"); update `CLAUDE.md`, `README.md` and the e2e tests. Release v0.2.0.

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
