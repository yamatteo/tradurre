# Tradurre — Plan, archived: Stage 6

Completed stage moved out of `PLAN.md` on 2026-10-04; kept as the record of its tasks, reports and
verifications. Stage numbers mentioned below refer to the plan at that date. Book text never appears here: the
reference book is copyrighted, and only counts and features were recorded.

## Stage 6 — Search and export
Done (2026-10-04).

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
Verified (Pauli, 2026-10-04): Done when holds (commit a57bd9e). Every timed wait is frame-precise; untimed ones stay
`expect`. Corrections at 5,000 beads are 150–290 ms: a 2× margin, so returning the whole book per correction stays.
Braun's note holds: `npm run type-check` doesn't cover `e2e/` (no tsconfig includes it), next task. Checked here
with `tsc --strict --lib es2022,dom,dom.iterable --types node`: all e2e files and `playwright.config.ts` have 0
errors.

#### Type-check the e2e tests
Status: done
**Done when:** `npm run type-check` passes and covers `e2e/*.ts` (shown by temporarily adding `const n: number = 'x'`
to an e2e file: `type-check` fails; then removed); `npm run test:e2e` passes; `uv run pytest` unchanged.

- New `frontend/tsconfig.e2e.json`, like `tsconfig.node.json`: extends `@tsconfig/node24/tsconfig.json`, `include:
  ["e2e/**/*.ts"]`, `compilerOptions`: `noEmit: true`, `tsBuildInfoFile: "./node_modules/.tmp/tsconfig.e2e.tsbuildinfo"`,
  `module: "ESNext"`, `moduleResolution: "Bundler"`, `types: ["node"]`, and `lib` of the base plus `"DOM"`,
  `"DOM.Iterable"` (the page-side functions use `document`; list the base's entries, `lib` replaces, not merges).
- `frontend/tsconfig.json`: add `{ "path": "./tsconfig.e2e.json" }` to `references`. Nothing else changes; no spec
  file changes unless the check reports an error (then fix the type only, no behaviour, and list it in the report).
Report: 2026-10-04 — new `frontend/tsconfig.e2e.json` (node24 base, Bundler, DOM + DOM.Iterable), referenced from
`tsconfig.json`; no spec file needed a fix. `const n: number = 'x'` in `scale.spec.ts` → `type-check` fails (TS2322),
removed → passes; e2e 62 passed; pytest 414 passed.
Verified (Pauli, 2026-10-04): Done when holds (commit 4986cd0; `type-check` rerun here, clean). The `*.json` rule in
`.gitignore` stays: it is the safety net that keeps book-derived JSON (golds, extractions) out of a public repo; a new
config JSON is added with `git add -f`, as the tsconfigs were (noted under Current state). Next: Search page.

#### Search page
Status: done
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
Report: 2026-10-04 — new `BookSearch.vue` at `/search` (state in the URL, `router.replace`; side select; book chip
with × ; results with marked spans, "Not reviewed" pill, Context (`around=2`, own bead tinted) and Open; More results
by offset; No results); "Search" link in the book top bar; new `e2e/search.spec.ts`, 5 tests (each with its own
random-tagged words: the e2e database is shared). Matches use the global `mark` style in `main.css` (unlayered, it
overrides Tailwind classes). type-check clean; e2e 67 passed; pytest 414 passed.
Verified (Pauli, 2026-10-04): Done when holds (commit 44246fd; type-check rerun, clean). SPEC §3.4 is met end to end:
one query, three sides, word beginnings and phrases, bead results with highlight, title and position, context on
demand, open at the bead, unreviewed marked, excluded never indexed. The yellow `mark` is the v1 rule in `main.css`;
Stage 7 restyles it with the A tokens when v1 goes.

### Export
Decided (user, 2026-10-04): the translator uses no translation software and won't open spreadsheets; in-app
search is how they use the corpus. So corpus export (TMX/TSV) moved to SPEC §5 "Later" (agreed); edition export
is due with v0.2. The project bundle stays in SPEC §3.5.

#### Edition export
Status: done
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
  href download>` links to that URL; always enabled; clicking one closes the menu (`emit('toggle')`). The book id
  comes from the injected `selection.book` (`MoreMenu.vue` already injects `selectionKey`): no new prop.
- Tests: `tests/test_edition.py` on a synthetic book (as `tests/test_domain_blocks.py` builds one): a heading, two
  paragraphs, an excluded running head and an excluded footnote, one segment edited → txt is BOM + heading +
  blank line + paragraph 1 (segments joined by a space, the edited text) + blank line + paragraph 2 + newline,
  nothing excluded; including the footnote (`include_block`) adds it in its place; docx read back with
  `python-docx`: the heading's style is "Heading 1", then the two paragraphs. `tests/test_books_api.py` (or a new
  `test_books_export_api.py`): content type, disposition filename, 404, 422. e2e (`book-layout.spec.ts`): More →
  "Target text (.txt)" → a download (`page.waitForEvent('download')`) named `<title> (IT).txt` whose content
  holds the target text.
- The v1 export (`api/export.py`) is untouched (Stage 7).
Report: 2026-10-04 — new `services/edition.py` (`edition_blocks`, `edition_txt`, `edition_docx`); `GET
/books/{id}/export/edition` (ASCII `filename` with non-ASCII as `_`, plus `filename*` when the name isn't ASCII);
`booksApi.editionUrl`; `MoreMenu.vue` "Export" with the four links. Tests: `test_edition.py` 4, new
`test_books_export_api.py` 4, e2e download test in `book-layout.spec.ts`. pytest 422 passed (414 before), type-check
clean, e2e 68 passed.
Verified (Pauli, 2026-10-04): Done when holds (commit fccc115). Included blocks only, current `text`, document order,
heading → "Heading 1"; the filename fallback is sound (`filename*` carries the real name). Braun's two deviations
(URL in `client.ts`; `_` for non-ASCII in the plain `filename`) accepted. Empty segment text can't occur:
`edit_text` refuses it.

#### Project bundle
SPEC §3.5: "export/import of the text layer and alignment of one project, as a full backup". Decided (Pauli,
2026-10-04):
- **Format:** a zip, `<title>.tradurre.zip`, holding one `bundle.json` (UTF-8, `ensure_ascii=False`). A zip because
  a book's JSON is 1–2 MB and compresses ~4×, and Windows opens it without tools; one file inside, so it stays
  trivially inspectable. Versioned: `"format": "tradurre-bundle", "version": 1`.
- **Contents:** the book (title, languages, created/updated), both documents (side, filename, format) with their
  blocks in order (kind, excluded, page) and each block's segments in order (`text`, `original_text`, and `bead`:
  the index of its bead in `beads`, or null when the block is excluded), the beads in order (confidence, method,
  reviewed), and the runs with their stats and warnings (SPEC §4 "Debuggable": they travel with the book). Ids and
  ords are not stored: order is the list order, so a bundle never depends on a database's ids.
- **Not included: the operation history.** A backup restores the state, not the way it was reached; the restored
  book starts with nothing to undo. History rows reference row ids that a restore renumbers, so carrying them
  would mean rewriting every `changes` JSON: cost with no use for the translator.
- **Import is always a new book** (new uuid, title as in the bundle), never over an existing one; ords are
  rebuilt with `GAP` spacing; the whole import is one transaction and is refused (nothing written) if the bundle
  is malformed or the result breaks an invariant (`check_project`). `bead_index` fills itself through its
  triggers, so a restored book is searchable at once.

##### Bundle: export and import in the service
Status: done
**Done when:** `uv run pytest` passes with the new `tests/test_bundle.py`; nothing else changes.

- New `tradurre/services/bundle.py`:
  - `class BundleError(ValueError)`; `FORMAT = "tradurre-bundle"`, `VERSION = 1`.
  - `export_bundle(conn, book_id) -> bytes`: the zip (`zipfile.ZIP_DEFLATED`) with `bundle.json`:
    `{"format", "version", "app_version" (importlib.metadata.version("tradurre")), "exported_at" (UTC ISO),
    "book": {"title", "source_lang", "target_lang", "created_at", "updated_at"}, "documents": [{"side",
    "filename", "format", "blocks": [{"kind", "excluded" (bool), "page", "segments": [{"text", "original_text",
    "bead"}]}]}] (source first), "beads": [{"confidence", "method", "reviewed" (bool)}] (by `ord`), "runs":
    [{"kind", "created_at", "app_version", "stats" (the parsed JSON object), "warnings": [{"side", "message"}]}]
    (by id)}`. Blocks by `ord`, segments by `ord`; `bead` is the index of the segment's bead in `beads`.
  - `import_bundle(conn, data: bytes) -> str`: the new book id. Inside one `transaction(conn)`: insert the
    project (new `uuid4`, the bundle's title, languages and timestamps), documents, blocks (`ord = i * GAP`),
    beads (`ord = k * GAP`), segments (`ord = j * GAP`, `bead_id` from the index), runs and warnings; then
    `check_project(conn, id)`: any violation → `BundleError` naming the first one (the transaction rolls back).
    `BundleError` also for: not a zip or no `bundle.json` ("Not a Tradurre bundle"), a wrong `format` (same),
    `version` above `VERSION` ("This bundle needs a newer Tradurre (version N)"), a missing key or a wrong type,
    a `bead` index out of range ("Malformed bundle: …" with the path, e.g. `documents[0].blocks[3].segments[1]`).
    A bead no segment points at is caught by the invariant check (I3).
- `tests/test_bundle.py`, on a synthetic book built like `tests/test_edition.py`'s fixture plus a one-sided bead,
  a reviewed bead, an edited segment and a run with one warning:
  - round trip: `import_bundle(export_bundle(...))` gives a second book whose normalized form equals the first's
    (a helper reading both books as the bundle structure without ids: compare `json.loads` of each export,
    ignoring `exported_at`); `check_project` is `[]`; `search_beads` with the edited word finds a bead in both
    books;
  - the zip holds exactly `bundle.json`, and its `"version"` is 1;
  - refused, with no project added (count `projects` before and after): bytes that aren't a zip; a zip without
    `bundle.json`; `"format": "other"`; `"version": 2`; a segment with `"bead": 99`; a bead no segment points at;
    an excluded block whose segment has a bead (I1).
Report: 2026-10-04 — new `services/bundle.py` (`export_bundle`, `import_bundle`, `BundleError`; a schema refusal
(`IntegrityError`) also becomes `BundleError`); new `tests/test_bundle.py`, 9 tests: round trip (equal exports,
invariants hold, the restored book searchable), contents, and refusals (not a zip, no `bundle.json`, wrong format,
version 2, bead index 99, a bead without segments, I1, a missing key, a wrong type, a value the schema refuses), each
leaving `projects` unchanged. pytest 431 passed (422 before).
Verified (Pauli, 2026-10-04): Done when holds (commit 8477704; `test_bundle.py` rerun, 9 passed). Order is list
order, segments name beads by index, the history stays out (agreed by the user, 2026-10-04); a refusal of any kind
(missing key, type, range, schema CHECK, deferred foreign key at commit, invariant) rolls the whole restore back.
The extra `IntegrityError` → `BundleError` is right: the API needs a 400, not a 500. Braun's point on a restore
next to its original (two books, same title and dates) is taken: next task renames on a title clash.

##### Bundle in the API and the app
Status: done
**Done when:** `uv run pytest` passes with the new API tests; `npm run type-check` passes; `npm run test:e2e`
passes with the new test.

- API (`api/books.py`): `GET /books/{id}/export/bundle` → `application/zip`, `Content-Disposition` named
  `<title>.tradurre.zip` built exactly as the edition export's (move that code into a `_disposition(name)` helper
  both use; the edition tests must pass unchanged). `POST /books/bundle` (multipart field `bundle`) → 201
  `BookImportResponse` (`id`, `title`, `bead_count`, `warnings: []`); `BundleError` → 400 with its message.
- `services/bundle.py`, `import_bundle`: if another book already has the bundle's title, the restored book's title
  is `<title> (restored YYYY-MM-DD)` (today's UTC date), set in the same transaction; the bundle's dates are kept.
  `tests/test_bundle.py`: the round trip's restored title becomes `Livre (restored <today>)` (compare the exports
  without `book.title`); a restore into a database without the original keeps `Livre` (a second connection on a
  fresh `init_db` database).
- `client.ts`: `booksApi.bundleUrl(id)` and `booksApi.importBundle(file)`.
- Book screen, `MoreMenu.vue`, under "Export": a fifth item "Project bundle (.zip)" (`data-testid=
  "export-bundle"`), the same kind of `<a download>` link.
- Library (`ProjectList.vue`): next to the import button, "Restore a bundle" (`data-testid="restore-bundle"`)
  opening a hidden `<input type="file" accept=".zip">`; on a file → `importBundle` → navigate to `/book/<id>`; an
  error shows the server's message in a new `<p data-testid="restore-error" class="mb-4 text-red-600">` under the
  page header (the page has no error area yet), cleared on the next attempt.
- Tests: `tests/test_books_export_api.py`: the bundle's content type and filename, 404; `POST /books/bundle` with
  an exported bundle → 201 and a second book with the same `bead_count`; with garbage → 400 "Not a Tradurre
  bundle". e2e (`book-layout.spec.ts`): More → "Project bundle (.zip)" downloads `<title>.tradurre.zip`; then on
  `/`, "Restore a bundle" with that file (`setInputFiles`) lands on `/book/<new id>` showing the same number of
  bead rows and the title `<title> (restored <today, UTC>)`; then a garbage file shows "Not a Tradurre bundle" in
  `restore-error`.
Report: 2026-10-04 — `GET …/export/bundle`, `POST /books/bundle` (400 on `BundleError`), `_disposition` shared with the
edition export; `import_bundle` titles a clash with a book `<title> (restored <UTC date>)`; `booksApi.bundleUrl`,
`importBundle`; More → Export → "Project bundle (.zip)"; library "Restore a bundle" with `restore-error`. Tests:
`test_bundle.py` 10 (title on clash, kept elsewhere), `test_books_export_api.py` +3, e2e download → restore through
the file chooser → garbage refused. pytest 435 passed (431 before), type-check clean, e2e 69 passed.
