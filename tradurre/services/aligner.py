"""Smart alignment of source/target text files for literary translation import.

Pipeline:
1. Strip artifact lines (page numbers, symbols-only lines)
2. Detect section boundaries (chapters)
3. Join wrapped lines into paragraphs
4. Split paragraphs into sentences
5. Find anchors (shared capitalized words/phrases with equal counts)
6. Align using anchors + padding (hierarchically: sections → paragraphs → sentences)
"""

import re
from collections import Counter


# Sentence-ending punctuation
_SENT_END = re.compile(r"[.;:?!]\s*$")

# Sentence boundary: sentence-end punctuation, whitespace, then capital letter
_SENT_BOUNDARY = re.compile(r"([.;:?!])\s+(?=[A-ZÀ-ÝÆŒ])")

# Artifact line: non-blank line containing only digits, whitespace, and punctuation/symbols
_ARTIFACT = re.compile(r"^[\d\s\W]*$")

# Capitalized token (including accented, hyphenated compounds like Marie-Ange)
_CAP_TOKEN = re.compile(r"\b[A-ZÀ-ÝÆŒ][a-zA-ZÀ-ÿæœ]+(?:-[A-Za-zÀ-ÿæœ]+)*\b")

# Chapter number: standalone integer 1-99
_CHAPTER_NUM = re.compile(r"^\d{1,2}$")


# ---------------------------------------------------------------------------
# Step 1: Strip artifact lines
# ---------------------------------------------------------------------------

def clean_lines(text: str) -> list[str]:
    """Remove lines that are only digits/symbols/whitespace (page numbers, etc.).

    Blank lines are preserved as paragraph separators.
    """
    result: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "":
            result.append("")  # keep blank lines as separators
        elif _ARTIFACT.match(stripped):
            continue  # drop artifact
        else:
            result.append(stripped)
    return result


# ---------------------------------------------------------------------------
# Step 1b: Detect section boundaries
# ---------------------------------------------------------------------------

def _is_section_break(lines: list[str], i: int, last_text_line: str) -> bool:
    """Check if line at index i is a section break marker (chapter heading)."""
    line = lines[i].strip()
    if not line:
        return False

    preceded_by_blank = (i == 0) or (lines[i - 1].strip() == "")
    followed_by_blank = (i == len(lines) - 1) or (
        i + 1 < len(lines) and lines[i + 1].strip() == ""
    )
    prev_ends_sentence = _SENT_END.search(last_text_line) if last_text_line else True

    # Chapter number (1-99), surrounded by blanks, after a sentence end
    if _CHAPTER_NUM.match(line):
        if preceded_by_blank and followed_by_blank and prev_ends_sentence:
            return True

    # Short heading: <60 chars, starts uppercase, not ending with comma or
    # sentence-ending punctuation, surrounded by blanks after a sentence end
    if len(line) < 60 and not line.endswith(","):
        looks_like_heading = (
            len(line) > 2
            and line[0].isupper()
            and not _SENT_END.search(line)
        )
        if (
            preceded_by_blank
            and followed_by_blank
            and prev_ends_sentence
            and looks_like_heading
        ):
            return True

    return False


def _detect_sections(lines: list[str]) -> list[list[str]]:
    """Split cleaned lines into sections at chapter boundaries.

    Returns a list of line-groups, one per section. Section marker lines
    are excluded from the content.
    """
    sections: list[list[str]] = []
    current_section: list[str] = []
    last_text_line = ""

    for i, line in enumerate(lines):
        if _is_section_break(lines, i, last_text_line):
            if current_section:
                sections.append(current_section)
                current_section = []
            last_text_line = ""
            continue

        current_section.append(line)
        if line.strip():
            last_text_line = line

    if current_section:
        sections.append(current_section)

    # If nothing detected, return everything as one section
    if not sections:
        sections = [lines]

    return sections


# ---------------------------------------------------------------------------
# Step 2: Join wrapped lines into paragraphs
# ---------------------------------------------------------------------------

def join_into_paragraphs(lines: list[str]) -> list[str]:
    """Join line-wrapped text into paragraphs.

    Rules:
    - A blank line ends the current paragraph.
    - A line ending with . : ; ? ! ends the current paragraph.
    - A line ending with a soft hyphen (U+00AD) joins to the next without space.
    - Otherwise the line is joined to the next with a space (line wrapping).
    """
    paragraphs: list[str] = []
    current: list[str] = []
    join_no_space = False  # next line joins without space (soft hyphen)

    for line in lines:
        if line == "":
            # Blank line → paragraph break
            if current:
                paragraphs.append("".join(current))
                current = []
            join_no_space = False
            continue

        # Strip leading soft hyphens (appear before some words like ­Pontorgueil)
        line = line.lstrip("\u00ad")

        if current:
            if join_no_space:
                current.append(line)
            else:
                current.append(" " + line)
        else:
            current.append(line)

        # Check if line ends with soft hyphen → next joins without space
        if current[-1].endswith("\u00ad"):
            current[-1] = current[-1].rstrip("\u00ad")
            join_no_space = True
        else:
            join_no_space = False

        if _SENT_END.search(line):
            # Line ends with sentence punctuation → paragraph break
            paragraphs.append("".join(current))
            current = []
            join_no_space = False

    if current:
        paragraphs.append("".join(current))

    return paragraphs


# ---------------------------------------------------------------------------
# Step 3: Split paragraphs into sentences
# ---------------------------------------------------------------------------

def split_sentences(paragraph: str) -> list[str]:
    """Split a paragraph into sentences at boundaries where sentence-ending
    punctuation is followed by a space and a capital letter.

    Returns a list of trimmed, non-empty sentences.
    """
    # Split keeping the punctuation attached to the preceding sentence
    parts = _SENT_BOUNDARY.split(paragraph)

    # _SENT_BOUNDARY captures the punctuation in group(1), so parts alternate:
    # [text_before, punct, text_before, punct, ..., text_rest]
    sentences: list[str] = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and re.match(r"^[.;:?!]$", parts[i + 1]):
            # Reattach punctuation to the preceding chunk
            sentences.append(parts[i] + parts[i + 1])
            i += 2
        else:
            sentences.append(parts[i])
            i += 1

    return [s.strip() for s in sentences if s.strip()]


# ---------------------------------------------------------------------------
# Hierarchy extraction: sections → paragraphs → sentences
# ---------------------------------------------------------------------------

def extract_hierarchy(text: str) -> list[list[list[str]]]:
    """Full pipeline returning sections[paragraphs[sentences]].

    1. _detect_sections on raw lines (before artifact removal, so chapter
       numbers like "2" are still visible)
    2. clean_lines — per section
    3. join_into_paragraphs — per section
    4. split_sentences — per paragraph
    """
    raw_lines = [line.strip() for line in text.split("\n")]
    raw_sections = _detect_sections(raw_lines)

    hierarchy: list[list[list[str]]] = []
    for section_lines in raw_sections:
        # Re-join section lines and run clean → join → split
        section_text = "\n".join(section_lines)
        cleaned = clean_lines(section_text)
        paragraphs_text = join_into_paragraphs(cleaned)
        section: list[list[str]] = []
        for para_text in paragraphs_text:
            sentences = split_sentences(para_text)
            if sentences:
                section.append(sentences)
        if section:
            hierarchy.append(section)

    return hierarchy


def extract_units(text: str) -> list[str]:
    """Full pipeline: clean → join → split. Returns flat sentence-level units."""
    return [s for sec in extract_hierarchy(text) for p in sec for s in p]


# ---------------------------------------------------------------------------
# Step 4: Find anchors
# ---------------------------------------------------------------------------

def _extract_capitalized(text: str) -> list[str]:
    """Extract all capitalized tokens (words starting with uppercase, len > 1)."""
    return _CAP_TOKEN.findall(text)


def _count_in_units(candidate: str, units: list[str]) -> int:
    """Count how many units contain the candidate as a substring."""
    return sum(1 for u in units if candidate in u)


def find_anchors(source_units: list[str], target_units: list[str]) -> list[str]:
    """Find capitalized words/phrases shared between source and target with
    equal occurrence counts.

    Returns anchors sorted by specificity (longer first, then rarer first).
    """
    source_text = " ".join(source_units)
    target_text = " ".join(target_units)

    # Collect capitalized tokens from both
    source_tokens = set(_extract_capitalized(source_text))
    target_tokens = set(_extract_capitalized(target_text))

    # Only keep tokens that appear in both
    shared_tokens = source_tokens & target_tokens

    # Build candidates: single tokens + bigrams of adjacent capitalized tokens
    candidates: set[str] = set()

    # Single tokens
    for tok in shared_tokens:
        candidates.add(tok)

    # Multi-word candidates: find sequences of 2-3 consecutive capitalized tokens
    # in source text that also appear in target text
    for text in [source_text, target_text]:
        words = text.split()
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                ngram_words = words[i : i + n]
                # All words in the n-gram must start with uppercase
                if all(_CAP_TOKEN.fullmatch(w) for w in ngram_words):
                    phrase = " ".join(ngram_words)
                    # Must appear in both texts
                    if phrase in source_text and phrase in target_text:
                        candidates.add(phrase)

    # Filter: keep candidates with equal non-zero counts in source and target units
    anchors: list[str] = []
    for candidate in candidates:
        sc = _count_in_units(candidate, source_units)
        tc = _count_in_units(candidate, target_units)
        if sc == tc and sc > 0:
            anchors.append(candidate)

    # Remove anchors that are substrings of longer anchors
    anchors.sort(key=len, reverse=True)
    filtered: list[str] = []
    for a in anchors:
        if not any(a in longer and a != longer for longer in filtered):
            filtered.append(a)

    # Sort by specificity: longer first, then fewer occurrences first
    def sort_key(a: str) -> tuple[int, int]:
        return (-len(a), _count_in_units(a, source_units))

    filtered.sort(key=sort_key)
    return filtered


# ---------------------------------------------------------------------------
# Step 5: Align using anchors
# ---------------------------------------------------------------------------

def align(
    source_units: list[str],
    target_units: list[str],
    anchors: list[str],
) -> list[tuple[str, str]]:
    """Align source and target units using anchor constraints.

    For each anchor, the nth occurrence in source is paired with the nth
    occurrence in target. Between anchor points, unanchored units are
    distributed with empty-string padding on the shorter side.

    Returns a list of (source_text, target_text) pairs.
    """
    # Build anchor constraints: (source_idx, target_idx)
    constraints: list[tuple[int, int]] = []

    for anchor in anchors:
        s_indices = [i for i, u in enumerate(source_units) if anchor in u]
        t_indices = [i for i, u in enumerate(target_units) if anchor in u]

        # Pair nth occurrence with nth occurrence
        for si, ti in zip(s_indices, t_indices):
            constraints.append((si, ti))

    # Deduplicate and sort by source index
    constraints = sorted(set(constraints), key=lambda c: (c[0], c[1]))

    # Remove crossing constraints (keep only monotonically increasing)
    mono: list[tuple[int, int]] = []
    for si, ti in constraints:
        if not mono or (si > mono[-1][0] and ti > mono[-1][1]):
            mono.append((si, ti))
        elif si == mono[-1][0] or ti == mono[-1][1]:
            # Same source or target index — skip (already handled)
            continue
        # else: crossing — skip

    # Add sentinel constraints for start and end
    anchor_points = [(-1, -1)] + mono + [(len(source_units), len(target_units))]

    result: list[tuple[str, str]] = []

    for k in range(len(anchor_points) - 1):
        s_start = anchor_points[k][0] + 1
        s_end = anchor_points[k + 1][0]
        t_start = anchor_points[k][1] + 1
        t_end = anchor_points[k + 1][1]

        s_gap = source_units[s_start:s_end]
        t_gap = target_units[t_start:t_end]

        # Pad the shorter side
        max_len = max(len(s_gap), len(t_gap))
        s_padded = s_gap + [""] * (max_len - len(s_gap))
        t_padded = t_gap + [""] * (max_len - len(t_gap))

        for s, t in zip(s_padded, t_padded):
            result.append((s, t))

        # Add the anchor point itself (if not sentinel end)
        if anchor_points[k + 1][0] < len(source_units):
            result.append((
                source_units[anchor_points[k + 1][0]],
                target_units[anchor_points[k + 1][1]],
            ))

    return result


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def smart_align(source_text: str, target_text: str) -> list[tuple[str, str]]:
    """Full smart alignment pipeline (flat, backward-compatible).

    1. Extract sentence-level units from both texts
    2. Find anchors
    3. Align using anchors
    4. Return list of (source, target) string pairs
    """
    source_units = extract_units(source_text)
    target_units = extract_units(target_text)
    anchors = find_anchors(source_units, target_units)
    return align(source_units, target_units, anchors)


# ---------------------------------------------------------------------------
# Hierarchical alignment
# ---------------------------------------------------------------------------

def _align_units(
    source_units: list[str],
    target_units: list[str],
) -> list[tuple[str, str]]:
    """Find anchors and align two lists of text units."""
    if not source_units and not target_units:
        return []
    anchors = find_anchors(source_units, target_units)
    return align(source_units, target_units, anchors)


def _anchor_score(source_units: list[str], target_units: list[str]) -> int:
    """Score an alignment by counting how many anchor constraint pairs it produces."""
    if not source_units or not target_units:
        return 0
    anchors = find_anchors(source_units, target_units)
    count = 0
    for anchor in anchors:
        sc = sum(1 for u in source_units if anchor in u)
        tc = sum(1 for u in target_units if anchor in u)
        count += min(sc, tc)
    return count


def _boundary_optimize(
    pairs: list[tuple[list[str], list[str]]],
    score_fn=None,
) -> list[tuple[list[str], list[str]]]:
    """Try moving boundary units between adjacent containers to improve alignment.

    For each adjacent pair of containers, tries moving the last unit of the
    first container to the start of the second (and vice versa), accepting
    the move only if it increases the total score.

    `score_fn` defaults to the anchor-count heuristic (_anchor_score) but can be
    swapped for any `(list[str], list[str]) -> float` scorer -- e.g. an
    embedding-similarity score (see tradurre.services.embed_align) -- to drive
    the same boundary-nudging logic with a stronger signal. Only ever reassigns
    which existing units are grouped together; never alters unit content.
    """
    if score_fn is None:
        score_fn = _anchor_score

    improved = True
    while improved:
        improved = False
        for i in range(len(pairs) - 1):
            src_a, tgt_a = pairs[i]
            src_b, tgt_b = pairs[i + 1]

            current_score = (
                score_fn(src_a, tgt_a) + score_fn(src_b, tgt_b)
            )

            best_score = current_score
            best = None

            # Try moving last of A-source to start of B-source
            if len(src_a) > 1:
                new_src_a = src_a[:-1]
                new_src_b = [src_a[-1]] + src_b
                s = score_fn(new_src_a, tgt_a) + score_fn(new_src_b, tgt_b)
                if s > best_score:
                    best_score = s
                    best = (new_src_a, tgt_a, new_src_b, tgt_b)

            # Try moving first of B-source to end of A-source
            if len(src_b) > 1:
                new_src_a = src_a + [src_b[0]]
                new_src_b = src_b[1:]
                s = score_fn(new_src_a, tgt_a) + score_fn(new_src_b, tgt_b)
                if s > best_score:
                    best_score = s
                    best = (new_src_a, tgt_a, new_src_b, tgt_b)

            # Try moving last of A-target to start of B-target
            if len(tgt_a) > 1:
                new_tgt_a = tgt_a[:-1]
                new_tgt_b = [tgt_a[-1]] + tgt_b
                s = score_fn(src_a, new_tgt_a) + score_fn(src_b, new_tgt_b)
                if s > best_score:
                    best_score = s
                    best = (src_a, new_tgt_a, src_b, new_tgt_b)

            # Try moving first of B-target to end of A-target
            if len(tgt_b) > 1:
                new_tgt_a = tgt_a + [tgt_b[0]]
                new_tgt_b = tgt_b[1:]
                s = score_fn(src_a, new_tgt_a) + score_fn(src_b, new_tgt_b)
                if s > best_score:
                    best_score = s
                    best = (src_a, new_tgt_a, src_b, new_tgt_b)

            if best is not None:
                pairs[i] = (best[0], best[1])
                pairs[i + 1] = (best[2], best[3])
                improved = True

    return pairs


def align_sections(
    source_sections: list[list[list[str]]],
    target_sections: list[list[list[str]]],
) -> list[tuple[list[list[str]], list[list[str]]]]:
    """Align sections using anchors on section-level concatenated text."""
    source_texts = [
        " ".join(s for p in sec for s in p) for sec in source_sections
    ]
    target_texts = [
        " ".join(s for p in sec for s in p) for sec in target_sections
    ]

    aligned_texts = _align_units(source_texts, target_texts)

    # Build lookup from text → structured section
    src_iter = iter(source_sections)
    tgt_iter = iter(target_sections)

    result: list[tuple[list[list[str]], list[list[str]]]] = []
    for src_text, tgt_text in aligned_texts:
        src_sec = next(src_iter) if src_text else [[]]
        tgt_sec = next(tgt_iter) if tgt_text else [[]]
        result.append((src_sec, tgt_sec))

    return result


def align_paragraphs(
    source_section: list[list[str]],
    target_section: list[list[str]],
) -> list[tuple[list[str], list[str]]]:
    """Align paragraphs within a section pair using anchors."""
    source_texts = [" ".join(p) for p in source_section]
    target_texts = [" ".join(p) for p in target_section]

    aligned_texts = _align_units(source_texts, target_texts)

    src_iter = iter(source_section)
    tgt_iter = iter(target_section)

    result: list[tuple[list[str], list[str]]] = []
    for src_text, tgt_text in aligned_texts:
        src_para = next(src_iter) if src_text else []
        tgt_para = next(tgt_iter) if tgt_text else []
        result.append((src_para, tgt_para))

    return result


def align_sentences(
    source_para: list[str],
    target_para: list[str],
) -> list[tuple[str, str]]:
    """Align sentences within a paragraph pair using anchors."""
    return _align_units(source_para, target_para)


def smart_align_hierarchical(
    source_text: str, target_text: str,
) -> list[tuple[int, int, str, str]]:
    """Full hierarchical alignment pipeline.

    Returns list of (section_idx, paragraph_idx, source_sentence, target_sentence).
    """
    source_h = extract_hierarchy(source_text)
    target_h = extract_hierarchy(target_text)

    # Level 1: sections
    section_pairs = align_sections(source_h, target_h)

    result: list[tuple[int, int, str, str]] = []
    for section_idx, (src_sec, tgt_sec) in enumerate(section_pairs):
        # Level 2: paragraphs within section
        para_pairs_raw = align_paragraphs(src_sec, tgt_sec)
        para_pairs = _boundary_optimize(list(para_pairs_raw))

        for para_idx, (src_para, tgt_para) in enumerate(para_pairs):
            # Level 3: sentences within paragraph
            sent_pairs = align_sentences(src_para, tgt_para)

            for src_sent, tgt_sent in sent_pairs:
                result.append((section_idx, para_idx, src_sent, tgt_sent))

    return result
