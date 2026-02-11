"""Smart alignment of source/target text files for literary translation import.

Pipeline:
1. Strip artifact lines (page numbers, symbols-only lines)
2. Join wrapped lines into paragraphs
3. Split paragraphs into sentences
4. Find anchors (shared capitalized words/phrases with equal counts)
5. Align using anchors + padding
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
# Step 1-3 combined
# ---------------------------------------------------------------------------

def extract_units(text: str) -> list[str]:
    """Full pipeline: clean → join → split. Returns sentence-level units."""
    lines = clean_lines(text)
    paragraphs = join_into_paragraphs(lines)
    units: list[str] = []
    for para in paragraphs:
        units.extend(split_sentences(para))
    return units


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
    """Full smart alignment pipeline.

    1. Extract sentence-level units from both texts
    2. Find anchors
    3. Align using anchors
    4. Return list of (source, target) string pairs
    """
    source_units = extract_units(source_text)
    target_units = extract_units(target_text)
    anchors = find_anchors(source_units, target_units)
    return align(source_units, target_units, anchors)
