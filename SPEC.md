# Tradurre — Product Specification

This document describes what Tradurre **should be**, not what it currently is.
It is the reference against which the code is reviewed and `PLAN.md` is written.
Change it deliberately, with the user's agreement; it is not a log of
implementation details.

---

## 1. Purpose

Tradurre turns **existing, unaligned literary translations** into a **reliable,
searchable parallel corpus**.

The translator owns a library of books in French and their published Italian
translations. Today those pairs are just files: knowing how a word, an idiom or
a passage was rendered means opening two PDFs and hunting. Tradurre ingests each
pair, aligns it sentence by sentence with as little manual work as possible,
lets the translator review and correct the alignment comfortably, and then makes
the whole library searchable: *"how has `désœuvrement` been translated, and in
what context?"*

### Priorities

1. **Corpus building** (now): import → align → review → search. Everything in
   this spec serves this first.
2. **Revision** (later): editing an existing translation side by side with its
   source, in a tool that is handier than Word for that job. The data model must
   not preclude it, but no work is done for it yet.
3. **Translating from scratch** (distant future): out of scope.

### User

One translator, non-technical, working on Windows. Single user, single machine.
The developer supports them.

### Scale

Dozens of books, one language pair (French → Italian). A typical book is roughly
1,000–5,000 sentences per side. Language codes are stored per project, but
nothing is tuned for pairs other than FR→IT.

### Non-goals

- Multi-user collaboration, accounts, sync, cloud hosting of the app.
- Machine translation or any generated text. Automated tools may **group, split
  and match** the translator's existing text; they never write or rewrite it.
- Scanned (image-only) PDFs, EPUB. Out of scope until asked for.
- Full typographic fidelity. Formatting (italics, emphasis) is nice to have, not
  required.

---

## 2. Core concepts

A **project** is one book: one **source edition** and one **target edition**,
plus the **alignment** between them.

### Text layer: what each edition says

Each edition is an ordered sequence of **blocks**. Each block is an ordered
sequence of **segments**.

- A **block** is a structural unit taken from the input: a paragraph, a heading,
  a footnote, a running head, a page number, front/back matter. Every block has
  a **kind**. Some kinds are **excluded** from alignment and search by default
  (running heads, page numbers, footnotes, …). Excluding never deletes: the
  translator can re-include a block, and the text is still there.
- A **segment** is (normally) a sentence: the smallest unit of alignment.
  Segmentation is automatic but correctable: the translator can split a segment
  or join two adjacent ones.
- Segment text is editable, to fix extraction errors (broken hyphenation,
  mangled glyphs, stray characters). The original extracted text is kept, so the
  translator can always compare or revert.

The two editions are **independent**: editing, splitting or joining segments on
one side never modifies the other side or the alignment's text.

### Alignment layer: which part of the source corresponds to which part of the target

The alignment is an ordered sequence of **beads**. A bead links a **contiguous
run of source segments** to a **contiguous run of target segments** (either side
may be empty):

- 1:1, 1:2, 2:1, 2:3, … — a translator merging or splitting sentences is normal,
  not an error.
- 1:0 / 0:1 — material present in only one edition (an omitted sentence, a
  translator's note, a preface).

Beads cover every non-excluded segment of both editions exactly once, in order
(alignment is monotone: no crossing). Each bead carries:

- **confidence** (0–1) and **method** (how it was produced: anchor, length,
  embedding, llm, manual);
- **review level**: the finest level (see below) at which the translator has
  seen and accepted it, or none.

Correcting the alignment means moving bead boundaries (e.g. "this target
sentence belongs to the previous bead"), merging or splitting beads. **It never
touches segment text.** Correcting text never changes the bead structure, with
one exception: joining two segments that sit in different beads also merges
those beads, so the joined sentence stays whole in one bead. Splitting a segment
keeps both parts in the bead that contained it.

### Levels: sentences, turns, paragraphs

The alignment is stored once, as beads (sentence pairs). The translator can look
at it, and review it, at three **levels**. A level is a view over the same
beads, never a second alignment, and the levels nest: a sentence is part of a
turn, a turn is part of a paragraph.

- **The source defines the structure.** A bead boundary is also a boundary at a
  coarser level when it falls at a break of the source's structure:
  - **turn**: any source sentence break, except inside a speech paragraph (a
    source paragraph that opens with a dialogue mark: a dash or a guillemet). A
    turn is therefore one narrative sentence, or a whole speech paragraph,
    always made of whole beads;
  - **paragraph**: a source paragraph break.
- A **unit** at a level is the run of beads between two of its boundaries. Units
  are derived, never stored: correcting the beads changes them automatically. A
  bead that crosses a source break (say the translator merged the last sentence
  of one paragraph with the first of the next) joins the two units.
- In a book without dialogue, turns and sentences coincide.
- The translator works at the turn level: against the translator's own reviewed
  alignment of a book, sentence beads agree only partly, because the translator
  groups sentences, while turns agree almost entirely.
- **Review marks are per level.** A bead records the finest level at which it
  was reviewed (sentence, turn, paragraph) or that it was not. A unit shows as
  reviewed when every bead in it was reviewed at that level or a finer one. So
  marking a turn reviewed does not make its sentences reviewed (the sentence
  view still shows them unreviewed), while a turn whose sentences are all
  reviewed is reviewed; likewise turns and paragraphs. A review mark from before
  levels existed counts as reviewed at the sentence level.

### History

Every change by the translator (text edit, segment split/join, block
exclude/include, bead change, review mark) is recorded as an operation that can
be **undone**, including after restarting the app. No user action can silently
destroy text.

---

## 3. Workflows

### 3.1 Import

1. The translator creates a project by choosing two files (source, target):
   born-digital **PDF**, **.docx** or **.txt** (UTF-8). Title and languages are
   pre-filled (FR→IT by default).
2. Extraction produces blocks with kinds. For PDFs it uses layout (position on
   page, font size, repetition across pages) to recognize running heads, page
   numbers and footnotes, and resolves PDF-specific damage: ligatures,
   private-use glyphs, end-of-line hyphenation, lines wrapped inside paragraphs.
3. Segmentation splits blocks into sentences, handling French and Italian
   conventions: abbreviations, dialogue dashes and guillemets, ellipses,
   quotations ending in punctuation.
4. A **baseline alignment** runs locally (no GPU, seconds per book) and the
   project opens in the review view.
5. Extraction problems the tool cannot fix are reported as **warnings attached
   to the project** and shown in the review view, never only in a log file.

### 3.2 High-quality alignment (parked)

A GPU aligner (sentence embeddings + an LLM judge, run on Colab through a
project bundle) is **parked**: the local baseline already aligns the reference
book at F1 0.994 against an alignment corrected by the developer; the
translator's own review of it (in v0.2) replaces it as the reference. It comes
back (see §5) only if a gold book scores below **0.95**.

### 3.3 Review

The translator reviews **the whole book**, guided by the tool: they jump from
one likely problem to the next, correct it, and mark what they have checked. The
review view is optimized for quick navigation and quick corrections:

- One continuous, scrollable list of beads, source left, target right, paragraph
  and heading structure visible. Performance stays smooth on a 5,000-bead book.
- **Level.** One key cycles the list between sentences, turns and paragraphs
  (see §2); each row is then a unit of that level. The default is the turn
  level. The current position stays on the unit that contains the current bead.
- Low-confidence beads and unmatched (1:0, 0:1) beads stand out visually; there
  are shortcuts to jump to the next one. At a coarser level, a unit stands out
  if any of its beads would.
- On request, beads holding more than one segment on either side are highlighted
  too, so many-to-one beads and false sentence splits are easy to spot.
- **Reviewed marks.** Reviewed marks are per level (see §2). The mark can be set
  or cleared on any single unit or on a selected run of units, and every unit
  from the top of the book to the current one can be marked reviewed at once.
  Marking a unit reviewed raises each of its beads to at least the current
  level; clearing it lowers each of its beads to the next coarser level, or to
  unreviewed at the paragraph level (clearing a turn also clears its sentences,
  but not its paragraph). Beads produced by an aligner start unreviewed; a bead
  produced by a correction inherits the mark, the weaker one winning (a merge is
  reviewed at a level only if all merged beads were; a split keeps the mark).
  Progress shows the share of units reviewed at the current level, with a
  shortcut to the next unreviewed unit.
- Keyboard-first corrections on the current bead:
  - move the first/last segment of a side to the previous/next bead;
  - cut, copy and paste, as usual. Inside the sentence editor they work on text
    (a paste is a text edit, original kept, undoable). Outside it they work on
    whole sentences: copy puts the current sentence on the clipboard; a sentence
    cut at a bead's edge and pasted at the adjacent edge of the neighbouring
    bead moves there (the same as the move above); any other paste would change
    the order of the text, and is refused;
  - merge with the next bead; split a bead at a chosen segment;
  - at a coarser level the same corrections apply to the unit's edges and are
    bead corrections: moving the first or last segment of a side to the
    neighbouring unit moves it across the bead boundary at that edge, and
    merging with the next unit merges the two beads that meet there. A unit can
    be split only at a source break that a bead crosses (which undoes such a
    merge); anywhere else the translator switches to the sentence level to
    split. There are no turn breaks of the translator's own: the sentence level
    holds those pairings;
  - split a segment at the cursor, join with the next segment;
  - edit segment text inline (plain text); text corrections and block exclusion
    work the same at every level;
  - exclude/include the current block;
  - exclude/include every block from the start of the edition up to the current
    bead, or from it to the end.
- **Re-align range**: select a stretch between two trusted beads and re-run the
  local aligner on just that stretch.
- Undo/redo with the usual shortcuts.
- Excluded blocks are hidden by default and can be revealed in place.

### 3.4 Search

The corpus is searchable across all projects, from a global search page and from
inside a project:

- One query, matched against the source side, the target side, or either.
  Matching ignores case and accents, and a word matches every word it begins
  (`désœuvr` finds `désœuvrement`, `désœuvré`), unless *Whole words* is on: then
  a word matches only itself (case and accents still ignored); a phrase in
  quotes matches those words in sequence.
- Each result is a **bead** (the matched source and target text, with the match
  highlighted), plus the book title and the position in the book. A result also
  shows the level at which it was reviewed: as a sentence, only as part of its
  turn or paragraph, or not reviewed.
- Results are grouped by book, books in library order (most recently worked on
  first), with each book's number of matches; inside a book, in reading order.
- **Context on demand:** expanding a result shows the surrounding beads; one
  click opens the project at that bead. When the result was not reviewed at the
  sentence level, it shows the whole turn as its context, with the matched pair
  highlighted.
- Excluded blocks are not searched. Beads not yet reviewed are searchable but
  marked as such.

### 3.5 Export

- **Edition export**: the (corrected) text of one side as .txt or .docx, keeping
  paragraph structure.
- **Project bundle** export/import: the text layer and alignment of one project,
  as a full backup, with the per-level review marks (an older bundle restores
  with its reviewed marks counting as sentence level).

---

## 4. Non-functional requirements

- **Python 3.14** everywhere, including Colab if the parked aligner (§5) is ever
  built (the notebook installs it with uv rather than using Colab's system
  Python).
- **Local-first.** The app runs on the translator's laptop with no network
  access needed. Data lives in a single SQLite file under `~/.tradurre/`;
  copying that file is a backup. The app also snapshots it at each start into
  `~/.tradurre/backups/`, keeping the last 10.
- **Easy install and upgrade on Windows** through the self-installing launcher;
  upgrades never lose data. Schema changes migrate the existing database
  automatically.
- **Never lose work.** Every edit is saved immediately (no "save" button) and is
  transactional: a failed request leaves the data as it was. Concurrent requests
  from the UI cannot corrupt the data.
- **Responsive.** Opening a 5,000-bead book and scrolling through it is smooth;
  a single correction is reflected in well under a second; a search across
  dozens of books returns in under a second.
- **Debuggable.** Import and alignment runs record what they did (counts,
  timings, warnings) in the project, so a bad result can be diagnosed from the
  project itself.
- **Tested.** Alignment, segmentation and extraction have regression tests on
  small fixtures committed to the repo; the API and data invariants (bead
  coverage, monotonicity, undo) have tests.

---

## 5. Later (designed for, not built)

- **Corpus export** (TMX for translation software, TSV for spreadsheets), if a
  use appears. It includes unreviewed and one-sided beads, marked as such.
- **Chapter level:** a fourth level above paragraphs, from the source's chapter
  headings.
- **Revision mode:** edit the target edition side by side with the source as a
  writing environment, with formatting (italics, emphasis) carried through
  import and export.
- **Inline formatting** in segments, preserved from .docx/PDF and exported to
  .docx.
- **Translating from scratch** with the corpus as translation memory.
- **High-quality alignment (Colab)**, parked (§3.2): the translator exports a
  project bundle; a notebook runs the GPU aligner on it and produces an
  alignment file (beads over the bundle's segments, with confidence and method);
  loading it replaces only unreviewed beads, never text, and is refused if the
  text changed since the export.
