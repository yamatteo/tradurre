# Tradurre — Plan, archived: Stage 4

Completed stage moved out of `PLAN.md` on 2026-10-04; kept as the record of its tasks, reports and
verifications. Stage numbers mentioned below refer to the plan at that date. Book text never appears here: the
reference book is copyrighted, and only counts and features were recorded.

## Stage 4 — Review view
Done (2026-10-04).

The correction screen of Stage 2 grows into the review screen of SPEC §3.3 (as changed 2026-10-04): one mode,
problem-first. Plain text editing; TipTap is not used here. Steps in order; the layout tasks and the two review
tasks after them are ready ("Reviewed runs" in two sub-tasks).

Decisions carried into this stage:
- (user, 2026-10-03) `reviewed` and `confidence` stay separate signals. A correction sets the touched beads to
  `manual`/1.0 but leaves their reviewed mark as SPEC §3.3 says; "done with the book" = every bead reviewed.
- (Pauli, 2026-10-04, measured) the length aligner seldom emits 1:0/0:1; a sentence with no counterpart usually
  lands in a 2:1/1:2 bead of confidence ~0.4–0.45, against ≥ 0.78 for an ordinary 1:1. So "low confidence" is
  **< 0.5**, and the multi-segment toggle shows the rest.
- (user, 2026-10-03, refined 2026-10-04) cut/copy/paste: inside the sentence editor, on text (a text edit);
  outside it, on whole sentences, so a cut sentence pasted at the adjacent edge of the neighbouring bead is a
  bead-boundary move and nothing else is allowed. SPEC §3.3 has the line (agreed 2026-10-04).
- Keys must work on an Italian Windows layout: letters, Shift+letters, arrows, Enter, Tab, Ctrl+Z/Y only (no `[`,
  `]`, `/`, `\` and the like, which need AltGr or move around). Rare range commands go in the "More" menu, no key.
- (Pauli, 2026-10-04, measured in "Layout: frame, fonts and rows") **render rule** for the book screen, on top of
  the Stage 2 scale rule: (1) `BookView.vue`'s template reads nothing that changes on a move or a status message:
  such state is shown by a small child component that injects it (`BeadActions`, `BookPosition`), else every
  arrow key re-diffs all rows (it cost +1 s per 20 moves on 10,000 beads); (2) state changes inside a row are
  paint-only: recolour what is always there (a border, a mark), never add a background, border or shadow to an
  inline element, nor change text outside a size-contained box, since either lays out the whole list again;
  (3) no font may load after the list has rendered (a late font relays out every row at once, ~0.5 s on 10,000):
  hence the `latin` subsets only, and any new face or weight is imported in `main.ts` and used from the start.

### Problem navigation
Status: done
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes, including the new
`frontend/e2e/review.spec.ts`; `uv run pytest` is unchanged (391 passed).
Report: 2026-10-04 — `src/review.ts` (`LOW_CONFIDENCE`, `isProblem`); `BookView.vue`: `p`/`P`, "Next problem", "Highlight multi-segment", `problems N`; `BeadRow.vue`: `data-problem`, amber border, absolute `s:t · c.cc` badge; `e2e/review.spec.ts` 4 tests; type-check passes, e2e 33 passed (29 + 4), pytest 391 passed.
Verified (/pauli, 2026-10-04, `9f8ab7c`): code and the 4 e2e tests match the task; pytest 391. One defect,
fixed in the next task: the badge sits at `top-0 right-1` inside a row with `py-2 px-4`, so it overlaps the end
of the target text's first line by ~8 px vertically and ~45 px horizontally (hiding words the translator must
read). Reviewed low-confidence beads no longer stand out: that is the problem-first reading of SPEC §3.3 agreed
on 2026-10-04 (a reviewed bead was accepted), not a gap.

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

### Screen layout and shortcuts
Decided (user, 2026-10-04): **variant A** ("two-tier toolbar") of the Claude Design canvas "Tradurre — Review
screen" (https://claude.ai/artifact/KSfbEbpiELukzpHe8JPY86, private to the user; artboards A1–A4), with: the serif
text kept but **a little denser**; excluded blocks stay **independent, one row per block and side**, as now (not
paired across sides as A2 draws them); **no highlighting of changes** in edited text (it would need a diff/version
history; out of scope). Not taken from the mockup: A3's per-warning "Go to bead" (warnings carry no location) and its
invented stats list. Built before the review tasks below, so they add their controls into slots that exist.

Visual tokens (from A1, the source of truth for all three tasks), in `frontend/src/assets/main.css` as a Tailwind v4
`@theme` block (`--color-*`, `--font-*`), used through utilities:
- Fonts, **bundled** (SPEC §4: no network needed): `@fontsource/ibm-plex-sans` (400, 500, 600) for the UI,
  `@fontsource/source-serif-4` (400, 600) for book text, `@fontsource/ibm-plex-mono` (400, 500) for keys and
  numbers, imported in `src/main.ts`. Never a Google Fonts link.
- Colours: ground `#F3F2EE`, second bar `#F8F7F4`, list `#FDFDFB`, ink `#1D1F23`, muted `#5E6168`, faint `#6A6D73`,
  bar rule `#E0DDD6`, row rule `#EEECE7`, button hover `#E8E6E0`, outline border `#D5D2CA`, accent `#2B59A3`,
  current side `#EFF3FA`, current segment `#D3DFF3`, problem text `#9A4A0C`, problem mark `#C2661A`, count pill
  `#F6E7D6` on `#7D3D0A`, reviewed mark `#2D6B4F`, run `#F0F4FA`, excluded row `#F5F4F0`, progress fill `#4A6E9E`.
- `<kbd>` chips: mono 10.5 px, 1 px border `#CBC7BE` with a 2 px bottom border, radius 4, white.

#### Layout: frame, fonts and rows
Status: done
Report: 2026-10-04 — bundled fonts and `@theme` tokens; full-height book screen without the global nav, sticky column header, bottom bar with status and `position` (new `BookPosition.vue`, so a move doesn't re-render the list); `BeadRow` on A1's grid with gutter marks, meta column (`problem-badge` only on problems), separators, *Not in this edition*; excluded rows per side with Include in the meta column; four class-based e2e assertions switched to `data-reviewed`/text/CSS; pytest 391 passed, e2e 33 passed, type-check and build clean (92 font files, no googleapis); screenshots `scratchpad/layout-frame-1366.png` and `layout-frame-1366-excluded.png`; 20 ArrowDown on 10,000 beads ~1.2–1.45 s (HEAD ~0.9 s, limit 2 s).
Verified (Pauli, 2026-10-04): Done when holds (commit cc58788; the screenshots match A1 as amended). Deviations
accepted: the e2e checks of bold/grey/green switched to computed style and text, not only data attributes (they
still test what the user sees); Plex Sans 400 italic added for *Not in this edition*. Left over, folded into the
next task: the status message still lives in `BookView`'s template (each `say()` re-diffs all rows, and the run
message of "Reviewed runs" would do so on every Shift+arrow); 92 font files, mostly Cyrillic/Greek/Vietnamese
subsets nobody needs. Navigation is ~40% slower than before but under the limit: the 5,000-bead scale check
re-measures it.
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes unchanged (see the last bullet);
`uv run pytest` unchanged; `npm run build` succeeds, its output holds the font files, and `grep -rn googleapis
frontend/src tradurre/static` finds nothing; the `Report:` names a screenshot of the book screen at 1366 × 768
(Playwright, saved to the scratchpad, not committed) for the user to compare with A1.

- Fonts and tokens as above (`npm install` the three `@fontsource` packages as dependencies).
- `App.vue`: the global nav is not shown on the `book` route (the book screen has its own "Library" link). The
  book screen fills the window: `BookView.vue` root `h-screen flex flex-col` on the ground colour; the header
  (today's controls, unchanged in this task, restyled with the tokens) stays on top, the bead list is the only
  scrolling element (`flex-1 min-h-0 overflow-auto`, list background), and the status line moves to a bottom bar
  (26 px, top rule, 12 px muted): status message left (`data-testid="status"`), on the right `Bead {i} of {n} ·
  {Source|Target} · sentence {k} of {m}` (`data-testid="position"`; `sentence – of 0` on an empty side).
- A sticky column header in the list (28 px, 10.5 px uppercase faint): `Source · {source_lang}` and `Target ·
  {target_lang}` (the codes upper-cased, e.g. `FR`, `IT`).
- `BeadRow.vue`, rewritten on A1's grid: `grid-template-columns: 40px minmax(0,1fr) minmax(0,1fr) 96px`, rows
  separated by the row rule, max content width 1560 px centred.
  - Text cells: Source Serif 4 **15 px, line-height 1.45, padding 7px 16px 8px** (A1 has 16/1.55, 11/12 18: this
    is the "a little denser"); the target cell has a left row-rule border; headings 600; blocks start on a new line
    as now; between two segments of the same block a thin rule (1 px × 0.9 em, `#B4B0A6`, 8 px margins) instead
    of a space, so 2:1 beads show their parts.
  - An empty side shows *Not in this edition* (UI font, 12.5 px italic, `#6E7177`).
  - Gutter (40 px): a reviewed check (`#2D6B4F`, `aria-label="Reviewed"`) if reviewed, else a problem diamond
    (`#C2661A`, `aria-label="Problem"`) if `isProblem`, else nothing. The green/amber left borders go.
  - Meta column (96 px): mono 11 px, right-aligned, `{s}:{t} · {confidence, 2 decimals}`, always rendered but
    transparent unless the row is current (muted) or a problem (`#9A4A0C`, 500). It carries
    `data-testid="problem-badge"` only on problem rows. This replaces the absolutely positioned badge (so the
    overlap found in "Problem navigation" is gone, and "Reviewed runs" drops its badge fix).
  - Current bead: a 1.5 px accent inset outline; the current side's cell on the current-side colour; the current
    segment on the current-segment colour with a 2 px accent underline (box-shadow), replacing today's underline.
  - Keep every `data-*` attribute the e2e specs read (`data-bead-id`, `data-current`, `data-side`, `data-reviewed`,
    `data-problem`, `data-cell`, `data-segment-id`, `data-current-segment`, `data-block-kind`) and the inline editor's
    behaviour as it is (restyled only: it edits in the same serif, at the same size, as the text it replaces).
  - Rows still never change height with state (the Stage 2 rule; `review.spec.ts` checks it).
- Excluded rows (with "Show excluded"): one row per block and side as now, on the excluded-row colour, UI font 13
  px muted, the kind as a 10.5 px uppercase label, the text, and the Include button (`data-testid="include"`) in
  the meta column.
- E2E changes allowed: none needed for text; if a selector depended on a removed class, switch it to the data
  attribute. Don't change keys, API or behaviour.

#### Layout: toolbars and import log
Status: done
Report: 2026-10-04 — A1's top bar (progress track, Import log button with pill and a 390 px popover closed by ×/Esc/its button) and second bar (problem navigation, Next unreviewed, review group, corrections with new Edit/Join actions, Undo/Redo icons), `BeadActions` split into `group` review/corrections, status message in new `BookStatus.vue` via `statusKey`; fonts latin subset only (latin-ext dropped: its per-subset files have no unicode-range and load late, a 0.5 s full relayout); new `e2e/book-layout.spec.ts`; e2e text changes as listed plus the import-log button text (`Import log 1`); pytest 391 passed, e2e 34 passed, type-check and build clean; 16 font files; screenshot `scratchpad/layout-bars-1366.png`; 20 ArrowDown on 10,000 beads 1.17–1.30 s alone (HEAD 1.22–1.39 s).
Verified (Pauli, 2026-10-04): Done when holds (commit fd12249). Both deviations accepted: latin-ext dropped on
measured evidence (latin covers French and Italian; rarer letters fall back to a system font, acceptable; recorded
as render rule 3); the import-log button text follows the design. Measured from the screenshot, the second bar has
~270 px free at 1366 between "Exclude" and Undo; "Up to here" and "More" need ~200: tight, so the run and range
tasks carry a fallback.
**Done when:** `npm run type-check` and `npm run test:e2e` pass (with the text changes listed below); a new e2e
test at viewport 1366 × 768 checks that neither bar overflows (`scrollWidth <= clientWidth`) and that the bars are
40 and 38 px high; the `Report:` names a screenshot at 1366 × 768 (scratchpad) with the import log open, the
font file count in `tradurre/static/assets` (expected about 20), and the 10,000-bead "20 ArrowDown" time (not
worse than the ~1.2–1.45 s of the previous task).

The header becomes A1's two bars.
- **Top bar** (40 px, ground): "← Library" link to `/`; a 1 px separator; the title (`data-testid="book-title"`,
  13.5 px 600); spacer; "Show excluded" and "Highlight multi-segment" checkboxes (same testids); separator;
  progress `Reviewed {r} / {n}` (`data-testid="book-progress"`) with an 84 × 4 px track filled to r/n; separator;
  "Import log" button (warning triangle icon and a count pill when there are warnings; `data-testid="import-log"`).
- **Second bar** (38 px, second-bar colour), groups separated by 1 px rules:
  - navigation: previous-problem icon button (`aria-label="Previous problem"`, title "Previous problem (Shift+P)"),
    `{n} problem(s)` (`data-testid="problem-count"`, "1 problem", "7 problems"), next-problem icon button
    (`data-testid="next-problem"`, title "Next problem (P)"), "Next unreviewed" with a `N` chip;
  - review: "Reviewed"/"Unreviewed" with an `R` chip (today's toggle);
  - corrections (`BeadActions.vue`, `data-testid="bead-actions"`, each button keeps its `data-action`): "To
    previous" `Alt+↑`, "To next" `Alt+↓`, "Merge" `M`, "Split" `S`, "Edit" `Enter` (new action `edit`, starts the
    inline editor), "Join" `J` (new action `join`, joins with the next segment), "Exclude" `X`;
  - spacer; Undo and Redo as icon buttons (`aria-label`, titles with the keys, testids `undo`/`redo`).
  Buttons: 28 px high, transparent, hover colour, label then key chip. Icons: inline stroke SVG, no emoji.
- **Import log** (A3, minus the invented parts): a 390 px popover under its button (`data-testid="import-log-panel"`),
  closed by its × button, by Esc and by clicking the button again; "Warnings · {n}" and the list
  (`data-testid="import-warning"`), "Imported {date} with Tradurre {version}", and the stats JSON in a small mono
  `<pre data-testid="import-stats">` (as today).
- E2E text changes: `book-progress` `reviewed x / y` → `Reviewed x / y`; `problem-count` `problems n` → `{n}
  problem(s)`. Nothing else.
- Leave room in the review group for "Up to here" (next task) and after the corrections for "More" (the range task).
- Render rule (Stage 4 "Decisions carried in"): the bars' parts that change on a move (the review toggle's label,
  disabled states) stay inside `BeadActions.vue` or another injecting child, never in `BookView`'s template. The
  status message moves out too: `BookView` provides a `status` ref (new key in `selection.ts`, or a second
  `InjectionKey` there) that `say()` writes, and a new `BookStatus.vue` shows it in the bottom bar's
  size-contained box (`data-testid="status"` unchanged).
- Fonts: import only the `latin` and `latin-ext` subsets (`@fontsource/<family>/latin-400.css`,
  `latin-ext-400.css`, and so on for each weight already imported), not the all-subset files: French and Italian
  need nothing else, and the wheel loses ~70 files.

#### Layout: shortcuts panel
Status: done
Report: 2026-10-04 — `keys.ts` (`SHORTCUTS`, 22 entries, `KeyedId`) drives BookView's plain-key map through `handlers: Record<KeyedId, …>`; new `KeysPanel.vue` (A4 modal, two columns) opened by `h` and a Keys button, closed by Esc/Close/scrim, keys ignored while open; import log date formatted; new e2e test in `book-layout.spec.ts`; pytest 391 passed, e2e 35 passed, type-check and build clean; screenshot `scratchpad/layout-keys-1366.png`; 20 ArrowDown on 10,000 beads 1.20–1.24 s alone.
Verified (Pauli, 2026-10-04): Done when holds (commit ccc7346); the panel matches A4; ~280 px left free on the
second bar at 1366.
**Done when:** `npm run type-check` and `npm run test:e2e` pass with a new test: `h` opens the panel, it lists
every entry of `SHORTCUTS`, Esc closes it, and the "Keys" button opens it too; while it is open, bead keys do
nothing.

- New `frontend/src/keys.ts`: `interface Shortcut { id: string; group: 'Move around' | 'Review' | 'Corrections' |
  'Editing a sentence' | 'History'; label: string; display: string[]; key?: string }` and `SHORTCUTS = [...] as
  const satisfies readonly Shortcut[]`, with every key the book screen handles (A4's list, plus the correction
  keys), one entry per `key`: e.g. "Previous bead" `↑` (`ArrowUp`) and "Next bead" `↓` (`ArrowDown`) are two
  entries; "Next / previous sentence" `Tab`, `Shift+Tab` is one entry (`key: 'Tab'`, its handler reads
  `event.shiftKey`). `key` is the `event.key` matched by the plain-key handler (letters, Shift+letters as upper
  case, arrows, Tab, Enter). Entries for Alt/Ctrl combinations and for keys inside the editor (Esc, Ctrl+Enter,
  Enter to save) have no `key` and stay handled where they are now.
- Export `type KeyedId = Extract<(typeof SHORTCUTS)[number], { key: string }>['id']`. `BookView.vue` builds its
  plain-key `actions` map from the entries with a `key` and a `handlers: Record<KeyedId, (event: KeyboardEvent) =>
  void>`, so the compiler refuses a keyed shortcut without a handler (and a handler without a shortcut).
- While the panel is open, `onKey` handles only Esc (closes it; it takes precedence over closing the import log)
  and ignores every other key, Ctrl+Z/Y included.
- The panel (A4): a modal dialog (`role="dialog"`, `aria-labelledby`, `data-testid="keys-panel"`) on a scrim,
  "Keyboard shortcuts", "Open this list any time with H or the Keys button.", Close (Esc); groups in two columns,
  each row the label and its key chips. Opened by `h` and by a "Keys" button with an `H` chip at the right end of
  the top bar (`data-testid="keys"`); closed by Esc, Close or a click on the scrim.
- `h` is in `SHORTCUTS` as "Show this list", the last entry of Move around.
- Small fix from the previous task: the import log shows its date formatted, `Imported 4 Oct 2026, 13:02 with
  Tradurre 0.1.0` (`new Date(created_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })`),
  not the raw ISO timestamp.

### Reviewed runs and "up to here"
SPEC §3.3 "Reviewed marks": set or clear the mark on one bead, on a selected run of beads, and on every bead from
the top of the book to the current one. The skim review is gone from SPEC, so its code goes too. Split in two
(Pauli, 2026-10-04): the backend removal first, then the screen.

#### Remove skim
Status: done
Report: 2026-10-04 — `skim` gone from `set_reviewed`, `BookReviewedRequest`, the API and `client.ts`; deleted the four named skim tests plus `test_review_mark_stops_coalescing` (skim-only too), the roundtrip's skim draw; history test kind renamed `"skim"` → `"streak"`; new `test_reviewed_run_is_one_undo`, `test_reviewed_ignores_an_old_skim_field`; pytest 388 passed (391 − 5 + 2), e2e 35 passed, type-check and build clean; `grep skim` matches only that compatibility test, which must send the field.
Verified (Pauli, 2026-10-04): holds (commit dd4a9a8; pytest 388 passed here). The Done when's grep contradicted
the required compatibility test and the "leave `test_domain_history.py`" instruction: my wording, not Braun's
error; the rename to `"streak"` and the extra skim-only test deletion are accepted.
**Done when:** `uv run pytest` passes (skim tests removed, new ones below); `npm run type-check` and `npm run
test:e2e` pass unchanged; `grep -rn skim tradurre frontend/src tests` finds nothing.

- `skim` parameter of `domain/beads.py:set_reviewed` (and the `skim_review` operation kind),
  `BookReviewedRequest.skim` (`models.py`), its use in `api/books.py:reviewed` and in `client.ts`
  (`setReviewed` sends `{bead_ids, reviewed}`). Delete `test_skim_marks_coalesce`, `test_skim_unmark_is_an_error`
  (`tests/test_domain_beads.py`), `test_skim_marks_coalesce_into_one_undo`, `test_skim_unmark_is_400`
  (`tests/test_books_corrections_api.py`), and the skim branch of `tests/test_domain_roundtrip.py` (drop the
  `skim` draw and the third argument; removing that `rng.random()` call changes the random sequences the round
  trip explores, which is expected; if a seed then fails, that is a real bug: stop and report it). Keep the
  generic `coalesce` mechanism of `history.py` and its tests (`tests/test_domain_history.py` uses its own kind
  names; leave it).
- New tests in `tests/test_books_corrections_api.py`: marking 3 beads in one request is one undo step (one undo
  clears all 3); a request that still sends `"skim": true` is accepted with the field ignored (Pydantic's default
  for extra fields; add no code).
- Stored `skim_review` operations: none exist outside tests (no user data, see "Current state"); no migration.

#### Runs and "up to here" in the book screen
Status: done
Report: 2026-10-04 — run state in `BookView` (`runAnchorId`, `inRun` by difference, `runBounds`; `select(…, extend)` and `correct(…, keepRun)` handle clearing), Shift+↑/↓ and Shift+click, `r` on a run, `R` and the "Up to here" button, run style via an always-present gutter border, run summary in `BookStatus`, three Review entries in `SHORTCUTS`; 4 new e2e tests in `review.spec.ts`; e2e 39 passed (no chip fallback needed at 1366), pytest 388 passed, type-check clean; screenshot `scratchpad/run-1366.png`; 20 ArrowDown on 10,000 beads 1.08–1.15 s alone.
Verified (Pauli, 2026-10-04): Done when holds (commit f435e9b; pytest 388 here; screenshot checked: run tint, 3 px
bar, bottom-bar summary, ~150 px left free on the second bar at 1366). Three defects found in review, fixed by
"Run and key fixes" below.
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes with the new tests in
`frontend/e2e/review.spec.ts` and `e2e/book-layout.spec.ts` still passing at 1366; `uv run pytest` unchanged; the
10,000-bead "20 ArrowDown" time not worse than ~1.2–1.3 s alone; the `Report:` names a screenshot at 1366 × 768
(scratchpad) with a 3-bead run selected.

- **State** (`BookView.vue`, `selection.ts`): `runAnchorId: Ref<number | null>` and `inRun:
  shallowReactive<Record<number, true>>`, the beads from the anchor to the current bead (both included), updated
  by difference like `currentRow` (Stage 2 scale rule: never a per-row computed over indices). `Selection` gains
  `inRun` and `runBounds: Readonly<Ref<{ first: number; last: number; size: number } | null>>` (1-based bead
  numbers), for the rows and the bottom bar. A run exists when the anchor is set and differs from the current bead.
- **Making a run:** `Shift+↓`/`Shift+↑` (handled in `onKey` before the plain-key map, like Alt+arrows) set the
  anchor to the current bead if there is none, then move. `Shift+click` on a row does the same towards the clicked
  bead (`BeadRow`'s `select` emit gains a fourth argument `extend: boolean`, the click's `shiftKey`; segment clicks
  pass it too).
- **Clearing it:** any change of current bead without Shift (arrows, `n`, `p`/`P`, a plain click), Esc (after the
  shortcuts panel and the import log in precedence), any correction other than `r`, and undo/redo. Changing side
  or sentence inside the current bead (←, →, Tab) keeps it.
- **`r` with a run:** if any bead in the run is unreviewed, mark all of them reviewed, else clear all; one request
  (`setReviewed(ids, flag)`), one undo; the run stays selected. Without a run, `r` is as now.
- **`R`** (`event.key === 'R'`): mark every bead from the first to the current one reviewed (one request with the
  ids of the unreviewed ones among them; none → `say('Already reviewed up to here')`); then `say('Reviewed up to
  here (N beads)')`, N the beads newly marked. It ignores and keeps the run. Button "Up to here" with a `Shift+R`
  chip in the second bar's review group, after "Reviewed" (`data-testid="reviewed-up-to-here"`). If the second
  bar then overflows at 1366, hide the key chips of the corrections group below 1440 px (`max-[1439px]:hidden` on
  their `<kbd>`), and nothing else.
- **Style (A1), paint-only (render rule 2):** run rows get `data-in-run="true"`, the run background, and a 3 px
  accent bar at their left edge made by recolouring a 3 px left border that every row's gutter cell always has
  (transparent otherwise), not by adding a border or shadow. The current bead's own styles stay on top.
- **Bottom bar:** while a run exists, `BookStatus.vue` shows `{size} beads selected ({first}–{last}). R marks them
  all reviewed.` instead of the status message (it injects `runBounds`; `BookView`'s template reads neither).
- **`SHORTCUTS`:** Review group gains "Mark everything up to here reviewed" `Shift+R` (`key: 'R'`, handler
  required by `KeyedId`), "Extend the selection" `Shift+↑`, `Shift+↓` and "Select up to a bead" `Shift+click`
  (no `key`); Esc is not listed as a shortcut: it only closes things.
- **Tests** (`review.spec.ts`, 3-bead book of that spec): Shift+↓ twice then `r` marks 3 beads, `data-in-run` on
  all 3, the bottom bar says `3 beads selected (1–3)…`, and Ctrl+Z clears all 3 marks (one undo) and the run; a
  run with mixed marks → `r` marks all; Shift+click from bead 1 on bead 3 selects 3; a plain ↓ and Esc each clear
  the run; `R` on the second bead marks beads 1–2 and leaves bead 3, and `R` again says "Already reviewed up to
  here".

#### Run and key fixes
Status: done
Report: 2026-10-04 — letter keys looked up by Shift, not Caps Lock (`BookView.onKey`); the Reviewed/Unreviewed label follows the run via `runBounds` (`BeadActions`); Shift+mousedown on text cells (not the editor) prevents the native selection (`BeadRow`); 3 new e2e tests in `review.spec.ts`, each failing on the old code (the button test runs Shift+↑ from bead 2 so the current bead is the reviewed one, and the selection test plain-clicks bead 1 first to leave a caret: as worded, both passed on the old code); `press('R')` sends no Shift, no dispatch fallback needed; e2e 42 passed, pytest 388 passed, type-check clean.
Verified (Pauli, 2026-10-04): Done when holds (commit 1e9f12c). Both test changes accepted: my scenarios were
non-discriminating; the fail-before check is now a convention (top of this file). Left over: the bottom bar's run
summary still says "R marks them all reviewed" when all are reviewed and `r` would clear them; fixed in "Range
exclude/include".
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes with the three new tests below in
`frontend/e2e/review.spec.ts`, all earlier tests unchanged; `uv run pytest` unchanged.

Found in review of the task above (Pauli, 2026-10-04):
- **Caps Lock turns `r` into `R`** (a bulk write over the whole book up to here) and `p` into `P`: `onKey` looks
  up `event.key` (`BookView.vue`, `actions.get(event.key)`), which Caps Lock upper-cases without Shift. Fix: for a
  one-character letter key, look up `event.shiftKey ? key.toUpperCase() : key.toLowerCase()`; other keys (Enter,
  Tab, arrows) as now. Shift decides, Caps Lock never does. `SHORTCUTS` doesn't change.
- **The "Reviewed"/"Unreviewed" button ignores the run:** its label (`BeadActions.vue`) follows the current bead
  only, while `r` on a run marks all if any is unreviewed. With a run (`selection.runBounds` set), the label is
  "Reviewed" if any bead of `book.beads.slice(first - 1, last)` is unreviewed, else "Unreviewed". Read
  `runBounds`, not `inRun` key by key (one dependency, not one per bead).
- **Shift+click also selects page text** (native selection from the caret to the click). In `BeadRow.vue`, the
  text cells get a `mousedown` handler that calls `preventDefault()` when `event.shiftKey` and the target is not
  a `textarea` (the segment editor keeps native Shift+click selection). The `click` still fires, so selection
  logic doesn't change.
- Tests (`review.spec.ts`, its 3-bead book): with Caps Lock simulated by `page.keyboard.press('R')` *without*
  Shift (Playwright sends `key: 'R'`, `shiftKey: false`) on bead 2, only bead 2 becomes reviewed (beads 1 and 3
  stay `false`); a run of beads 1–2 with bead 1 reviewed shows the button `Reviewed`, and after `r` it shows
  `Unreviewed`; after a Shift+click from bead 1 on bead 3, `window.getSelection()?.toString()` is `''`.
  If `press('R')` turns out to send `shiftKey: true` in this Playwright version, dispatch the event instead
  (`page.dispatchEvent('body', 'keydown', { key: 'R', shiftKey: false })` or the equivalent on `window`), and say
  so in the Report.
- Nothing else changes: no new keys, no style changes, the render rules hold (`BookView`'s template reads
  nothing new).

### Range exclude/include
Status: done
Report: 2026-10-04 — `blocks.py` bodies factored into `_exclude`/`_include`, new `exclude_range`/`include_range` (shared `_range_blocks`); `POST /blocks/exclude-range` and `/include-range` with `BookRangeRequest`; `client.ts` `excludeRange`/`includeRange`; "More" menu in the second bar (Esc, click outside, item; toggles against the import log; Esc order panel > import log > More > run); `BookStatus` says "R clears them all." when the run is all reviewed (`book` added to `Selection`; its test fails on the old code); 6 domain tests, 2 API tests, 3 e2e tests; pytest 396 passed, e2e 45 passed (book-layout at 1366 unchanged), type-check clean. "Nothing to exclude" is unreachable (a bead's own block is never excluded), so untested; the open import log covers the More button, so that toggle's test dispatches the click.
Verified (Pauli, 2026-10-04): Done when holds (commit e52323b; pytest 396 here). Both deviations accepted. The
overlap is real: the import log (top bar, right-aligned, 390 px) hangs over the second bar's right half and closes
only by ×/Esc/its button; it gets click-outside closing in "Original text in the book screen". Range include
placing restored blocks as one-sided beads ahead of a target-only bead is `include_block`'s rule, as specified;
"Re-align range" is the repair.
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
- `BookView.vue`: the **"More" menu** of A1, after the corrections group of the second bar ("More ▾",
  `data-testid="more"`, `aria-expanded`): a 310 px popover, heading "Exclude or include in bulk" (10.5 px
  uppercase faint), four items "Exclude from the start up to here", "Include from the start up to here", "Exclude
  from here to the end", "Include from here to the end" (`data-testid="exclude-to-start"`, `include-to-start`,
  `exclude-to-end`, `include-to-end`), 30 px rows; closed by Esc, a click outside or choosing an item. No keys.
  Esc precedence in `onKey`: shortcuts panel, import log, More menu, selected run. Opening "More" closes the
  import log and vice versa. Its open state is a `BookView` ref like `showImportLog` (it changes on clicks only, so
  the render rule allows it in the template).
  `e2e/book-layout.spec.ts` must still pass at 1366; if "More" makes the second bar overflow, apply the chip
  fallback of "Reviewed runs" (if not applied yet), and nothing else.
  They act on the current bead and side; after
  success `say('Excluded N blocks (Ctrl+Z to undo)')` / `Included N blocks`, N = the difference in the book's
  excluded-block count.
- Tests (`tests/test_domain_blocks.py`, `tests/test_books_corrections_api.py`):
  exclude to start / to end take the right blocks and leave invariants I1–I5 holding (`tradurre.domain.invariants.check_project` returns no errors);
  one undo restores everything; a straddling block goes whole; include to start skips a `page_number` block and
  restores a `front_matter` one; the error cases. `review.spec.ts`: "Exclude from the start up to here" on the second bead, source side,
  excludes the current bead's own block too ("up to here" is inclusive): the source texts of beads 1 and 2 leave
  the list, "Show excluded" shows them as two excluded rows, Ctrl+Z brings both back in one step.
- Don't change the single-block exclude/include behaviour or keys.
- Left over from "Run and key fixes": `BookStatus.vue`'s run summary ends "R clears them all." instead of "R marks
  them all reviewed." when every bead of the run is reviewed (the same rule as the button's `marks` in
  `BeadActions.vue`: compute it from `runBounds` and a slice of the beads, which `BookStatus` gets by injection: add
  `book: Readonly<Ref<Book | null>>` to `Selection` in `selection.ts`, provided by `BookView`). Test in
  `review.spec.ts`: a run of 2 marked with `r`, then the bar says `2 beads selected (1–2). R clears them all.`;
  it must fail before the change.

### Original text and revert
SPEC §2: "The original extracted text is kept, so the translator can always compare or revert." `original_text`
is stored (`db.py`, segments) and kept consistent by split and join (`domain/segments.py`: an unedited segment
stays equal to its original through both), but the API never sends it. A2 of the design: edited sentences get a
dotted underline, their original shows on demand in a popover, with "Restore original". **No highlighting of
what changed** (user, 2026-10-04: it needs a diff/version history, out of scope): the original is shown whole.
"Edited" means `text != original_text`, nothing else.

#### Original text: API and restore
Status: done
Report: 2026-10-04 — `BookSegment.original` (null unless edited) filled by `_read_book`; `segments.restore_original` (kind `restore_original`, the two refusals); `POST /segments/{id}/restore`; `client.ts` `original` and `restoreOriginal`; 2 domain tests (the empty-original case made for real: edit, then a split whose cut maps to the end of the original), 1 API test; pytest 399 passed, e2e 45 passed, type-check clean.
Verified (Pauli, 2026-10-04): Done when holds (commit 1d0d3fe; pytest 399 here). `reconcile` in `BookView.vue`
compares beads by JSON, so `original` changes re-render their row with no further work.
**Done when:** `uv run pytest` passes with the new tests below; `npm run type-check` passes; `npm run test:e2e`
passes unchanged.

- `models.py`: `BookSegment` gains `original: str | None`, the extracted text **only when it differs** from
  `text`, else `None` (a 5,000-bead book must not carry every sentence twice). `api/books.py:_read_book` selects
  `s.original_text` and fills it. Excluded blocks' segments don't change.
- `domain/segments.py`: `restore_original(conn, project_id, segment_id) -> int`: sets `text = original_text` in one
  `Recorder`, recorded as `restore_original` (one undo). DomainError "The sentence is not edited" when they are
  equal; "The original of this sentence is empty" when `original_text.strip()` is empty (possible after a split
  of an edited segment maps the cut to the end of the original). `original_text` itself never changes.
- `api/books.py`: `POST /books/{id}/segments/{segment_id}/restore` through `_correct`. `client.ts`:
  `BookSegment.original: string | null`, `booksApi.restoreOriginal(id, segmentId)`.
- Tests: `tests/test_domain_segments.py` (or the module holding `edit_text`'s tests): edit then restore gives the
  original back and one undo returns the edit; the two refusals change nothing and record no operation.
  `tests/test_books_corrections_api.py`: a fresh book has `original: null` everywhere; after an edit that segment
  has `original` = the old text and the others stay `null`; `restore` → `null` again; restore of an unedited
  segment is 409.

#### Original text in the book screen
Status: done
Report: 2026-10-04 — dotted underline and `data-edited` on edited spans (`BeadRow`); new `OriginalPopover.vue` (state by `originalKey` injection, fixed, under or above the span, empty-original message, Restore disabled for it); key `o` in `SHORTCUTS`; "Text" heading and "Restore the original sentence" in More; Esc order panel > import log > More > popover > run, the three mutually exclusive; import log closes on a click outside; 3 e2e tests in `book-corrections.spec.ts` + a click-outside step in `book-layout.spec.ts`, all 4 failing on the old code; e2e 48 passed, pytest 399 passed, type-check clean; 20 ArrowDown on 10,000 beads 1.09–1.18 s alone.
Verified (Pauli, 2026-10-04): Done when holds (commit 65bd5a9; pytest 399 here). Braun's two notes become part of
"Re-align in the book screen": the popover stays put while the list scrolls (it closes on scroll there), and the
open More menu reads the current bead in `BookView`'s template (render rule 1; the menu moves to its own
component there, as the re-align item needs the run too).
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes with the new tests below in
`frontend/e2e/book-corrections.spec.ts` (each failing before the change, see Conventions) and
`e2e/book-layout.spec.ts` still passing at 1366; `uv run pytest` unchanged; 20 ArrowDown on 10,000 beads not
worse than ~1.2–1.3 s alone.

- **Mark** (`BeadRow.vue`): a segment span with `seg.original !== null` gets `data-edited="true"` and a dotted
  underline (`underline decoration-dotted decoration-muted underline-offset-[3px]`), drawn as text decoration, not
  a border (the 2 px bottom border stays the current-segment marker). It changes only when the bead's data
  changes, never on a move.
- **Popover** (A2): new `frontend/src/components/OriginalPopover.vue`, rendered by `BookView` and reading its
  state by injection (render rule 1: `BookView`'s template must not read it). State: `showOriginal:
  Ref<boolean>` in `BookView`, provided with a new `originalKey` in `selection.ts`. When open and the current
  segment is edited, the popover is `position: fixed`, 360 px wide, placed under the current segment's span
  (`document.querySelector('[data-segment-id="…"]').getBoundingClientRect()`, flipped above it if it would leave
  the viewport), white, `border-bar-rule`, rounded, shadow, `data-testid="original-popover"`. Content: heading
  "Original" (10.5 px uppercase faint), the original in `font-text` 15 px, then a "Restore original" button
  (`data-testid="restore-original"`) and a close ×. It closes on Esc, on ×, after a restore, and whenever the
  current segment changes (a `watch` on `currentSegmentId` in `BookView`).
- **Key `o`** (agreed by the user, 2026-10-04; `SHORTCUTS`, group "Corrections", label "Show the original sentence", `display: ['O']`): toggles
  the popover for the current segment; on an unedited one, `say('This sentence is not edited')` and nothing
  opens. **Restore** has no key: the popover's button and a "More" menu item "Restore the original sentence"
  (`data-testid="restore-original-more"`, under a second heading "Text" after the four bulk items, disabled
  unless the current segment is edited). Both call `correct(… restoreOriginal …)` and then `say('Original
  restored (Ctrl+Z to undo)')`.
- **Empty original** (a split of an edited sentence can map the cut to the end of the original, leaving one part
  with `original === ''`): the popover shows, in place of the text, "The original of this part is empty: it was
  split after an edit." (italic, muted), and both restore controls are disabled for it.
- **Esc precedence** in `onKey`: shortcuts panel, import log, More, original popover, run. The popover, the
  import log and More are mutually exclusive: opening one closes the others.
- **Import log click-outside** (left over from "Range exclude/include"): a mousedown outside the import log's
  button and panel closes it, in the same `onWindowMouseDown` as More.
- Tests (`book-corrections.spec.ts`, its own book): Enter, type a change, Enter → the span has
  `data-edited="true"`, other spans don't; `o` opens the popover showing the old text; "Restore original" puts the
  old text back, removes `data-edited`, closes the popover, and Ctrl+Z brings the edit back; `o` on an unedited
  sentence shows "This sentence is not edited" and no popover; with the popover open, ↓ closes it; the More item
  restores too; an empty original, built through the API before opening the page (edit a sentence "S." to "S.
  Encore.", then `POST segments/{id}/split` with `offset` = `len("S. ")`: the new "Encore." segment's original is
  `''`, as in `test_restore_refused`), shows the empty message and a disabled "Restore original". `book-layout.spec.ts`: with the import log open, a click on the list closes it.
- Don't change the editing flow (Enter / Ctrl+Enter / Esc in the editor) or any existing key.

### Re-align range
SPEC §3.3: "select a stretch between two trusted beads and re-run the local aligner on just that stretch". The
stretch is the selected run (or the current bead alone, to re-split one many-to-many bead). Decided (user,
2026-10-04): every bead in the stretch is replaced, reviewed or not, and the new beads start **unreviewed** (SPEC
§3.3: "Beads produced by an aligner start unreviewed"); one operation, so one undo restores the old beads and
their marks. The aligner is the import's: `services/align.py:align` (its length ratio is computed from the texts
it is given, i.e. from the stretch, which is right between two trusted beads).

#### Re-align: service and API
Status: done
Report: 2026-10-04 — new `services/realign.py` (`_run`, `_segments`, `align.align`, `replace_beads(kind="realign")`); `BookRealignRequest`, `POST /beads/realign`, `booksApi.realign`; `tests/test_realign.py` (stretch equals the aligner's output, inside reviewed mark replaced, outside kept, invariants, one undo = exact snapshot; three refusals record nothing) and an API test on `gap`; all fail on the old code (import error / 404); pytest 402 passed, e2e 48 passed, type-check clean.
Verified (Pauli, 2026-10-04): Done when holds (commit d2ab8a4; pytest 402 here). Braun's note (an unchanged
re-align still drops the marks) went to the user, who agreed to keep them: "Re-align: nothing changed" below.
**Done when:** `uv run pytest` passes with the new tests below (each failing before the change); `npm run
type-check` passes; `npm run test:e2e` passes unchanged.

- New `tradurre/services/realign.py`: `realign(conn, project_id, first: int, last: int) -> list[int]`. It reads
  the run's beads in order (`domain/replace.py:_run`), their segment ids and texts per side in document order
  (`domain/beads.py:_segments`, then the texts), calls `align.align(source_texts, target_texts)`, maps the
  returned indices back to segment ids as `NewBead(source_ids, target_ids, confidence, "length")`, and calls
  `replace_beads(conn, project_id, first, last, new_beads, kind="realign")`. Returns the new bead ids. Errors
  come from `replace_beads` (`_run`): another project's bead, first after last. Callers own the transaction.
  The domain layer doesn't import services; this module may import the domain.
- `models.py`: `BookRealignRequest(first_bead_id: int, last_bead_id: int)`. `api/books.py`: `POST
  /books/{id}/beads/realign` through `_correct`. `client.ts`: `booksApi.realign(id, firstBeadId, lastBeadId)`.
- Tests, new `tests/test_realign.py` on a synthetic project (as `tests/test_domain_blocks.py` builds one): a
  3-bead stretch laid out wrongly by hand (e.g. a 1:0 bead followed by a 1:2) re-aligns to the aligner's own
  output for those texts (compare with `align.align` called directly on them), every new bead has `method
  "length"` and `reviewed 0`, a reviewed bead inside the stretch is replaced and one outside keeps its mark,
  `check_project` is `[]`, and one `undo` restores the exact snapshot (beads and marks); first after last and a
  bead of another project are refused with nothing recorded. `tests/test_books_corrections_api.py`: on the `gap`
  fixture, `beads/realign` over B..D returns 200, `/check` is `[]`, the beads outside the stretch are unchanged,
  and `undo` returns the `gap` layout.

#### Re-align in the book screen
Status: done
Report: 2026-10-04 — More menu moved to `MoreMenu.vue` (injected selection; `BookView`'s template reads no current-bead state now); "Alignment" heading with "Re-align the selection" (run, or the current bead), status `Re-aligned N beads into M (Ctrl+Z to undo)`, run cleared, first new bead current; list `@scroll` closes the original popover; 2 e2e tests in `review.spec.ts`, both failing on the old code; e2e 50 passed, pytest 402 passed, type-check clean; 20 ArrowDown on 10,000 beads 1.15–1.19 s with More closed, 1.10–1.18 s with it open.
Verified (Pauli, 2026-10-04): Done when holds (commit 7d1aab1; pytest 402 here); `BookView`'s template no longer
reads current-bead state. Braun's second note checked: `align.align` on that test's stretch (B2..B3) returns the
same two beads, so the follow-up below must rework that test.
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes with the new tests below (each failing
before the change) and `e2e/book-layout.spec.ts` still passing at 1366; `uv run pytest` unchanged; 20 ArrowDown
on 10,000 beads not worse than ~1.2–1.3 s alone, and also measured once with the More menu open (report both).

- **More as a component** (render rule 1): move the menu's button and popover out of `BookView.vue` into
  `frontend/src/components/MoreMenu.vue`. It injects the selection (and the book through it) for its disabled
  states, and emits `bulk(action, to)`, `restore`, `realign`; `BookView` keeps the handlers and the open state
  (`showMore`, still a `BookView` ref for the mutual exclusion and Esc order, passed as a prop, with a `toggle`
  emit). After the move `BookView`'s template reads nothing that changes on a move, menu open or not.
- **Item:** under a third heading "Alignment", "Re-align the selection" (`data-testid="realign"`), enabled when
  there is a current bead; it re-aligns the selected run, or the current bead if there is no run. After success:
  `say('Re-aligned N beads into M (Ctrl+Z to undo)')` (N the stretch's size, M the new count: N plus the
  difference in the book's bead count), the run is cleared and the current bead is the first new one (the
  `selectIndex` of `correct`). No key.
- **Popover and scrolling:** the original popover closes when the bead list scrolls (`@scroll` on the list
  container sets `showOriginal = false`; a handler binding, not a read, so render rule 1 holds).
- Tests (`review.spec.ts`, its 3-bead book, whose import gives B3 a 2:1 below 0.5): a run of B2..B3 → "Re-align
  the selection" → `/check` (API) is `[]`, every bead of the stretch is unreviewed, the status starts
  `Re-aligned 2 beads into`, and Ctrl+Z restores the previous rows and marks (mark B2 reviewed first). With the
  original popover open (edit a sentence through the API first), a mouse-wheel scroll of the list closes it.
- `SHORTCUTS` and existing keys don't change.

#### Re-align: nothing changed
Status: done
Report: 2026-10-04 — `realign` compares the aligner's `(source, target)` groups with the stretch's and raises "The aligner gives the same beads; nothing changed" when equal; new domain test (second re-align refused, marks kept, one operation) and API test (409 on the imported book), the existing e2e re-align test first moves "Paul partit." into B2 through the API, new e2e test for the unchanged case; the three new tests fail on the old code (the reworked one passes either way, as intended); pytest 404 passed, e2e 51 passed, type-check clean.
Verified (Pauli, 2026-10-04): Done when holds (commit e4e8f85; pytest 404 here). Braun's note (a refused
re-align still clears the run) is general: `correct` clears the run before the request, so every refused
correction loses the selection although nothing changed. Fixed in "Cut/copy/paste between rows" (clear only on
success).
**Done when:** `uv run pytest` passes with the new tests below; `npm run type-check` passes; `npm run test:e2e`
passes with the reworked and new tests in `review.spec.ts`; each new test fails on the code before the change.

Agreed (user, 2026-10-04): "if realign does not change anything, don't un-review the already reviewed beads".
- `services/realign.py:realign`: before `replace_beads`, compare the aligner's beads with the stretch's current
  beads as lists of `(source ids, target ids)`. If equal, raise `DomainError("The aligner gives the same beads;
  nothing changed")`: no write, nothing recorded, marks, confidences and methods untouched. Any difference keeps
  today's behaviour (every bead replaced, all unreviewed).
- The screen needs no code change: a refused correction already shows the server's message in the status line
  (`correct` in `BookView.vue`); the run is cleared as for any correction.
- Tests: `tests/test_realign.py`: re-align a stretch already in the aligner's layout (e.g. re-align A..C twice:
  the second call) → DomainError, snapshot unchanged, one operation only (the first), reviewed marks kept.
  `tests/test_books_corrections_api.py`: the same over the API → 409 with that message.
  `review.spec.ts`: the import of that spec's book is already the aligner's layout for B2..B3 (`align.align`
  returns the same two beads), so the existing "Re-align the selection…" test must first break it through the
  API before opening the page: `POST beads/{B3}/move {"side": "source", "to": "previous"}` (B2 becomes "Il
  pleuvait. Paul partit." | "Paul partì."), then mark B2 reviewed as now and expect the same outcome. New test: on
  the untouched book, mark B2, select B2..B3, "Re-align the selection" → status `The aligner gives the same
  beads; nothing changed`, B2 still reviewed, rows unchanged.

### Cut/copy/paste between rows
Status: done
Report: 2026-10-04 — Ctrl+C/X/V outside the editor in `BookView.vue` (`cut` + `cutRow` in `Selection`, dashed accent border and `data-cut` in `BeadRow.vue`, Esc before the run, cleared by any successful correction); `correct` clears run and cut only after success, so `BookStatus.vue` now shows a message over the run summary and a change of the run clears the message; 3 `SHORTCUTS` entries; 5 e2e tests in `book-corrections.spec.ts`, 1 in `review.spec.ts`, all failing on the old code except the editor test (a guard, passes either way); e2e 57 passed, pytest 404 passed, type-check clean; 20 ArrowDown on 10,000 beads 1.17–1.21 s.
Verified (Pauli, 2026-10-04): Done when holds (commit 3187c9a; pytest 404, e2e 57 here). Braun's status-bar
rule is accepted: a message shows over the run summary until it expires, and a change of the run's bounds clears
it (`BookStatus.vue`, `watch(runRange)` in `BookView.vue`); without it a refusal would be invisible while the run
stays. Two follow-ups in "Cut and copy: fixes" below: clearing the cut on *every* successful correction (as this
task said) is stricter than "as usual" (SPEC §3.3), and Ctrl+C now blocks the browser's copy of selected text
outside the bead list (the import log).
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes with the new tests below (each failing
before the change); `uv run pytest` unchanged; 20 ArrowDown on 10,000 beads not worse than ~1.2–1.3 s alone.

SPEC §3.3 (agreed 2026-10-04): "cut, copy and paste, as usual. Inside the sentence editor they work on text …
Outside it they work on whole sentences …". Frontend only: the paste is the existing move
(`booksApi.move(id, beadId, side, 'previous' | 'next')`, i.e. `move_first_to_previous` / `move_last_to_next`).
- **Inside the editor** nothing changes: `onKey` already returns for text entry, so the browser's own
  cut/copy/paste act on the text, and saving is the existing text edit.
- **Ctrl+C** (outside the editor, in `onKey`'s Ctrl branch next to Ctrl+Z/Y): `navigator.clipboard.writeText` of
  the current sentence's text, then `say('Sentence copied')`; no current sentence → nothing.
- **Ctrl+X:** marks the current sentence as cut, if it is the first or the last of its side in its bead;
  otherwise `say('Only the first or last sentence of a bead can move to a neighbouring bead')` and nothing is
  marked. Nothing is written to the server and the text stays in place; the clipboard gets the text too (as
  Ctrl+C). Then `say('Sentence cut: go to the previous or next bead and press Ctrl+V (Esc cancels)')`.
  State in `BookView`: `cut: { beadId, side, segmentId } | null`, and for the rows `cutRow:
  shallowReactive<Record<number, number>>` (bead id → segment id), updated by difference like `currentRow` and
  added to `Selection` (Stage 2 scale rule: a row reads only its own key).
- **Look** (render rule 2, paint-only): the cut sentence's span gets `data-cut="true"` and its always-present
  2 px bottom border turns dashed in the accent colour (`border-dashed border-accent`); no other change.
- **Ctrl+V:** with nothing cut, `say('Nothing cut')`. With a cut sentence: if the current bead is the bead
  right before the cut one and the sentence is the first of its side there, `move(…, cutBead, side,
  'previous')`; if the current bead is the one right after and the sentence is the last, `move(…, 'next')`;
  otherwise `say('A sentence can only move to the edge of the neighbouring bead: the text order never
  changes')` and the cut stays. The side is the cut sentence's, whatever the current side. After a successful
  paste the cut is cleared, the current bead stays the one pasted into, and `say('Sentence moved (Ctrl+Z to
  undo)')`.
- **The cut is cleared** by Esc (precedence: shortcuts panel, import log, More, original popover, cut, run), by
  any successful correction (`correct`), and by undo/redo. Moving around keeps it.
- **Refusals keep the selection** (left over from "Re-align: nothing changed"): `correct` in `BookView.vue` clears
  the run (and now the cut) only after the request succeeds, not before it; a refused correction changes nothing,
  so it keeps both. Test (`review.spec.ts`): on the untouched 3-bead book, select B2..B3, "Re-align the
  selection" → the "nothing changed" message and `data-in-run` still on B2 and B3.
- `SHORTCUTS`, group "Corrections", no `key` (handled in the Ctrl branch): "Copy the sentence" `Ctrl+C`, "Cut the
  sentence" `Ctrl+X`, "Paste it into the neighbouring bead" `Ctrl+V`.
- Tests (`book-corrections.spec.ts`, its `gap` book): select "Il pleuvait." (C, alone on its source side),
  Ctrl+X → `data-cut="true"` and the status; ↑ to B, Ctrl+V → rows equal `B_MERGED` (C, left empty, is deleted
  by the move), status "Sentence moved…", no `data-cut` left; Ctrl+Z → `ORIGINAL`. Cut "Il pleuvait.", ↑ twice
  to A, Ctrl+V → the refusal message and rows unchanged; Esc clears `data-cut`. Ctrl+C on "Marie arriva." puts
  that text on the clipboard (grant `clipboard-read`/`clipboard-write` to the context; read with
  `navigator.clipboard.readText()`). The middle-sentence refusal: `m` twice on A (its source becomes "Chapitre
  un", "Marie arriva.", "Il pleuvait."), select "Marie arriva.", Ctrl+X → the refusal message, no `data-cut`. Inside the editor, select all, Ctrl+X, Ctrl+V, Enter → the text is unchanged and nothing is
  marked cut.

### Cut and copy: fixes
Status: done
Report: 2026-10-04 — `keepCut` in `correct` (the cut follows its sentence while it is first or last of its side in a bead, else dropped; `pasteSentence` clears it after a move); Ctrl+C/X left to the browser when a text selection lies outside the bead list (`list` ref); 3 e2e tests in `book-corrections.spec.ts`, all failing on the old code; e2e 60 passed, pytest 404 passed, type-check clean.
Verified (Pauli, 2026-10-04): Done when holds (commit 5028f32; pytest 404, e2e 60 here). `keepCut` scans the
beads only while a cut is pending: negligible next to the whole-book refetch.
**Done when:** `npm run type-check` passes; `npm run test:e2e` passes with the new tests below (each failing
before the change); `uv run pytest` unchanged.

SPEC §3.3: cut, copy and paste "as usual". Frontend only, `BookView.vue` (and the new tests).
- **The cut survives corrections that keep it valid.** In an editor a cut waits until it is pasted or replaced;
  here marking a bead reviewed (`r`) between Ctrl+X and Ctrl+V drops it, which is not "as usual". In `correct`,
  replace `cut.value = null` on success: after `book.value = reconcile(...)` (and before the `!beads.length`
  return), find the bead whose `cut.side` holds `cut.segmentId`; if the segment is the first or last of that side
  there, keep the cut with that bead's id (`cut.value = { ...cut, beadId }` only when the id changed), else
  `cut.value = null` (gone, excluded, or now in the middle). Undo/redo follow the same rule (they go through
  `correct`). `pasteSentence` sets `cut.value = null` itself after a successful move (the moved sentence is at an
  edge of its new bead, so the rule alone would keep it). Esc and the refusals don't change. Update `correct`'s
  comment.
- **Copy of selected text outside the bead list is the browser's.** Give the bead list's scrolling container a
  ref (`list`). In `onKey`'s Ctrl+C/X/V branch, for `c` and `x` only: if `document.getSelection()` is not collapsed
  and its `anchorNode` is not inside `list`, return **without** `preventDefault` (the browser copies the selection,
  e.g. from the import log). Inside the list, or with no selection, today's whole-sentence behaviour stays.
- Tests (`book-corrections.spec.ts`, its `gap` book): cut "Il pleuvait." (C), `r` → C is reviewed and
  `data-cut` is still on it; ↑, Ctrl+V → `B_MERGED`, no `data-cut`. Cut "Marie arriva." (B), ↑ to A, `m` → A's
  source is "Chapitre un", "Marie arriva." and `data-cut` is still on "Marie arriva."; `m` again (A takes "Il
  pleuvait." too) → no `data-cut`. Copy from the import log (grant `clipboard-read`/`clipboard-write`): open it,
  select the text of `import-stats` with a DOM range (`page.evaluate`), Ctrl+C → `navigator.clipboard.readText()`
  equals that selection's `toString()` and the status is not "Sentence copied".

### Scale check at 5,000 beads
Status: done
Report: 2026-10-04 — new e2e test "a 5,000-bead book: load, corrections and scrolling" in `book-view.spec.ts`, no app change. Alone (three runs): load 1515/1541/1535 ms, Alt+↓ 381/391/389, Ctrl+Z 299/305/304, m 191/199/195, Ctrl+Z 191/190/191 ms, scroll 0 long tasks (the wheel scrolls ~30,000 px; a 150 ms task injected through `setTimeout` is caught and fails the test, so the check is live). Blocked: in the full `npm run test:e2e` (default parallel workers, one shared backend) it fails in 3 of 3 runs: Alt+↓ 1466/1338/1375 ms, the first Ctrl+Z 466/580 ms, while the 10,000-bead tests import on the same server; with `--workers=1` all 61 pass (Alt+↓ 419 ms). Commit 80b097a first recorded this task as done with e2e 61 passed: wrong, corrected here. Decision needed: how to isolate the timing test (e.g. serial, its own project, or measured apart from the suite).
Resolved (Pauli, 2026-10-04): the measurement holds: alone, every number is well inside its bound (commit
80b097a; the scroll check was shown live by an injected 150 ms task). The failure is the test environment, not the
app: in the parallel suite the move waits behind other workers' 10,000-bead imports on the same backend (one
SQLite writer), and `--workers=1` passes all 61. The default `npm run test:e2e` is red at HEAD until "Timing tests
run last, alone" below, which is the next task.
**Done when:** the new test below passes three runs in a row (report each run's numbers); `npm run type-check`
passes; the rest of `npm run test:e2e` and `uv run pytest` unchanged.

SPEC §5 "Responsive": a 5,000-bead book opens and scrolls smoothly; a single correction is reflected in well under
a second. Stage 2's checks pass at 10,000 beads (load < 5 s, 20 ↓ < 2 s, `r` < 1.5 s) with a whole-book refetch
per correction and no virtualization; nothing yet measures structural corrections or scrolling. This task only
measures: **if a bound fails, don't optimize and don't loosen it**: stop (`blocked`) with the numbers, and
`/pauli` plans virtualization or incremental updates from them.
- New test in `frontend/e2e/book-view.spec.ts`, "a 5,000-bead book: load, corrections and scrolling", built like
  the 10,000-bead one there (`Phrase numéro k.` / `Frase numero k.`, `test.setTimeout(120_000)`), logging every
  number with `console.log` and `test.info().annotations` as that test does. Bounds:
  - load (goto → last row attached) < 3,000 ms;
  - on bead 20 (20 ↓ from the first), each step timed from the key press to its visible result, each < 500 ms:
    Alt+↓ (bead 21's source cell shows 2 sentences), Ctrl+Z (1 again), `m` (5,000 → 4,999 rows), Ctrl+Z (5,000);
  - scrolling: after load, register a `PerformanceObserver` for `longtask` in the page (`page.evaluate`, entries
    pushed to a `window` array), hover the list, 20 × `page.mouse.wheel(0, 1500)` with 50 ms between, then 200 ms
    more; the longest long task < 100 ms (none at all is fine).
- No change to app code.

### Timing tests run last, alone
Status: done
Report: 2026-10-04 — the three timing tests moved unchanged to `e2e/scale.spec.ts` (serial), project `scale` depends on `e2e` in `playwright.config.ts`, CLAUDE.md line; the 5,000-bead test also times a second Alt+↓/Ctrl+Z. Default `npm run test:e2e` 61 passed three runs in a row; 5,000-bead lines: load 1425/1392/1502 ms, Alt+↓ 404/420/420, Ctrl+Z 329/337/317, m 201/201/215, Ctrl+Z 215/201/202, Alt+↓ again 344/327/310, Ctrl+Z again 394/418/326 ms, scroll 0 long tasks; `--project=e2e` lists 58; pytest 404 passed, type-check clean.
Verified (Pauli, 2026-10-04): Done when holds (commit 8b3c3a2; pytest 404 here; `--project=e2e` lists 58, all
61). Stage 4's tasks are all done; archived after the post-stage review with the user (2026-10-04).
**Done when:** the default `npm run test:e2e` (no `--workers` flag) passes three runs in a row, 61 tests, with the
three timing tests in project `scale` (report each run's 5,000-bead line); `npm run type-check` passes; `uv run
pytest` unchanged.

Decided (Pauli, 2026-10-04): the timing tests measure the app, so nothing else may run against the shared e2e
backend while they do. Playwright projects with a dependency, not a global `workers: 1` (which would make the
whole suite ~2× slower for three tests).
- New `frontend/e2e/scale.spec.ts`: **move** (cut, not copy) the three timing tests there, bodies and bounds
  unchanged: "a 10,000-bead book loads and navigates within the limits" and "a 5,000-bead book: load, corrections
  and scrolling" from `book-view.spec.ts`, "r on a 10,000-bead book is fast" from `book-corrections.spec.ts`. Copy
  the helpers they use (`importBook` without the `gap` restore, which they never need; `current`). At the top:
  `test.describe.configure({ mode: 'serial' })`, so they run one after another in one worker.
- In the 5,000-bead test, after the first Ctrl+Z, time a **second** Alt+↓ and its Ctrl+Z the same way (same
  bound, < 500 ms each) and log them as `Alt+↓ again` / `Ctrl+Z again`: alone the first move costs ~385 ms against
  ~195 ms for `m`, and the second tells whether that is the move or a first-correction warm-up.
- `frontend/playwright.config.ts`: `projects: [{ name: 'e2e', testIgnore: /scale\.spec\.ts/ }, { name: 'scale',
  testMatch: /scale\.spec\.ts/, dependencies: ['e2e'] }]`; `use`, `webServer` and the rest stay top-level. So
  `npm run test:e2e` runs everything, the timing tests only after every other test has finished (and not at all
  if one failed: the run is red anyway); `npx playwright test --project=e2e` skips them.
- `CLAUDE.md`, the `npm run test:e2e` line: add "the timing tests (`e2e/scale.spec.ts`) run last, alone".
- No app code changes.
