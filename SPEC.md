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

Dozens of books, one language pair (French → Italian). A book is roughly 3,000–10,000 sentences per side.
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
except that splitting or joining a segment keeps the result inside the bead(s) that contained it.

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

### 3.2 High-quality alignment (Colab)

The best alignment needs a GPU (sentence embeddings + an LLM judge). That runs on Colab:

1. From the app, the translator exports a **project bundle** (the extracted, possibly already corrected text
   layer of both editions).
2. A notebook runs the heavy aligner on the bundle and produces an **alignment file**: beads over the bundle's
   segments, with confidence and method.
3. The translator loads the alignment file back into the project. It replaces the beads of the regions not yet
   reviewed; reviewed beads are kept. Text is never changed by this round trip.

The heavy aligner may also be run directly on the two original files (as a convenience), producing a bundle plus
alignment in one go.

### 3.3 Review

The translator skims **the whole book**. The review view is optimized for steady reading and quick corrections:

- One continuous, scrollable list of beads, source left, target right, paragraph and heading structure visible.
  Performance stays smooth on a 10,000-bead book.
- Low-confidence beads and unmatched (1:0, 0:1) beads stand out visually; there are shortcuts to jump to the next
  one.
- **Reviewed marks.** Each bead is reviewed or not, and the mark can be set or cleared on any single bead. Beads
  produced by an aligner start unreviewed; a bead produced by a correction inherits the mark (a merge is reviewed
  only if all merged beads were). Progress shows the share of beads reviewed, with a shortcut to the next unreviewed
  bead.
- **Skim review.** A pass the translator starts deliberately, typically once after import: starting from the first
  unreviewed bead, they read the book and fix what's wrong as they go. A bead becomes reviewed when it leaves
  through the top edge during ordinary downward scrolling after being fully on screen for about a second. Jumps,
  scrollbar drags and scrolling up mark nothing. The pass ends when the translator stops it or at the end of the
  book. One undo removes the marks made since the last correction.
- Keyboard-first corrections on the current bead:
  - move the first/last segment of a side to the previous/next bead;
  - merge with the next bead; split a bead at a chosen segment;
  - split a segment at the cursor, join with the next segment;
  - edit segment text inline (plain text);
  - exclude/include the current block.
- **Re-align range**: select a stretch between two trusted beads and re-run the local aligner on just that
  stretch.
- Undo/redo with the usual shortcuts.
- Excluded blocks are hidden by default and can be revealed in place.

### 3.4 Search

The corpus is searchable across all projects, from a global search page and from inside a project:

- Query the source side, the target side, or both. Matching ignores case and accents; phrases work.
- Each result is a **bead** (the matched source and target text, with the match highlighted), plus the book
  title and the position in the book.
- **Context on demand:** expanding a result shows the surrounding beads; one click opens the project at that
  bead.
- Excluded blocks are not searched. Beads not yet reviewed are searchable but marked as such.

### 3.5 Export

- **Corpus export** per project or for the whole library: TMX and TSV (one bead per row).
- **Edition export**: the (corrected) text of one side as .txt or .docx, keeping paragraph structure.
- **Project bundle** export/import (see 3.2), which also works as a full backup of a project.

---

## 4. Non-functional requirements

- **Python 3.14** everywhere, including Colab, where the notebook installs it with uv rather than using Colab's
  system Python.
- **Local-first.** The app runs on the translator's laptop with no network access needed (except for the
  optional Colab step). Data lives in a single SQLite file under `~/.tradurre/`; copying that file is a backup.
- **Easy install and upgrade on Windows** through the self-installing launcher; upgrades never lose data.
  Schema changes migrate the existing database automatically.
- **Never lose work.** Every edit is saved immediately (no "save" button) and is transactional: a failed request
  leaves the data as it was. Concurrent requests from the UI cannot corrupt the data.
- **Responsive.** Opening a 10,000-bead book and scrolling through it is smooth; a single correction is reflected
  in well under a second; a search across dozens of books returns in under a second.
- **Debuggable.** Import and alignment runs record what they did (counts, timings, warnings) in the project, so a
  bad result can be diagnosed from the project itself.
- **Tested.** Alignment, segmentation and extraction have regression tests on small fixtures committed to the
  repo; the API and data invariants (bead coverage, monotonicity, undo) have tests.

---

## 5. Later (designed for, not built)

- **Revision mode:** edit the target edition side by side with the source as a writing environment, with
  formatting (italics, emphasis) carried through import and export.
- **Inline formatting** in segments, preserved from .docx/PDF and exported to .docx.
- **Translating from scratch** with the corpus as translation memory.
