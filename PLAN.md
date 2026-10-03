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
- One shared `sqlite3` connection across FastAPI's threadpool; no undo/history. `tests/test_aligner.py` now reads
  synthetic fixtures, but 9 of its tests hit a `RecursionError` in the live aligner (see Stage 0).
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
Status: todo
**Done when:** on a fresh clone, `uv run pytest` collects every test file and passes, with no file read
from `library/`.
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

### Database access
Status: todo
**Done when:** each request gets its own connection (or all access goes through one lock), multi-statement
operations run inside an explicit transaction that rolls back on error, and a test shows that a failing
operation leaves no partial change.

### Dependency hygiene
Status: todo
**Done when:** `pytest` and `httpx` are in a dev dependency group, not runtime dependencies; dead code
(`/import/preview` and its client call, the unreachable `return` in `import_artifact`) is removed; tests pass.

### Python 3.14
Status: todo
**Done when:** development and the Windows install use Python 3.14, and `uv run pytest` and
`uv run --python 3.12 pytest` both pass with the same counts.

Decision (user, 2026-10-03, now in SPEC §4): 3.14 and 3.12 are both supported; on conflict, 3.12 wins.
`requires-python` stays `>=3.12`, because the Colab step (Stage 4) installs the `align` extra on Colab's 3.12.
- Add `.python-version` containing `3.14` at the repo root.
- `packaging/start-tradurre.bat`: add `--python 3.14` to the `uv.exe tool install --force` line, so the
  translator's environment is deterministic instead of "whatever Python uv finds". Existing installs move to
  3.14 on the next upgrade, because `--force` rebuilds the tool environment (uv downloads its managed 3.14).
- `CLAUDE.md`: in "Commands", "Python 3.12" → "Python 3.14; the code must also run on 3.12 (Colab, SPEC §4)", and
  add `uv run --python 3.12 pytest` to the command list as the check to run before calling a task done whenever
  it adds or bumps a dependency or uses syntax/stdlib newer than 3.12.
- Don't touch `pyproject.toml` or `uv.lock`. All runtime dependencies already ship `cp314`/`abi3`
  `win_amd64` wheels in `uv.lock` (checked: pymupdf, pydantic-core, httptools, watchfiles, lxml, websockets,
  pyyaml), so nothing builds from source on Windows.
- If the 3.12 run fails for a reason that isn't a one-line fix, stop and report (SPEC: 3.12 wins, but how is a
  decision).
- Report that the `.bat` change can't be exercised here; the developer checks it by hand on the next release.

---

## Stage 1 — New data model

Separate text from alignment (SPEC §2). Built alongside the old `pairs` model, which stays working until
Stage 6 removes it.

### Schema
Tables for documents (one per edition), blocks (with kind and excluded flag), segments (text and original
text), beads (source/target segment ranges, confidence, method, reviewed), an operation log, and per-project
warnings/run metadata. Ordering that doesn't require renumbering the whole book on every insert.
Must include a schema-version mechanism (`PRAGMA user_version` plus an ordered list of migration functions run
by `init_db()`), because SPEC §4 requires automatic migration on upgrade once v0.2 ships; the ad hoc
`ALTER TABLE … try/except` pattern described in `CLAUDE.md` cannot express table rebuilds or data moves. (Needs
user agreement, since `CLAUDE.md` says not to add a migration framework; update `CLAUDE.md` with it.)
Open question for the user before breakdown: is "reviewed" a per-bead flag, or derived from the per-project
"reviewed up to here" position (SPEC §2 vs §3.3)? It decides what §3.2 "reviewed beads are kept" protects.

### Domain operations
A service layer, independent of HTTP, implementing every SPEC §3.3 correction (segment split/join/edit, block
exclude/include, bead boundary moves, merge/split, review mark) as transactional operations that record an
inverse in the operation log; undo/redo on top of it. Also one bulk primitive, "replace the beads covering a
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
a plain read-only bead list (no virtualization), so every task here leaves a working app. Warnings stored on the
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
