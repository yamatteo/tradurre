# Tradurre — Product Specification

This document describes what Tradurre **should be**, not what it currently is. It is the reference against which
the code is reviewed and `PLAN.md` is written. Change it deliberately, with the user's agreement; it is not a
log of implementation details.

---

## 1. Purpose

Tradurre turns **existing, unaligned literary translations** into a **reliable, searchable parallel corpus**.

The translator owns a library of books in French and their published Italian translations. Today those pairs
are just files: knowing how a word, an idiom or a passage was rendered means opening two PDFs and hunting. Tradurre
ingests each pair, aligns it sentence by sentence with as little manual work as possible, lets the translator
review and correct the alignment comfortably, and then makes the whole library searchable: *"how has
`désœuvrement` been translated, and in what context?"*

### Priorities

1. **Corpus building** (now): import → align → review → search. Everything in this spec serves this first.
2. **Revision** (later): editing an existing translation side by side with its source, in a tool that is
   handier than Word for that job. The data model must not preclude it, but no work is done for it yet.
3. **Translating from scratch** (distant future): out of scope.

### User

One translator, non-technical, working on Windows. Single user, single machine. The developer supports them.

### Scale

Dozens of books, one language pair (French → Italian). A typical book is roughly 1,000–5,000 sentences per side.
Language codes are stored per project, but nothing is tuned for pairs other than FR→IT.

### Non-goals

- Multi-user collaboration, accounts, sync, cloud hosting of the app.
- Machine translation or any generated text. Automated tools may **group, split and match** the translator's
  existing text; they never write or rewrite it.
- Scanned (image-only) PDFs, EPUB. Out of scope until asked for.
- Full typographic fidelity. Formatting (italics, emphasis) is nice to have, not required.

---

## 2. Core concepts

A **project** is one book: one **source edition** and one **target edition**, plus the **alignment** between them.

### Text layer: what each edition says

Each edition is an ordered sequence of **blocks**. Each block is an ordered sequence of **segments**.

- A **block** is a structural unit taken from the input: a paragraph, a heading, a footnote, a running head, a page
  number, front/back matter. Every block has a **kind**. Some kinds are **excluded** from alignment and search
  by default (running heads, page numbers, footnotes, …). Excluding never deletes: the translator can re-include
  a block, and the text is still there.
- A **segment** is (normally) a sentence: the smallest unit of alignment. Segmentation is automatic but
  correctable: the translator can split a segment or join two adjacent ones.
- Segment text is editable, to fix extraction errors (broken hyphenation, mangled glyphs, stray characters).
  The original extracted text is kept, so the translator can always compare or revert.

The two editions are **independent**: editing, splitting or joining segments on one side never modifies the
other side or the alignment's text.

### Alignment layer: which part of the source corresponds to which part of the target

The alignment is an ordered sequence of **beads**. A bead links a **contiguous run of source segments** to a
**contiguous run of target segments** (either side may be empty):

- 1:1, 1:2, 2:1, 2:3, … — a translator merging or splitting sentences is normal, not an error.
- 1:0 / 0:1 — material present in only one edition (an omitted sentence, a translator's note, a preface).

Beads cover every non-excluded segment of both editions exactly once, in order (alignment is monotone: no
crossing). Each bead carries:

- **confidence** (0–1) and **method** (how it was produced: anchor, length, embedding, llm, manual);
- **reviewed**: whether the translator has seen and accepted it.

Correcting the alignment means moving bead boundaries (e.g. "this target sentence belongs to the previous bead"),
merging or splitting beads. **It never touches segment text.** Correcting text never changes the bead structure,
with one exception: joining two segments that sit in different beads also merges those beads, so the joined
sentence stays whole in one bead. Splitting a segment keeps both parts in the bead that contained it.

### History

Every change by the translator (text edit, segment split/join, block exclude/include, bead change, review mark)
is recorded as an operation that can be **undone**, including after restarting the app. No user action can
silently destroy text.

---

## 3. Workflows

### 3.1 Import

1. The translator creates a project by choosing two files (source, target): born-digital **PDF**, **.docx** or
   **.txt** (UTF-8). Title and languages are pre-filled (FR→IT by default).
2. Extraction produces blocks with kinds. For PDFs it uses layout (position on page, font size, repetition
   across pages) to recognize running heads, page numbers and footnotes, and resolves PDF-specific damage:
   ligatures, private-use glyphs, end-of-line hyphenation, lines wrapped inside paragraphs.
3. Segmentation splits blocks into sentences, handling French and Italian conventions: abbreviations,
   dialogue dashes and guillemets, ellipses, quotations ending in punctuation.
4. A **baseline alignment** runs locally (no GPU, seconds per book) and the project opens in the review view.
5. Extraction problems the tool cannot fix are reported as **warnings attached to the project** and shown in the
   review view, never only in a log file.

### 3.2 High-quality alignment (parked)

A GPU aligner (sentence embeddings + an LLM judge, run on Colab through a project bundle) is **parked**: the local
baseline already aligns the reference book at F1 0.994 against an alignment corrected by the developer; the
translator's own review of it (in v0.2) replaces it as the reference. It comes back
(see §5) only if a gold book scores below **0.95**.

### 3.3 Review

The translator reviews **the whole book**, guided by the tool: they jump from one likely problem to the next,
correct it, and mark what they have checked. The review view is optimized for quick navigation and quick
corrections:

- One continuous, scrollable list of beads, source left, target right, paragraph and heading structure visible.
  Performance stays smooth on a 5,000-bead book.
- Low-confidence beads and unmatched (1:0, 0:1) beads stand out visually; there are shortcuts to jump to the next
  one.
- On request, beads holding more than one segment on either side are highlighted too, so many-to-one beads and
  false sentence splits are easy to spot.
- **Reviewed marks.** Each bead is reviewed or not, and the mark can be set or cleared on any single bead or on a
  selected run of beads, and every bead from the top of the book to the current one can be marked reviewed at once. Beads
  produced by an aligner start unreviewed; a bead produced by a correction inherits the mark (a merge is reviewed
  only if all merged beads were). Progress shows the share of beads reviewed, with a shortcut to the next unreviewed
  bead.
- Keyboard-first corrections on the current bead:
  - move the first/last segment of a side to the previous/next bead;
  - cut, copy and paste, as usual. Inside the sentence editor they work on text (a paste is a text edit, original
    kept, undoable). Outside it they work on whole sentences: copy puts the current sentence on the clipboard; a
    sentence cut at a bead's edge and pasted at the adjacent edge of the neighbouring bead moves there (the same
    as the move above); any other paste would change the order of the text, and is refused;
  - merge with the next bead; split a bead at a chosen segment;
  - split a segment at the cursor, join with the next segment;
  - edit segment text inline (plain text);
  - exclude/include the current block;
  - exclude/include every block from the start of the edition up to the current bead, or from it to the end.
- **Re-align range**: select a stretch between two trusted beads and re-run the local aligner on just that
  stretch.
- Undo/redo with the usual shortcuts.
- Excluded blocks are hidden by default and can be revealed in place.

### 3.4 Search

The corpus is searchable across all projects, from a global search page and from inside a project:

- One query, matched against the source side, the target side, or either. Matching ignores case and accents, and a
  word matches every word it begins (`désœuvr` finds `désœuvrement`, `désœuvré`); a phrase in quotes matches those
  words in sequence.
- Each result is a **bead** (the matched source and target text, with the match highlighted), plus the book
  title and the position in the book.
- **Context on demand:** expanding a result shows the surrounding beads; one click opens the project at that
  bead.
- Excluded blocks are not searched. Beads not yet reviewed are searchable but marked as such.

### 3.5 Export

- **Edition export**: the (corrected) text of one side as .txt or .docx, keeping paragraph structure.
- **Project bundle** export/import: the text layer and alignment of one project, as a full backup.

---

## 4. Non-functional requirements

- **Python 3.14** everywhere, including Colab if the parked aligner (§5) is ever built (the notebook installs it
  with uv rather than using Colab's system Python).
- **Local-first.** The app runs on the translator's laptop with no network access needed. Data lives in a single SQLite file under `~/.tradurre/`; copying that file is a backup.
- **Easy install and upgrade on Windows** through the self-installing launcher; upgrades never lose data.
  Schema changes migrate the existing database automatically.
- **Never lose work.** Every edit is saved immediately (no "save" button) and is transactional: a failed request
  leaves the data as it was. Concurrent requests from the UI cannot corrupt the data.
- **Responsive.** Opening a 5,000-bead book and scrolling through it is smooth; a single correction is reflected
  in well under a second; a search across dozens of books returns in under a second.
- **Debuggable.** Import and alignment runs record what they did (counts, timings, warnings) in the project, so a
  bad result can be diagnosed from the project itself.
- **Tested.** Alignment, segmentation and extraction have regression tests on small fixtures committed to the
  repo; the API and data invariants (bead coverage, monotonicity, undo) have tests.

---

## 5. Later (designed for, not built)

- **Corpus export** (TMX for translation software, TSV for spreadsheets), if a use appears. It includes unreviewed
  and one-sided beads, marked as such.
- **Revision mode:** edit the target edition side by side with the source as a writing environment, with
  formatting (italics, emphasis) carried through import and export.
- **Inline formatting** in segments, preserved from .docx/PDF and exported to .docx.
- **Translating from scratch** with the corpus as translation memory.
- **High-quality alignment (Colab)**, parked (§3.2): the translator exports a project bundle; a notebook runs the
  GPU aligner on it and produces an alignment file (beads over the bundle's segments, with confidence and method);
  loading it replaces only unreviewed beads, never text, and is refused if the text changed since the export.
