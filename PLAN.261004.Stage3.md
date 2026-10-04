# Tradurre — Plan, archived: Stage 3

Completed stage moved out of `PLAN.md` on 2026-10-04; kept as the record of its tasks, reports and
verifications. Stage numbers mentioned below refer to the plan at that date. Book text never appears here: the
reference book is copyrighted, and only counts and features were recorded.

## Stage 3 — Better import
Done (2026-10-04).

**Decided (user, 2026-10-03): tradurre is AGPL-3.0-only** (`LICENSE`, `pyproject.toml`), so PyMuPDF (AGPL-3.0)
stays the PDF library. The launcher already installs `tradurre[pdf]` (`EXTRAS=pdf`); "PDF import in the app" makes
`pymupdf` a core dependency (the `pdf` extra stays, redundant, for the launcher).

### Reference book
(Context for the whole stage, not a task.) `library/contrefeu.fr.pdf` (Emmanuel Venet, *Contrefeu*) and `library/contrefeu.it.pdf` (*Sacro fuoco*), both
born-digital, ~38,000 words per side. Local only (see "Current state"). How the tasks of this stage use it:
- **Opt-in tests.** `tests/test_library.py`, every test marked `library` and skipped when the files are missing,
  so a fresh clone stays green. They assert structural facts (logical page count, first and last sentence of
  the body, no page-number text in included blocks, reading order across page boundaries), never long excerpts.
- **Failures become committed fixtures.** A problem found on the real book gets a short synthetic reproduction in
  `tests/fixtures/` before it is fixed (same rule as Stage 0 "Test fixtures", archived).
- **Gold chapter.** One chapter whose alignment the translator has checked by hand; see the step "Gold
  chapter" below. It is how the baseline aligner (here) and the Colab aligner (Stage 5) are compared, by numbers
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

### PDF extraction
Continues "Structured extraction" (Stage 2) with the same design.

#### PDF lines and logical pages
Status: done
**Done when:** `tests/test_extract_pdf.py` passes; `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — `pymupdf` in the `dev` group (`uv.lock`), `_Line`, `_pdf_lines` with the two-up rule in `extract.py` (`extract` still refuses `.pdf`); `tests/test_extract_pdf.py` 4 tests (the two-up case needs ≥ 60% two-up spreads, so its document has 3 spreads, one with text only on the right); local check on the reference book: FR 128 logical pages, IT 184 (91 spreads × 2 + 2 portrait covers), left page before right across a spread; pytest 253 passed (249 + 4).
Verified (/pauli, 2026-10-03, `1e3a45b`): pytest 253; the rule and tests match the task, and the test-document
fix is correct (the task's own 60% rule required it). Measured on the reference book with `_pdf_lines` to check
the next task's thresholds, which led to corrections there (see its "Measured" note).

In `extract.py`, the first half of PDF extraction (no blocks yet):
- Add `pymupdf` to the `dev` dependency group (`uv add --dev pymupdf`; `uv.lock` updated) so PDF tests run in
  `uv run pytest`. The `pdf` extra stays as it is (see the open question under this stage).
- `@dataclass _Line(page: int, x0: float, y0: float, x1: float, y1: float, text: str, size: float)`: `page` is
  the 0-based logical page, `size` the largest span size in the line, `text` the spans joined (lines whose text is
  only whitespace are dropped).
- `_pdf_lines(doc) -> tuple[list[_Line], list[tuple[float, float]]]`: the lines of every logical page in reading
  order, and each logical page's `(width, height)`.
  - **Two-up spreads**, decided once per document: a landscape page (`width > height`) "looks two-up" if at least
    20% of its lines have their centre left of `width / 2` and at least 20% right of it. If at least 60% of the
    document's landscape pages that have text look two-up, every landscape page is split: lines with centre left
    of `width / 2` go to logical page `2k`, the others to `2k + 1` with `x` shifted by `-width / 2`, and both
    logical pages are `(width / 2, height)`. (A blank or one-column page in a two-up book still yields two logical
    pages, so page counts stay right.) Otherwise one logical page per PDF page.
  - Within a logical page, lines sorted by `(y0, x0)`.
- `tests/test_extract_pdf.py` (PDFs built in the test): a portrait page's lines in top-to-bottom order; a
  two-page landscape document with text in both columns → 4 logical pages, left column's lines before the right
  column's, right-hand `x` shifted; in that document, a page with text only on the right still gives 2 logical
  pages, its lines on the second; a landscape document with one centred column → one logical page per PDF page;
  page sizes returned correctly.

#### PDF blocks
Status: done
**Done when:** `tests/test_extract_pdf.py` passes with the cases below; `uv run pytest -m library` passes on this
machine (the reference book is present); `uv run pytest` otherwise unchanged.
Report: 2026-10-03 — rule (a) applied (non-paragraph blocks end at a page boundary) on top of the blocked tree: `_extract_pdf`, `extract` reads `.pdf`, API refuses `.pdf` by extension, obsolete test removed; `tests/test_extract_pdf.py` 13 pass (2 new for rule (a)); `tests/test_library.py` passes: FR 208 paragraph / 120 page_number / 27 heading / 3 footnote, IT 197 / 157 / 27 / 2, chapter numbers 25 = 25, no stray numbers, 0 warnings; `uv run pytest` 266 passed (253 − 1 obsolete + 9 PDF + 5 library runs); e2e `books.spec.ts` 4 passed.
Verified (/pauli, 2026-10-03, `520747c`): pytest 266, library tests pass. Checked on the reference book (counts
only): extraction takes 1.75 s (FR) / 1.89 s (IT); hard line-end hyphens kept by the join rule never produce a
word whose unhyphenated form also occurs in the book (0 of 505 FR, 0 of 221 IT hyphenated tokens), so keeping
them is right for this book.
Report: 2026-10-03 — blocked on one library test: number-only headings FR 25, IT 24. The missing IT one (size 11.3, top of logical page 7) merges into the preceding heading block (a 9-word front-matter heading on page 5; page 6 is blank), because "consecutive lines of the same kind form one block" has no page condition. Needs a rule: e.g. non-paragraph blocks don't continue across a page boundary, or a chapter-number line is always its own block. Everything else is done, uncommitted: `_extract_pdf` (classification, assembly, joining, glyphs), `extract` reads `.pdf`; the API still refuses `.pdf` with 415 (now by extension, since `extract` no longer raises) and the obsolete `test_pdf_not_implemented_yet` is removed; `tests/test_extract_pdf.py` 11 pass; `tests/test_library.py` 3 tests (marker registered), 2 pass: page numbers FR 120, IT 157; stray included numbers 0 both sides; blocks FR 208 paragraph / 120 page_number / 27 heading / 3 footnote, IT 197 / 157 / 26 / 2; `uv run pytest` here: 263 passed, 1 failed (that library test; on a fresh clone the library tests skip).
Answered (/pauli, 2026-10-03, user agreeing): resume from the uncommitted tree. **Rule (a): a block of any kind
other than `paragraph` never continues onto another logical page** (in `_extract_pdf`'s assembly, a line starts a
new block when the previous block's last line is on a different page). Only paragraphs legitimately run over a
page break, and they already have their own rule. This also fixes a second merge the same line of code allows: a
footnote at the bottom of page n and one at the bottom of page n+1, with the paragraph continuing between them,
currently join (the continuing paragraph doesn't end the footnote block). Not adopted: "a chapter number is always
its own block" alone (fixes only this case; a half title and a dedication on consecutive pages would still merge);
within one page, "IV" followed by a title line still forms one heading block, which aligns fine since the other
side merges the same way. Add tests: two heading lines on consecutive pages (with a blank page between) → two
heading blocks; footnotes at the bottom of two consecutive pages, with a paragraph running across the break → two
footnote blocks and one paragraph. Braun's deviations are accepted: the API refuses `.pdf` by extension until "PDF
import in the app"; test PDFs embed the font to keep U+00AD.

`extract` for `.pdf`, from `_pdf_lines`:
- `body_size` = the line size covering the most characters in the document (`_Line.size` rounded to 0.1 pt,
  weighted by `len(text)`; lines carry only their largest span's size, which is good enough). Per logical page,
  `left` = the most common `round(x0)` among lines whose `size` is within 0.5 pt of `body_size`.
- **Measured** (/pauli, 2026-10-03, reference book through `_pdf_lines`; numbers only, no text): FR page numbers
  sit at `y0/h` 0.871 (size 10, body 11.9), so a 12% band by `y0` would catch **none** of them; IT page numbers
  at 0.933 (size 8.2, body 12.5). Number-only lines that are **chapter numbers**: FR 25, size 14, anywhere from
  0.13 to 0.72 of the page; IT 25, size 11 (smaller than the body!), at the top (0.08) of the chapter's first
  page. So position and size alone can't tell IT chapter numbers from page numbers; frequency can (page numbers
  sit in the same slot on 120/128 and 157/184 logical pages, chapter numbers on ~13%). No running heads in this
  book. First-line indent ≈ 14 pt on both sides; body line pitch 14.0 (FR) and ≈ 16.1 (IT).
- "In the top/bottom band" below means: the line's vertical centre `(y0 + y1) / 2` is within 15% of the logical
  page height from its top or bottom edge.
- Classification, per line, in this order:
  - `page_number`: text matches `^\s*([0-9]+|[ivxlcdm]+)\s*$` (case-insensitive), `size <= body_size + 0.5`, in
    the top or bottom band, **and** its slot is frequent: candidates are grouped by (band, `round(size)`), and only
    a group with lines on at least 25% of the document's logical pages counts;
  - `running_head`: in the top band, and its text with digits removed, casefolded and stripped is non-empty and
    occurs (so normalized) in the top band of at least 3 logical pages;
  - `heading`: `size >= body_size * 1.1`, or a line that is only a chapter number, `^\s*([0-9]+|[IVXLC]+)\s*$`
    **case-sensitive** (lower-case Roman numerals would catch Italian words like "di", "mi", "vi" wrapped alone
    onto a line; lower-case Roman page numbers are still caught by `page_number`);
  - `footnote`: `size <= body_size * 0.9` and in the bottom 40% of the page;
  - otherwise body.
- Assembly: consecutive lines of the same kind form one block (non-paragraph blocks never across a logical page
  boundary; see "Answered" above), except that body (`paragraph`) lines also start a
  new block when `x0 >= left + 0.5 * body_size` (first-line indent) or the vertical gap to the previous body line
  exceeds 1.5 × the median body line pitch of the document; `page_number` and `running_head` lines are one block
  each. A paragraph continues across a page boundary unless the next page's first body line is indented (the
  excluded lines in between don't break it). `page` = logical page of the block's first line, plus 1.
- Joining lines inside a block: a line ending in U+00AD (soft hyphen) is joined to the next with the soft hyphen
  removed and no space; a line ending in a letter followed by `-` is joined keeping the `-` and no space; any
  other pair with one space. Soft hyphens elsewhere are removed. Then `normalize_ocr_artifacts`.
- Glyphs: `glyph_resolver.resolve_pua_glyphs(doc)` (no LLM) and `apply_resolution(text, mapping)` on every
  block's text; its warnings go to `Extraction.warnings`.
- Tests (PDFs built in the test, one font, sizes like the reference book): indented paragraphs become separate
  blocks; a paragraph running over a page break stays one block, with the page number between excluded as its own
  `page_number` block; a page number at 87% of the page height (FR-like) is a `page_number`; in a 10-page document
  with page numbers at the bottom of every page, a small number-only line at the top of 2 pages (IT-like chapter
  number) is a `heading`, not a `page_number`; a soft hyphen and a hard hyphen at line ends; a repeated top line
  on 3 pages → `running_head`, on 2 → not; a larger line → `heading`; small text at the bottom → `footnote`; a
  two-up document reads left page then right page.
- `tests/test_library.py` (new; every test marked `library` and skipped when `library/contrefeu.*.pdf` is missing;
  register the marker in `pyproject.toml` `[tool.pytest.ini_options]`): for each side, at least 110 (FR) / 150
  (IT) `page_number` blocks; no included block whose text is number-only except `heading`s; the number of
  number-only `heading` blocks is the same on both sides (25 each when measured). Counts only, never text in
  assertions or messages (the book is copyrighted). Report the actual numbers.

#### Front and back matter
Status: done
**Done when:** `uv run pytest` passes with the new `tests/test_matter.py`; `uv run pytest -m library` passes on
this machine with the new library test; `npm run test:e2e` passes; `uv run python scripts/gold_score.py` prints
exclusion precision **1.000** and recall **≥ 0.90**, and alignment F1 **≥ 0.994**. The `Report:` gives the full
score output except the missed-run texts. (Pauli's probe of exactly this rule, 2026-10-04: exclusion P 1.000 R 0.902
F1 0.948, was 0.592; alignment P 0.992 R 0.998 F1 0.995; 1232 predicted beads, shapes 1:1 1212, 1:2 16, 2:1 2, 0:1 2.)
Report: 2026-10-04 — `services/matter.py` (`MARKERS`, `mark_matter`), applied by `extract` to every format; `tests/test_matter.py` 11 tests, library test FR 22/6, IT 7/8 front/back blocks; pytest 391 passed, `-m library` 10 passed, e2e 29 passed. gold_score: extraction 3.6 s, build 1.5 s; beads 1222 gold, 1232 predicted; shapes 1:1 1212, 1:2 16, 2:1 2, 0:1 2; alignment P 0.992 R 0.998 F1 0.995 (boundaries 1221 gold, 1229 predicted); exclusion P 1.000 R 0.902 F1 0.948; excluded chars source 1134 gold / 1127 predicted, target 1979 / 1681. Import stats: 9 low-confidence beads (was 25), 2 one-sided (was 12).

Decided (user, 2026-10-04): **exclude first, then align**, with a conservative rule tuned to the data we have, no
learned classifier. Reason (counts only): alignment is weak evidence. Of the 29 source segments the gold excludes
but the import includes, the length aligner leaves only 6 one-sided; 15 sit in 2:1 beads and 8 are paired 1:1 with
the other edition's front matter. Bias: leave junk in rather than hide text. A stray title page is obvious at the
top of the review. A wrongly excluded epigraph, dedication or last paragraph is hidden. Precision matters more than
recall. `x`/Include and range include (Stage 4) still override it, and nothing is deleted.

Measured (Pauli, 2026-10-04, reference book against the gold; features and counts only):
- The gold excludes exactly two runs per edition: everything before chapter 1 except one title heading, and a tail
  after the last body paragraph. Nothing in between.
- Front matter: FR blocks 0–26 on logical pages 3–6, IT blocks 0–7 on pages 3–4 (IT's p.5 title heading is kept
  by the gold). Paragraphs there are 1–17 words, one of 56 words with a publishing marker; the first chapter
  number is on p.7 on both sides.
- Back matter: FR 6 short paragraphs on p.128, IT one note-like run on p.181 (a 1-word heading, 4 and 55 words)
  and 8 short paragraphs plus a footnote on p.184. **Both books' last body paragraph is short (34 and 32 words),
  and FR's sits on the page right before the colophon (p.127, which has no page number)**, so "short blocks at the
  end" or "pages without page numbers" would hide the novel's last paragraph. A publishing marker is what tells
  them apart.
- Markers found, front/back/body counts: only publishing terms occur in the front/back runs (©, ISBN, Copyright,
  Dépôt légal, Imprimé, Du même auteur, www., Éditions, Editore, Titolo originale, Traduzione di/dal, Finito di
  stampare); none of them occurs in the body. Generic words do: "roman" (9/11 in the body), "Paris", "Table".

The rule, in a new module `tradurre/services/matter.py`:
- `MARKERS`: case-sensitive substrings `"ISBN"`, `"©"`, `"Copyright"`, `"Dépôt légal"`, `"Achevé d"`, `"Imprimé"`,
  `"Du même auteur"`, `"Dello stesso autore"`, `"Titre original"`, `"Titolo originale"`, `"Traduit de"`,
  `"Traduzione di"`, `"Traduzione dal"`, `"Finito di stampare"`, `"Tous droits"`, `"Tutti i diritti"`, `"www."`,
  `"Éditions"`, `"Edizioni"`, `"Editore"`. A block is **marked** if its text contains one (any kind, excluded
  kinds included).
- A **long paragraph** is a `paragraph` block of at least 60 whitespace-separated words (`_LONG = 60`). A **chapter
  number** is a `heading` whose text matches `extract._CHAPTER_NUMBER` (import it; don't copy the regex).
- `mark_matter(blocks: list[ExtractedBlock]) -> list[ExtractedBlock]`: a new list (`dataclasses.replace`, the input
  is not mutated) in which some `paragraph` blocks become `front_matter` or `back_matter`. **Only `paragraph`
  blocks change kind.** Headings stay as they are: the book's title stays visible and aligns title to title.
  - Front: `B` = index of the first block that is a chapter number or a long paragraph; none → no front rule. `M` =
    the last index before `B` of a marked block; none → no front rule. Region: indices `0..M`, plus, when
    `blocks[M].page` is not `None`, the blocks between `M` and `B` on the same page as `M`. Its paragraphs become
    `front_matter`.
  - Back: `E` = index of the last long paragraph; none → no back rule. `F` = the first index after `E` of a marked
    block; none → no back rule. Region: indices `F..end`, plus, when `blocks[F].page` is not `None`, the blocks
    between `E` and `F` on the same page as `F`. Its paragraphs become `back_matter`.
  - No marker, no exclusion: a book whose front matter carries none is left as it is (the translator range-excludes
    it).
- `tradurre/services/extract.py`: `extract` applies `mark_matter` to the result of every format (txt, docx and
  pdf: block order alone works without pages), keeping the warnings. `EXCLUDED_KINDS` already holds both kinds,
  so the build excludes them and the import stats count them with no other change.
- Accepted misses (both measured): FR's 1-word heading on p.5 (headings are never re-kinded) and IT's p.181 run
  (a page without a marker; it may be a note, which is text; the translator range-excludes it if not).
- `tests/test_matter.py` (synthetic `ExtractedBlock`s, no book text):
  - a front run of short paragraphs with a marker on its last page, then a chapter number → those paragraphs are
    `front_matter`, a heading among them stays `heading`;
  - the same without any marker → nothing changes;
  - a short paragraph after `M` on `M`'s page is front matter; one on a later page before `B` is not;
  - a long paragraph as the first body block when there is no chapter number → `B` is that paragraph;
  - a short last body paragraph on the page before a marked colophon page stays `paragraph`, while the colophon
    page's paragraphs (including an unmarked one before the marker) become `back_matter`;
  - a marker inside the body (between the first and last long paragraph) changes nothing;
  - `page=None` blocks (docx-like): regions by index only;
  - an empty list and an all-short list without markers → unchanged;
  - `extract` on a small docx built in the test with a marked first paragraph followed by a long one → first
    block `front_matter`.
- `tests/test_library.py`: per side, the counts of `front_matter`/`back_matter` blocks after `extract` (probe: FR
  22/6, IT 7/8); assert each is at least 1, report the actual numbers. Counts only.
- Don't change the aligner, the segmenter, the API, the frontend, or the existing extraction tests (none of their
  fixtures carries a marker; if one fails, stop and report).
- Then re-run `gold_score.py` (no re-export of the gold needed).

Decided (user, 2026-10-03): sources are mixed and unknown per book (PDF, sometimes the translator's own .docx for
the Italian side), so both paths stay first-class: the PDF pipeline is not the only road, and docx import keeps
its tests.

### PDF import in the app
Status: done
Report: 2026-10-03 — pymupdf core dependency (`pdf` extra kept, commented); unreadable PDF → 400; extraction via `run_in_threadpool`; form accepts .pdf; API test on a built PDF pair, library import test (reference pair: 201, 4.3 s wall, 1354 beads, 185 one-sided); pytest 268 passed, `-m library` 6 passed, type-check clean, e2e 28 passed (the form test's button label updated too).
**Done when:** `uv run pytest` passes (including the new tests); `uv run pytest -m library` passes on this machine
with the new import test; `npm run type-check` passes; `npm run test:e2e` passes.

The reference book becomes importable in the app (SPEC §3.1.1: born-digital PDF, .docx or .txt).
- `pyproject.toml`: `pymupdf>=1.24` moves into `[project].dependencies` and out of the `dev` group (`uv.lock`
  updated). The `pdf` extra **stays** with its current content: the Windows launcher installs `tradurre[pdf]`
  (`packaging/start-tradurre.bat:14`), and dropping the extra would break that line; it is now redundant, say so in
  a comment above it. Do not change the launcher.
- `tradurre/services/extract.py`: `_extract_pdf` turns a file PyMuPDF can't open into `ValueError("The file is
  not a readable PDF")` (catch the exception `pymupdf.open` raises; don't catch broadly around the rest).
- `tradurre/api/books.py`: remove the `.pdf` refusal in `_extract` (the 415 goes away); `ValueError` already maps
  to 400. Extraction is CPU work of seconds per PDF inside an `async def` handler, which would freeze every other
  request meanwhile: call `extract` through `starlette.concurrency.run_in_threadpool`. Nothing else in the import
  changes.
- Frontend: `BookImport.vue` file inputs `accept=".txt,.docx,.pdf"`; `ProjectList.vue` button "Import a book
  (txt/docx/pdf)".
- Tests:
  - `tests/test_books_api.py`: `test_pdf_is_refused_and_writes_nothing` becomes: an unreadable `.pdf`
    (`b"%PDF-1.4"`) → 400 "The file is not a readable PDF", nothing written; plus a new test importing a small
    PDF pair built in the test (reuse the embedded-font helper pattern of `tests/test_extract_pdf.py`; a few
    paragraphs and page numbers per side) → 201, beads present, page-number blocks excluded (`GET` shows them in
    `excluded`).
  - `tests/test_library.py`: importing the reference pair through `POST /api/v2/books` (TestClient on a temporary
    database, as in the API tests) returns 201; record in the `Report:` the wall time of the request, the bead
    count, and how many beads are one-sided. Assert only 201 and bead count > 1000 (counts, no text).
  - `frontend/e2e/books.spec.ts`: the PDF case now expects "The file is not a readable PDF".
- After this task, tell the user in the report how to try it: `uv run tradurre --dev` plus `npm run dev`, import
  `library/contrefeu.fr.pdf` / `contrefeu.it.pdf`.

### Whole-book gold
Status: dropped
Report: 2026-10-04 — blocked. `gold_export.py <id> all` done and tested (pytest 368 passed); export of the user's book OK (1222 beads, 0 one-sided, `library/contrefeu.gold.tsv`, gitignored). `gold_score.py` refuses: "doesn't match the current extraction", divergence at character 0 on both sides. Cause: the user excluded blocks the import includes (source: 28 paragraphs + 1 heading; target: 17 paragraphs + 1 heading; no text edits), so the gold's text is not a contiguous substring of a fresh import's (gold 196,294 / 201,813 non-space chars vs predicted 196,871 / 203,039). The metric's "gold is a substring" assumption fails whenever the translator's exclusions differ from the import's; needs a design decision.
Dropped 2026-10-04 (Pauli, with the user): superseded by "Gold v2"; its uncommitted `all` changes to
`gold_export.py`/`tests/test_gold.py` are replaced there.

### Gold v2
Status: done
Report: 2026-10-04 — `gold.py` rewritten (`Layer`, `read_layer`, JSON format 1, `score` with alignment and exclusion metrics per character); `gold_export.py <id>` writes `library/contrefeu.gold.json`; `gold_score.py` prints both scores; `tests/test_gold.py` rewritten (13 tests; v1's 22 removed); pytest 359 passed. User's book: 1222 beads, 0 one-sided, excluded segments source 152 / target 181. Score of the current pipeline: import 4.5 s, 1353 predicted beads; alignment P 0.840 R 0.903 F1 0.870 (boundaries 1221 gold / 1312 predicted); exclusion P 1.000 R 0.421 F1 0.592 (excluded chars source 1134 gold / 557 predicted, target 1979 / 753); longest missed runs: beads 1099–1164 (66), 740–751, 243–249, 45–49, 1059–1063.
**Done when:** `uv run pytest` passes with the rewritten `tests/test_gold.py`; `uv run python scripts/gold_export.py
046fb6f2-ba5d-4b6b-ac1a-d6a9caf9f38c` writes `library/contrefeu.gold.json` from the user's database; `uv run python
scripts/gold_score.py` runs on it, and the `Report:` gives its full output except the missed-run texts (metrics,
counts, timing only).

Design v2 under "Gold chapter" is binding. Start from the working tree (it holds the dropped task's uncommitted
`all` changes; replace them).
- `tradurre/services/gold.py`, rewritten:
  - `Layer` (dataclass): `source: list[tuple[str, int | None]]`, `target: …` (segment `original_text`, bead index
    or `None`), `reviewed: list[bool]` (per bead). `read_layer(conn, book_id) -> Layer` (ValueError "book … not
    found" as now). `layer_to_json(layer) -> dict` / `layer_from_json(dict) -> Layer`, JSON shape
    `{"format": 1, "source": [[text, bead], …], "target": […], "reviewed": […]}`.
  - `score(gold: Layer, predicted: Layer) -> Score`; `Score` dataclass: `alignment_precision`, `alignment_recall`,
    `alignment_f1`, `gold_boundaries`, `predicted_boundaries`, `exclusion_precision`, `exclusion_recall`,
    `exclusion_f1`, `excluded_chars: dict[str, tuple[int, int]]` (side → (gold, predicted)), and `missed:
    list[tuple[int, int]]` (runs of gold bead indices whose boundary is not predicted, longest first, as now).
  - Remove `chapter_beads`, `book_beads`, `boundaries`, `read_tsv`, `write_tsv` and the chapter regex.
- `scripts/gold_export.py <book id> [--db] [--out]` (default `library/contrefeu.gold.json`): no chapter argument;
  refuses while any bead is unreviewed (as now, "N of M beads of the book are not reviewed"); prints bead count,
  one-sided beads, excluded segments per side.
- `scripts/gold_score.py [--gold] [--source] [--target]` (default gold `library/contrefeu.gold.json`): builds as
  now, reads the prediction with `read_layer`, prints import time and bead counts (gold, predicted), the alignment
  P/R/F1 and boundary counts, the exclusion P/R/F1 and excluded characters per side (gold vs predicted), and the 5
  longest missed runs with the first source segment of the run's first gold bead, cut to 80 characters.
- `tests/test_gold.py`, rewritten (synthetic only; hand-built `Layer`s plus the docx fixture through the API):
  identical layers → all six metrics 1; merged beads → alignment recall < 1, precision 1, `missed` names it; gold
  excludes a block that the prediction keeps as a one-sided bead → exclusion recall < 1, alignment F1 1; prediction
  excludes a block the gold keeps → exclusion precision < 1; different segmentation or whitespace of the same text
  → 1; different text → ValueError naming the side; the empty-set conventions; `read_layer` on the docx book after
  excluding one block via `POST …/blocks/{id}/exclude` gives `None` for its segments; JSON round trip; the export
  script refuses an unreviewed book and writes the file once all are reviewed; the score script on the docx pair
  with a gold that has one block excluded → "alignment F1 1.000" and exclusion recall 0.
- Don't touch `build_book`, the extractor, the segmenter, the aligner, the API or the frontend.

### Stale frontend warning
Status: done
Report: 2026-10-04 — `__main__.py`: `_stale_build` + startup warning in both modes; 4 tests appended to the existing `tests/test_main.py` (the task said new; it already held the `--version` test); pytest 363 passed. The build was already current (rebuilt by the user 2026-10-03 23:43): no warning. After touching `BookView.vue` (no content change): "warning: the built frontend in …/tradurre/static is older than frontend/src; run 'npm run build' in frontend/ (or use the Vite dev server on http://localhost:5173 with --dev)."; after `npm run build`: no warning.
**Done when:** `uv run pytest` passes with the new test; the `Report:` shows the startup line printed by `uv run
tradurre --no-browser` on this machine before and after `npm run build`.

Found 2026-10-03: the user opened the app on :8000 and got the **v0.1 screens** (old import wizard, sections,
"insert"/"remove"), because `tradurre/static/` was built before Stage 2 and the backend serves it in every mode,
`--dev` included (`app.py:46-58`); the new screens existed only on Vite's :5173. Nothing warned.
- `tradurre/__main__.py`: a function `_stale_build(frontend_src: Path, static: Path) -> bool`, true when
  `frontend_src` exists (a source checkout; an installed wheel has none) and its newest file under `src/`,
  `index.html`, `package.json` is newer than `static/index.html`. At startup, in **both** modes, if true print
  `warning: the built frontend in {static} is older than frontend/src; run 'npm run build' in frontend/ (or use
  the Vite dev server on http://localhost:5173 with --dev).` Keep the existing "no built frontend" warning.
- `tests/test_main.py` (new): `_stale_build` on a `tmp_path` tree: newer source → true; older source → false; no
  `frontend/` → false; no `static/index.html` → false (the other warning covers it).
- Nothing else changes.

### Gold chapter
Decided (user, 2026-10-03): made **in the app**, not in a spreadsheet. The translator imports the reference book,
corrects one chapter in the correction screen (moving sentences, splitting/joining segments; text edits only for
extraction damage) and marks its beads reviewed. Default chapter: the first of the body (chapter number "1"),
~200–400 sentences, with some 1:2/2:1 and unmatched material. This is the **user's** work, between "Gold export"
(the tool to save it) and the first scored aligner task; Braun's tasks below don't wait for it (they test on
synthetic books).

Design v1 (Pauli, 2026-10-03; tasks "Gold export" and "Gold score" below, done): one chapter as a TSV of beads,
located as a substring of a fresh import. **Broken by real use** (2026-10-04, see "Whole-book gold"): the user
corrected the whole book and excluded front/back matter by hand, so the gold's included text is no longer a
contiguous piece of a fresh import's. Replaced by design v2, binding for "Gold v2":
- **Whole book, whole text layer.** The gold is the user's corrected book: every segment of both editions in
  document order (block `ord`, segment `ord`), its `original_text` (text edits don't matter), and the 0-based index
  of its bead in bead order, or `null` if its block is excluded. The prediction has the same shape, read from a
  fresh import in a temporary database. Chapters and the TSV go away.
- **Same extraction or refuse.** Per side, the concatenation of all segments' text with whitespace removed must be
  identical in gold and prediction; otherwise refuse: "the gold doesn't match the current extraction ({side})".
  Known cost: an extractor change that alters text invalidates the gold. When that first happens, map offsets with
  a diff instead of refusing (a task then, not now).
- **Two scores, per character** (non-whitespace characters of each side, now in one-to-one correspondence):
  - *Exclusion*: positives are excluded characters. Precision = excluded in both / excluded in prediction, recall
    = excluded in both / excluded in gold, both sides pooled.
  - *Alignment*, on the characters included in **both** gold and prediction ("common"): a bead's boundary is
    (number of common source characters in it and all beads before, same for target). Gold and predicted
    boundary sets, minus (0, 0) and the end (all common source, all common target). Precision, recall, F1. A bead
    made only of characters the other side excluded collapses onto its neighbour's boundary, so an exclusion
    error is charged to the exclusion score, not twice.
  - Empty-set convention for both: precision = 1 if the predicted set and the gold set are both empty, 0 if only
    the predicted one is; same for recall with the roles swapped; F1 = 0 when precision + recall = 0.
- Gold beads must all be reviewed (export refuses otherwise). The file is `library/contrefeu.gold.json`
  (gitignored, copyrighted: never committed).

#### Gold export
Status: done
Report: 2026-10-03 — `tradurre/services/gold.py` (`chapter_beads`, `write_tsv`, `read_tsv`), `scripts/gold_export.py` (refuses unreviewed chapters, missing database); `tests/test_gold.py` 6 tests on a docx book; pytest 274 passed, `--help` prints usage.
**Done when:** `uv run pytest` passes with the new `tests/test_gold.py` export tests; `uv run python
scripts/gold_export.py --help` prints usage.

- New module `tradurre/services/gold.py` (no FastAPI imports):
  - `chapter_beads(conn, book_id, chapter: int) -> list[tuple[str, str, bool]]`: the chapter's beads as
    (source cell, target cell, reviewed), per the design above. Raises `ValueError` with a clear message for an
    unknown book or a chapter number that doesn't exist ("chapter 7 not found; the book has 5").
  - `write_tsv(path, cells: list[tuple[str, str]])` and `read_tsv(path) -> list[tuple[str, str]]` (exact round
    trip, including empty cells).
- `scripts/gold_export.py <book id> <chapter> [--db PATH] [--out PATH]` (argparse; `--db` defaults to
  `tradurre.config.DB_PATH`, `--out` to `library/contrefeu.gold.tsv`; the book id is the one in the book's URL).
  Refuses (exit 1, nothing written) if any bead of the chapter is unreviewed, naming how many; otherwise writes
  the file and prints the bead count and how many beads are one-sided.
- `tests/test_gold.py`: build a small book through `POST /api/v2/books` on a temporary database (fixtures as in
  `tests/test_books_api.py`) from .docx files (txt never yields `heading` blocks) with "Heading 1" paragraphs
  "1" and "2", as `_docx` in `test_books_api.py` builds them. Cover: chapter 1 and the last chapter boundaries; a text edit doesn't
  change the cell (original text); a split segment gives the same cell as before; unknown chapter → `ValueError`;
  TSV round trip with an empty cell; the script's refusal on an unreviewed bead (call its `main(argv)`).
- Don't touch the app, the API or the schema.

#### Gold score
Status: done
Report: 2026-10-03 — `gold.py`: `book_beads` (`chapter_beads` now slices it), `boundaries`, `score`/`Score`; `scripts/gold_score.py` builds the pair as the import does in a temporary database; 12 new tests in `tests/test_gold.py`; pytest 286 passed, `--help` prints usage. Not run on a real gold: `library/contrefeu.gold.tsv` doesn't exist yet. Sanity check on the reference PDFs with a 30-bead slice of the book itself as gold (scratchpad, deleted): F1 1.000, import 4.4 s, 1354 beads.
**Done when:** `uv run pytest` passes with the new score tests in `tests/test_gold.py`; `uv run python
scripts/gold_score.py --help` prints usage; the `Report:` says whether the score could run on this machine (only
once `library/contrefeu.gold.tsv` exists; if it doesn't yet, say so, it's not a failure).

- `tradurre/services/gold.py`:
  - `book_beads(conn, book_id) -> list[tuple[str, str, bool]]`: all beads' (source cell, target cell, reviewed);
    `chapter_beads` is rewritten to slice its result (same behaviour; the export tests stay unchanged and green).
  - `boundaries(cells: list[tuple[str, str]]) -> tuple[str, str, list[tuple[int, int]]]`: the two side texts and
    the boundary of every bead, in order, per the metric in the design above.
  - `score(gold, predicted) -> Score` (both `list[tuple[str, str]]`); `Score` is a dataclass: `precision`,
    `recall`, `f1`, `gold_count`, `predicted_count` (the set sizes) and `missed: list[tuple[int, int]]`, the runs
    of consecutive gold bead indices (first, last; 0-based) whose boundary isn't predicted, longest first. Raises
    `ValueError` with the "doesn't match" message.
- `scripts/gold_score.py [--gold PATH] [--source PATH] [--target PATH]` (argparse; defaults
  `library/contrefeu.gold.tsv`, `library/contrefeu.fr.pdf`, `library/contrefeu.it.pdf`; a missing file → exit 1
  with its name). It builds the book exactly as the import does, without the server: `extract` both files, a
  temporary database file (`tempfile.TemporaryDirectory`), `get_connection` + `init_db`, then inside
  `transaction(conn)` insert the `projects` row and call `build_book` (as `api/books.py:69-76`). It prints the
  wall time of extraction + build, precision/recall/F1 (3 decimals), the two counts, and the 5 longest missed
  runs as `beads i–j` with the first gold line of the run cut to 80 characters (terminal only, never a file).
  `main(argv) -> int` like `gold_export.py`.
- Tests (synthetic, no library; build cells by hand, no database needed except for `book_beads`):
  identical lists → 1/1/1; two gold beads merged in the prediction → recall < 1, precision 1, and `missed` names
  that bead; the gold located inside a longer prediction (beads before and after) → 1/1/1; the same alignment
  with a cell's text cut at a different place inside one bead, or different whitespace → 1/1/1; a one-sided gold
  bead (empty target) predicted right → 1/1/1; a gold not in the prediction → `ValueError`; `book_beads` on the
  docx fixture returns all 7 beads and `chapter_beads` still passes its tests. One script test: `main` with
  `--source`/`--target` pointing to the existing small docx files (written to `tmp_path`) and a gold TSV written
  from their chapter → exit 0 and "F1 1.000" in the output.
- This is the measuring stick for "Segmentation" and "Baseline local aligner": from then on their `Report:` lines
  quote `gold_score.py`'s F1. Don't touch the app, the API, the schema, or the export script.

### Segmentation
Status: done
Report: 2026-10-03 — `services/segment.py` (one regex with closers/openers and an exact `isupper` class, case-sensitive abbreviations, token = letters and inner dots so `l'Avv.` holds), used by `build_book`; `tests/test_segment.py` 38 cases + invariant; library invariant test. Reference book, old → new: FR 1258 → 1260 segments, >400 chars 47 → 45, lowercase starts 1 → 1, abbreviation ends 4 → 0; IT 1265 → 1266, 46 → 45, 10 → 10, 4 → 0 (the long ones have no internal terminator: real long sentences). Import: 1353 beads (was 1354), 180 one-sided (was 185). No gold yet. pytest 364 passed, `-m library` 8 passed, e2e 28 passed.
**Done when:** `uv run pytest` passes with the new `tests/test_segment.py`; `uv run pytest -m library` passes
with the new library test; the `Report:` gives, per side of the reference book, the segment count and the
diagnostic counts below **before and after** the change, the bead and one-sided bead counts from
`test_import_through_the_api` (run with `-s`), and the F1 of `scripts/gold_score.py` if
`library/contrefeu.gold.tsv` exists (otherwise "no gold yet").

SPEC §3.1.3: segmentation handles French and Italian conventions (abbreviations, dialogue dashes and guillemets,
ellipses, quotations ending in punctuation). Today `build_book` uses v0.1's `aligner.split_sentences`
(`aligner.py:26,275`): a split only after `.?!` + whitespace + `[A-ZÀ-ÝÆŒ]`, so it misses `…`, `?`/`!` followed
by a closing `»`, a dialogue dash, an opening `«`, and splits after "M." or "Sig.".

- New module `tradurre/services/segment.py`, `split_sentences(text: str) -> list[str]`. A boundary is, in order:
  1. a terminator: one or more of `.` `?` `!` `…` (so `...`, `?!`, `!…` count once);
  2. optional closers: zero or more of `»` `”` `"` `’` `)` `]`, each optionally preceded by whitespace (so
     `! »` and `."` end the sentence *after* the closer);
  3. whitespace (at least one character; Python's `\s` covers U+00A0 and U+202F, which French uses before
     `?!»:;`);
  4. the next sentence's start: optional openers (`«` `“` `"` `(` `—` `–` or a `-` followed by whitespace,
     with whitespace between), then a character for which `str.isupper()` is true. Digits and lowercase never
     start a sentence (so `« Viens ! » dit-il.` and `Que faire ? se demanda-t-il.` stay whole).
  
  No boundary after an abbreviation: the token before the terminator (letters and inner dots, from the last
  whitespace or opener) is, **case-sensitively**, one of `M MM Mme Mlle Mgr Dr Pr St Ste Me Sig Sigg Sig.ra
  Sig.na Dott Dott.ssa Prof Prof.ssa Avv Ing Mons SS cf p pp vol chap fig éd` (the dot that follows it being the
  terminator), or a single uppercase letter (an initial: `J. Dupont`). Case matters: Italian `a me.` ends a
  sentence, `Me` (Maître) doesn't. `etc.` and `ecc.` are **not**
  abbreviations here: they end sentences often enough, and a wrong split is one `j` away.
  Segments are the text between boundaries, stripped; empty ones dropped. Invariant, tested: the segments, with
  all whitespace removed and concatenated, equal the input with all whitespace removed.
- `tradurre/services/build.py`: `_blocks` uses `segment.split_sentences` (keep the `or [block.text]` fallback);
  update the module docstring. `aligner.split_sentences` and its callers in the old API stay untouched (Stage 7
  removes them).
- `tests/test_segment.py`, one test per rule with French and Italian examples written for the test (never text
  from the reference book): `.`/`?`/`!` + capital; `…` and `...` + capital vs + lowercase; `? »` / `! »` then a
  capital (boundary after `»`) vs then `dit-il`; `."` / `.”`; NBSP and U+202F before `?` and `»`; dialogue
  `— Tu viens ? — Non.` (two segments); an opening `« ` after a period; `(` after a period; accented capitals
  (`À`, `É`); each abbreviation group (French titles, Italian titles, `p.`/`cf.`, an initial) not splitting;
  `etc.` + capital splitting; Italian `a me. Poi` splitting; digits after a period not splitting; the whitespace invariant over all the test
  inputs (a parametrized check).
- `tests/test_library.py`: one test, per side, that the invariant holds on every included block of the reference
  book (counts only in the failure message: how many blocks break it).
- Diagnostics for the `Report:` (a throwaway script in the scratchpad, never committed, printing counts only),
  per side, with the old and the new splitter on the reference book's included blocks: segment count; segments
  over 400 characters (likely missed boundaries); segments starting with a lowercase letter (likely wrong
  splits); segments whose last token is in the abbreviation list (wrong splits the old splitter made).
- Don't touch the aligner (`align`, `find_anchors`), the extractor, the API or the frontend.

### Baseline local aligner
SPEC §3.1.4: a baseline alignment runs locally (no GPU, seconds per book), producing beads with real confidence.
Decided (user, 2026-10-03): this work is **capped**: one anchor + length aligner, a target alignment F1 on the
gold agreed with the user, no further tuning rounds. Asked again after the first book (user, 2026-10-04): no
Colab, no more aligner work unless a gold book scores below 0.95.

Baseline (Gold v2 report, 2026-10-04, interim anchor aligner): alignment F1 **0.870** (P 0.840, R 0.903),
1353 predicted beads vs 1222 gold. Measured by Pauli (counts only): segmentation is identical in gold and import
(1383/1426 segments; the user split or joined nothing); gold beads are 1204 × 1:1, 14 × 1:2, 4 others, **0
one-sided**; the interim aligner makes only 1:1 (1173), 1:0 (87) and 0:1 (93): no 2:1/1:2 at all, and where its
anchors run out it emits one side's run unpaired then the other's (gold beads 1099–1164, 66 beads, is one such
gap). A length-based DP addresses exactly this.
**Target (agreed with the user, 2026-10-04): alignment F1 ≥ 0.95.**
The user then joined two false splits in the gold book (`Tr.`, `Com.`: abbreviations particular to this novel,
not added to the segmenter); re-export the gold before scoring (the score is the same either way).
**Result (Pauli, 2026-10-04, verified):** the length aligner meets the target on the gold (F1 0.994, P 0.991, R
0.998). Measured by Pauli on synthetic input it is not yet fit for SPEC §1's scale (books up to 10,000 sentences a
side): it keeps two full (n+1)×(m+1) Python tables although it computes only a band, so 10,000 × 10,000 took
11.7 s and **1.8 GB**, and 10,000 × 10,300 (300 extra target sentences at the end) 44 s and **2.5 GB**, inside the
server process. "Length aligner at book scale" fixes that before it becomes the import's aligner.
**Fixed and verified (Pauli, 2026-10-04):** 7.3 s / 47 MB and 35.9 s / 101 MB; gold unchanged. Accepted limit: the
narrow-band-first rule can miss the optimum without nearing the band edge when the segment counts differ wildly
(found once in 200 random inputs, 13 × 146 segments, a slightly costlier path). Real pairs of editions are far
from that; not worth more work. If a real book needs faster alignment, numpy is the next step (not a dependency
today).
Known weakness (Pauli, synthetic probe, not a task yet): the length ratio is taken over the whole input, one-sided
material included, so a large one-sided run skews it. 600 sentences against the same 600 plus N other sentences
at the end: N = 10 → 598/600 pairs right, N = 30 → 591, N = 60 → 523 (the extra text gets smeared over the book
as 1:2 beads). Real text has anchors that resist this, and excluding front/back matter before alignment would
remove the main source; "Front and back matter" now does that for marked front/back matter. Revisit if a real book shows it.

#### Length aligner
Status: done
**Done when:** `uv run pytest` passes with the new `tests/test_align.py`; `uv run python scripts/gold_score.py
--aligner length` runs on the gold; the `Report:` gives alignment P/R/F1 and the bead count for both `--aligner
anchor` and `--aligner length`, the aligner's own wall time on the reference book, and the predicted bead shapes
(counts of 1:1, 1:0, 0:1, 2:1, 1:2, 2:2). The import's default does **not** change in this task.

- New module `tradurre/services/align.py`, `align(source: list[str], target: list[str]) -> list[Bead]`, `Bead` a
  dataclass `(source: list[int], target: list[int], confidence: float)` of indices into the inputs. Every index
  appears exactly once, in order on each side (the beads tile both sequences). Either list may be empty.
- Algorithm: dynamic programming over (i, j) with moves 1:1, 1:0, 0:1, 2:1, 1:2, 2:2 and cost = prior + length
  + anchor:
  - prior = −ln p, p(1:1) = 0.89, p(1:0) = p(0:1) = 0.005, p(2:1) = p(1:2) = 0.045, p(2:2) = 0.011;
  - length (Gale–Church), for moves with both sides non-empty: `ls`, `lt` = character counts (whitespace removed)
    of the move's source and target segments, `c` = total target chars / total source chars over the whole
    input (1 if a side is empty), `δ = (lt − ls·c) / sqrt(ls · 6.8)`, cost = −ln max(1e-12, erfc(|δ| / √2));
    zero for 1:0 and 0:1;
  - anchor, for moves with both sides non-empty: −1.5 × min(3, number of distinct tokens present on both sides),
    a token being a run of digits, or a word that starts with an uppercase letter and is not the first word of
    its segment (compare exactly).
  - Band: only cells with |j − i·m/n| ≤ 100 + |m − n| (n, m = input lengths; all cells if either is 0 or the band
    covers everything); the DP must still reach (n, m).
  - Ties broken by the move order listed above (1:1 first).
- Confidence per bead: `round(exp(−max(0, cost − (−ln 0.89)) / 4), 3)`, so a clean 1:1 is near 1 and a 1:0 is
  about 0.27.
- `tradurre/services/build.py`: `build_book(..., aligner: str = "anchor")`; `"length"` uses `align.align` and
  writes beads with method `"length"` and the bead's confidence; `"anchor"` is today's path, unchanged. The API
  doesn't pass it (so the app stays on `"anchor"`).
- First re-export the gold: `uv run python scripts/gold_export.py 046fb6f2-ba5d-4b6b-ac1a-d6a9caf9f38c`.
- `scripts/gold_score.py`: `--aligner {anchor,length}` (default `anchor`), passed to `build_book`; also print the
  predicted bead shapes (as in the Done when) and the aligner's wall time separately from extraction.
- `tests/test_align.py` (synthetic texts only): equal sequences of similar-length sentences → all 1:1; one long
  source sentence against two target sentences of proportional length → a 1:2 bead; a source
  sentence with no counterpart in a run of equal-length pairs, long enough that merging it is implausible → a 1:0
  bead; anchors (names, numbers) choose between two length-equivalent pairings; an empty side → all one-sided;
  very different lengths (10 vs 30 segments) still tile; a randomized check (20 seeds, random lengths up to 60
  segments a side) that every result tiles both sides in order; 1,500 × 1,500 synthetic sentences align in under
  5 s; confidence of a clean 1:1 > 0.8 and of a 1:0 < 0.4.
- Don't change `aligner.py`, the API, the frontend or any existing test.
Report: 2026-10-04 — `services/align.py` (banded Gale–Church + anchors), `build_book(aligner=)`, gold_score `--aligner`/shapes/timings, 10 tests in `tests/test_align.py`. Gold: anchor P 0.840 R 0.903 F1 0.870, 1353 beads (1:1 1173, 0:1 93, 1:0 87); length P 0.991 R 0.998 **F1 0.994 ≥ 0.95**, 1256 beads vs 1222 gold (1:1 1218, 1:2 16, 2:1 10, 1:0 6, 0:1 6); exclusion unchanged (F1 0.592). `align.align` on the book's 1231×1243 included segments: 1.8 s (build step 1.9 s vs 1.0 s for anchor). pytest 373 passed (was 363).

#### Length aligner at book scale
Status: done
**Done when:** `uv run pytest` passes, with the two new tests below in `tests/test_align.py`; `uv run python
scripts/gold_score.py --aligner length` prints exactly the numbers of the "Length aligner" report (P 0.991 R 0.998
F1 0.994, 1256 beads, the same shapes); the `Report:` gives time and peak RSS of `align.align` on 10,000 × 10,000
and on 10,000 × 10,300 synthetic sentences (below), each under **300 MB**, the first under **10 s**, the second
under **45 s**.

Same costs, same results, less memory and less work. Only `tradurre/services/align.py` and `tests/test_align.py`
change.
- Storage: per DP row, only the band cells `lo..hi`: an `array('d')` of best costs and an `array('b')` holding
  the index in `_MOVES` of the chosen move (−1 for none), plus that row's `lo`. A previous cell outside its row's
  stored range counts as unreachable. No (n+1)×(m+1) structure, no tuple per cell. The move cost is not stored:
  backtracking recomputes the chosen move's cost with the same function, for the confidence.
- Segment lengths from prefix sums (no `sum` over slices in the inner loop).
- Adaptive band: run first with width `_BAND`; if the backtracked path passes within 10 cells of a band edge that
  is not clipped by the grid (some (i, j) with `j − lo_i < 10` and `lo_i > 0`, or `hi_i − j < 10` and
  `hi_i < m`), run once more with width `_BAND + |m − n|` (today's width) and return that result. When the two
  widths are equal there is no second run.
- Tie-breaking, confidence and every cost stay exactly as they are; the existing tests don't change.
- New tests: (1) `_book(300, seed=1)` against itself followed by `_book(150, seed=99)` (more than `_BAND`
  extra, so the narrow pass runs into the band edge): the result equals the result with `_BAND` monkeypatched to
  10,000 (no band at all); Pauli checked that today's code passes this. (2) under `tracemalloc`, aligning
  2,000 × 2,000 synthetic sentences peaks under 25 MB.
- Measure (scratchpad script, not committed): sentences from `tests/test_align.py`'s `_book` (seed 1);
  10,000 × 10,000 is `_book(10000)` against itself, 10,000 × 10,300 is `_book(10000)` against `_book(10300)`
  (same seed, so the extra 300 are at the end); time with `time.perf_counter`, peak RSS with
  `resource.getrusage`, one process per case. Pauli's probe of this design: ~7.5 s / ~45 MB and ~28 s (second
  pass alone) / ~95 MB.
Report: 2026-10-04 — `align.py`: band rows only (`array('d')` costs + `array('b')` move indices), prefix sums, move cost inlined in the DP loop, adaptive band (narrow, rerun wide if the path comes within `_EDGE` = 10 of an unclipped edge); 2 new tests (fallback equals unbanded; 2,000² peaks 5.6 MB traced, was 101 MB). Gold unchanged (P 0.991 R 0.998 F1 0.994, 1256 beads, same shapes). 10,000 × 10,000: 7.3 s, peak RSS 47 MB; 10,000 × 10,300: 35.9 s, 101 MB. Same output as before on 199 of 200 random inputs; the other (13 × 146 segments) finds a costlier path: the narrow pass misses the optimum without nearing its edge. pytest 375 passed.

#### Length aligner on import
Status: done
**Done when:** `uv run pytest`, `npm run type-check` and `npm run test:e2e` pass; importing the reference PDFs
through the form gives beads with method `length`; `gold_score.py` (no `--aligner` any more) prints the same
alignment numbers as the "Length aligner" report.

- `tradurre/services/build.py`: `build_book` loses its `aligner` parameter and the anchor path; it always uses
  `align.align`, method `"length"`, the bead's confidence. Update the module docstring (it still says alignment
  is v0.1's). `scripts/gold_score.py` loses `--aligner` (keeps shapes and timings). `aligner.py` stays for the
  old v0.1 API; nothing in the new model imports it.
- Tests. Pauli forced the length aligner into the suite (2026-10-04): 12 Python tests fail, all in
  `tests/test_build.py`, `tests/test_books_api.py` and `tests/test_books_corrections_api.py`, because their tiny
  fixtures (e.g. `SOURCE`/`TARGET` at `tests/test_books_api.py:14-15`) expect a 1:0 bead. **The length aligner
  cannot produce that on a 3–4 sentence text:** with the Gale–Church priors (2:1 at 0.045 vs 1:0 at 0.005) and a
  ratio taken from so little text, merging the unmatched sentence into a neighbour always costs less; Pauli tried
  longer fixtures and it still merges. So the plan's earlier rule ("change the fixture, not the expectations") is
  withdrawn. Instead:
  - expected methods become `"length"`; expected confidences are asserted as ranges or not at all, never as
    exact floats;
  - a test whose purpose is the alignment itself (`test_build.py`) asserts the new layout, after checking it is
    a sensible one (the unmatched sentence merged into its neighbour, not a shifted pairing); pick fixture text
    so it is (sentences of distinct lengths; a name or number not at the start of each matched pair);
  - a test whose purpose is a correction or the API asserts against the new layout; if it needs a one-sided bead,
    it creates it in its setup with a correction (e.g. move the last target segment to the next bead), and its
    own assertions are otherwise unchanged in meaning;
  - the e2e specs that import the same fixtures (`books.spec.ts`, `book-view.spec.ts`, `book-corrections.spec.ts`,
    `segment-editing.spec.ts`) follow the same rules.
  List in the `Report:` every test whose expectations changed, with one phrase each.
- `tests/test_align.py` `test_memory_stays_within_the_band` takes 12 s of the suite's 31 s (tracemalloc slows
  every float allocation). Rewrite it to monkeypatch `_BAND` to 10 and align `_book(500, seed=13)` against itself,
  asserting a peak under 2 MB. Pauli measured: 0.6 MB in 0.75 s; the pre-"book scale" code peaked at 5.3 MB, so
  the test still tells the two apart.
- Don't change `align.py`, the segmenter, the extractor or any endpoint.
Report: 2026-10-04 — `build_book` always uses `align.align` (method `length`), anchor path and `--aligner` removed; reference PDFs through `POST /api/v2/books`: 4.8 s, 1256 beads, all `length`, 12 one-sided; gold P 0.991 R 0.998 F1 0.994. Tests changed: `test_build.py` 3 (method `length`, confidence ranges; extra sentence now joins its neighbour's 2:1 bead, renamed); `test_books_api.py` import read-back and list counts (new 3-bead layout); `test_books_corrections_api.py` new `gap` fixture (move + split restore the one-sided layout) for move, merge/split, reviewed, skim, edit/split/join, join-across, undo/redo row on the plain import; memory test 500² with `_BAND` 10 (under 1.1 s; was 12 s). e2e: `restoreGap` (same two corrections via the API) in the book-view, book-corrections and segment-editing helpers; undo/redo and Escape tests on the plain import with its own rows; books.spec form import 2 beads. pytest 375 passed; type-check passes; e2e 28 passed.

### Import warnings and run metadata
Status: done
**Done when:** `uv run pytest` passes (new migration and API tests); `npm run type-check` passes; `npm run
test:e2e` passes with the new test **three full runs in a row** (default workers); the `Report:` quotes the stored stats JSON of a reference-book import (counts
and timings only, no text), taken from `test_import_through_the_api` run with `-s`.

SPEC §3.1.5 (warnings attached to the project, shown in the review view) and §4 "Debuggable" (runs record counts,
timings, warnings in the project). Today the import's warnings are only in the `POST` response
(`api/books.py:78-80`), shown once by `BookImport.vue`, then lost; nothing records counts or timings.

- `tradurre/db.py`: migration 5 `_m005_runs` (append to `MIGRATIONS`, `_run_script`):
  ```sql
  CREATE TABLE runs (
      id          INTEGER PRIMARY KEY,
      project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
      kind        TEXT NOT NULL CHECK (kind IN ('import', 'align')),
      created_at  TEXT NOT NULL,
      app_version TEXT NOT NULL,
      stats       TEXT NOT NULL              -- JSON object
  );
  CREATE INDEX idx_runs_project ON runs(project_id, id);
  CREATE TABLE warnings (
      id      INTEGER PRIMARY KEY,
      run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
      side    TEXT CHECK (side IN ('source', 'target')),   -- NULL: the whole run
      message TEXT NOT NULL
  );
  ```
  `'align'` is reserved for Stage 5; only `'import'` is written now. Runs are not operations: not in the undo log.
- `tradurre/api/books.py`, `import_book`: time each side's `extract` (`time.perf_counter`, around the threadpool
  call) and `build_book`; in the same transaction as the build, insert one `import` run (`app_version` =
  `importlib.metadata.version("tradurre")`) and one `warnings` row per extraction warning, with its side and the
  message **without** the "source: " prefix (the `POST` response keeps its prefixed list unchanged). `stats`:
  ```json
  {"source": {"filename": "…", "format": "pdf", "bytes": 0, "extract_ms": 0, "pages": 0,
              "blocks": {"paragraph": 0, "page_number": 0, …}, "excluded_blocks": 0, "segments": 0},
   "target": {…}, "build_ms": 0, "beads": 0, "one_sided_beads": 0, "low_confidence_beads": 0,
   "bead_shapes": {"1:1": 0, "2:1": 0, …}}
  ```
  `pages` = the highest block `page`, or `null` (txt/docx); `blocks` counts every kind present; `segments` counts
  the side's included segments; `low_confidence_beads` counts beads with confidence < 0.5 (the threshold Stage 4
  will highlight); `bead_shapes` counts beads by "source segments:target segments", only shapes present; ms are
  integers. Counts come from the database after `build_book` (one query
  each), not from re-running segmentation.
- `tradurre/models.py` + new endpoint `GET /api/v2/books/{id}/runs` → `list[BookRun]`, newest first: `id`,
  `kind`, `created_at`, `app_version`, `stats` (`dict`), `warnings: list[{side: str | None, message: str}]`;
  404 for an unknown book (as `get_book`). `BookResponse` does not change.
- Frontend: `client.ts` `booksApi.getRuns(id)` and a `BookRun` type. `BookView.vue` fetches the runs once on
  mount (not after corrections) and shows, in the header next to "Show excluded", a button `data-testid="import-log"`
  labelled "Import log", or "Import log (N warnings)" / "(1 warning)" in amber when the latest import run has
  warnings. Clicking it toggles a panel under the header (`data-testid="import-log-panel"`): the warnings as a
  list (`data-testid="import-warning"` per item, "source: …"/"target: …"), then the latest import run's
  `created_at`, `app_version` and `stats` as indented JSON in a `<pre data-testid="import-stats">`. Keyboard
  navigation keeps working while it is open (the button is not a text entry).
- Tests:
  - `tests/test_books_api.py`: a txt import stores one run whose `stats` has the counts of the known fixture
    (the length aligner's layout, see `test_import_txt_and_read_back`: `beads` 3, `one_sided_beads` 0,
    `low_confidence_beads` 1, `bead_shapes == {"1:1": 2, "2:1": 1}`, `source.blocks == {"paragraph": 3}`, `pages`
    null, `extract_ms` ≥ 0) and no
    warnings; the Latin-1 import stores one warning with side `target` and the unprefixed message; the PDF pair
    test also checks `pages` 3 and `blocks.page_number` 3 per side; unknown book → 404; a refused import (empty
    txt) writes no run.
  - `tests/test_bead_index.py:149` already checks `user_version == len(MIGRATIONS)`; add nothing there unless it
    fails.
  - `tests/test_library.py` `test_import_through_the_api`: also `GET …/runs` and print its `stats` (with `-s`);
    assert only that it has one run.
  - `frontend/e2e/books.spec.ts`: after a Latin-1 target import through the API, the book view's button reads
    "Import log (1 warning)", opening it shows the warning and the stats, and ↓ still moves the current bead.
- **Unblocked (Pauli, 2026-10-04, second time):** resume from the uncommitted working tree (all of the above,
  plus `_store_book` run with `run_in_threadpool`, which stays). The worker thread freed the event loop but the
  build held the write lock ~10 s, so other writers hit `database is locked` (Braun's second report). Pauli measured
  a 10,000-sentence `build_book`: 9.8 s, of which alignment ~8.1 s and segmentation + writes ~1.7 s. So:
  - `tradurre/services/build.py`: split `build_book` in two. `prepare_book(source, target) -> PreparedBook` does
    everything that needs no database: `_blocks` per side, the included segment texts, and `align.align` on them
    (a dataclass holding both sides' `NewBlock` lists and the `align.Bead` list). `write_book(conn, project_id,
    prepared)` creates the documents and appends the beads, mapping bead indices to segment ids exactly as today.
    `build_book(conn, project_id, source, target)` stays, as `write_book(conn, project_id, prepare_book(source,
    target))`, so `scripts/gold_score.py` and `tests/test_build.py` don't change.
  - `tradurre/api/books.py`: `import_book` runs `prepare_book` in the threadpool **before** `_store_book`, which
    now takes the prepared book and calls `write_book` inside its transaction; the write lock then covers only the
    writes. `build_ms` = prepare + write (the stats shape doesn't change).
  - `tradurre/db.py` `get_connection`: `sqlite3.connect(..., timeout=15)` (was the default 5 s), so a writer
    queued behind a big import's ~2 s of writes waits instead of failing. One line; every connection gets it.
  - No new test: the e2e suite is the check ("three runs in a row" above). If it still fails, stop with the
    server log's errors.
- Don't change the aligner, the segmenter, the extractor or any correction endpoint.
Report: 2026-10-04 — blocked: everything is implemented (migration 5, run + warnings written by the import, `GET …/runs`, Import log button/panel, tests) and pytest (378) and type-check pass, but `npm run test:e2e` fails 1–2 tests per run (different ones, all timing out on page load). Cause, pre-existing since "Length aligner on import": `import_book` runs `build_book` on the event loop, and the two e2e tests that import 10,000 beads take ~10 s each, freezing every other request of the shared e2e backend meanwhile; with those two tests deselected the suite passes twice in a row (27/27). Needs a decision: run the build in a worker thread (likely fix) or not.
Report: 2026-10-04 — blocked again: the build now runs in a worker thread (`_store_book` via `run_in_threadpool`; pytest 378, type-check pass), and e2e got worse: 4–6 failures per run (3 runs), each a `500` from `sqlite3.OperationalError: database is locked` in the server log. The event loop is free now, but the 10,000-bead imports hold the write lock ~10 s and the other tests' imports and corrections give up after sqlite3's 5 s timeout: the "known and accepted" limit is what breaks the suite. Needs a decision.
Report: 2026-10-04 — done: migration 5 (`runs`, `warnings`); the import stores one run (stats as specified, plus `low_confidence_beads`, `bead_shapes`) and its unprefixed warnings; `GET /api/v2/books/{id}/runs`; Import log button/panel in `BookView.vue`; `build.py` split into `prepare_book` (segment + align, no database) and `write_book`, both run in the threadpool, the write transaction only around the writes; `get_connection` timeout 15 s. pytest 378 passed; type-check passes; e2e 29 passed three runs in a row. Reference import stats: source pdf 624690 bytes, extract 1678 ms, 128 pages, blocks footnote 3 / heading 27 / page_number 120 / paragraph 208, 123 excluded, 1260 segments; target pdf 675518 bytes, extract 1781 ms, 184 pages, footnote 2 / heading 27 / page_number 157 / paragraph 197, 159 excluded, 1266 segments; build 1468 ms; 1256 beads, 12 one-sided, 25 low-confidence; shapes 1:1 1218, 1:2 16, 2:1 10, 1:0 6, 0:1 6. Gold score unchanged (F1 0.994).
