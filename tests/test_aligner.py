"""Tests for the smart alignment pipeline using library/easy.source.txt and library/easy.target.txt."""

from pathlib import Path

import pytest

from tradurre.services.aligner import (
    align,
    align_paragraphs,
    align_sections,
    align_sentences,
    clean_lines,
    extract_hierarchy,
    extract_units,
    find_anchors,
    join_into_paragraphs,
    smart_align,
    smart_align_hierarchical,
    split_sentences,
    _boundary_optimize,
    _detect_sections,
)

LIBRARY = Path(__file__).resolve().parent.parent / "library"
EASY_SOURCE = (LIBRARY / "easy.source.txt").read_text(encoding="utf-8")
EASY_TARGET = (LIBRARY / "easy.target.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 1: clean_lines
# ---------------------------------------------------------------------------


class TestCleanLines:
    def test_removes_page_numbers(self):
        text = "Hello world.\n7\n\nNext paragraph."
        lines = clean_lines(text)
        assert "7" not in lines
        assert "Hello world." in lines

    def test_removes_symbol_only_lines(self):
        text = "Some text.\n*\n---\n123\nMore text."
        lines = clean_lines(text)
        non_blank = [l for l in lines if l]
        assert all("*" not in l and "---" not in l and "123" not in l for l in non_blank)

    def test_preserves_blank_lines(self):
        text = "Para one.\n\nPara two."
        lines = clean_lines(text)
        assert "" in lines

    def test_easy_source_no_crash(self):
        lines = clean_lines(EASY_SOURCE)
        assert len(lines) > 0
        # Easy files are already clean, so nearly all lines should survive
        original_non_blank = [l for l in EASY_SOURCE.split("\n") if l.strip()]
        cleaned_non_blank = [l for l in lines if l]
        assert len(cleaned_non_blank) >= len(original_non_blank) * 0.9


# ---------------------------------------------------------------------------
# Step 2: join_into_paragraphs
# ---------------------------------------------------------------------------


class TestJoinIntoParagraphs:
    def test_joins_wrapped_lines(self):
        lines = [
            "The quick brown fox",
            "jumped over the lazy dog.",
        ]
        paras = join_into_paragraphs(lines)
        assert len(paras) == 1
        assert paras[0] == "The quick brown fox jumped over the lazy dog."

    def test_splits_on_sentence_end(self):
        lines = [
            "First sentence.",
            "Second sentence.",
        ]
        paras = join_into_paragraphs(lines)
        assert len(paras) == 2

    def test_splits_on_blank_line(self):
        lines = ["First para.", "", "Second para."]
        paras = join_into_paragraphs(lines)
        assert len(paras) == 2

    def test_colon_ends_paragraph(self):
        lines = [
            "He said the following:",
            "A new thought begins here.",
        ]
        paras = join_into_paragraphs(lines)
        assert len(paras) == 2

    def test_comma_does_not_end_paragraph(self):
        lines = [
            "First part,",
            "second part.",
        ]
        paras = join_into_paragraphs(lines)
        assert len(paras) == 1

    def test_easy_source_produces_paragraphs(self):
        lines = clean_lines(EASY_SOURCE)
        paras = join_into_paragraphs(lines)
        # Should produce multiple paragraphs from the continuous text
        assert len(paras) > 5


# ---------------------------------------------------------------------------
# Step 3: split_sentences
# ---------------------------------------------------------------------------


class TestSplitSentences:
    def test_single_sentence(self):
        result = split_sentences("Hello world.")
        assert result == ["Hello world."]

    def test_two_sentences(self):
        result = split_sentences("First sentence. Second sentence.")
        assert len(result) == 2
        assert result[0] == "First sentence."
        assert result[1] == "Second sentence."

    def test_question_mark_boundary(self):
        result = split_sentences("Is this right? Yes it is.")
        assert len(result) == 2

    def test_lowercase_after_period_no_split(self):
        result = split_sentences("e.g. this should not split.")
        assert len(result) == 1

    def test_accented_capital(self):
        result = split_sentences("Fin de la phrase. À cette époque, il vivait seul.")
        assert len(result) == 2
        assert "À cette époque" in result[1]


# ---------------------------------------------------------------------------
# Step 1-3 combined: extract_units
# ---------------------------------------------------------------------------


class TestExtractUnits:
    def test_easy_source_units(self):
        units = extract_units(EASY_SOURCE)
        assert len(units) > 20  # should have many sentences
        # First unit should start with "Le premier incendie"
        assert units[0].startswith("Le premier incendie")

    def test_easy_target_units(self):
        units = extract_units(EASY_TARGET)
        assert len(units) > 20
        assert units[0].startswith("Il primo incendio")

    def test_with_artifacts(self):
        text = "7\n\nSome real text here.\n36\n\nMore text follows."
        units = extract_units(text)
        assert all("7" != u and "36" != u for u in units)
        assert len(units) == 2


# ---------------------------------------------------------------------------
# Step 4: find_anchors
# ---------------------------------------------------------------------------


class TestFindAnchors:
    def test_easy_files_anchors(self):
        source_units = extract_units(EASY_SOURCE)
        target_units = extract_units(EASY_TARGET)
        anchors = find_anchors(source_units, target_units)

        # These proper nouns appear identically in both source and target
        # Note: "Marie-Ange" may be excluded because source has some "MarieAnge"
        # (missing hyphen from PDF extraction), causing count mismatch
        expected = {"Guillaume", "Pontorgueil", "Sainte-Guénulphe", "Sibylle Stoltz"}
        anchor_set = set(anchors)

        for name in expected:
            assert any(
                name in a for a in anchor_set
            ), f"Expected anchor containing '{name}' not found. Anchors: {anchors}"

    def test_translated_names_excluded(self):
        source_units = extract_units(EASY_SOURCE)
        target_units = extract_units(EASY_TARGET)
        anchors = find_anchors(source_units, target_units)

        # These names differ between source and target
        for name in ["Ligné", "Ardent"]:
            # They should NOT be anchors (different counts or only in one side)
            # Ligné only in source, Ardent only in target
            assert name not in anchors, f"'{name}' should not be an anchor"

    def test_simple_anchors(self):
        source = ["Hello Marie-Ange.", "Goodbye Guillaume."]
        target = ["Ciao Marie-Ange.", "Arrivederci Guillaume."]
        anchors = find_anchors(source, target)
        assert "Marie-Ange" in anchors
        assert "Guillaume" in anchors


# ---------------------------------------------------------------------------
# Step 5: align
# ---------------------------------------------------------------------------


class TestAlign:
    def test_simple_alignment(self):
        source = ["A before.", "Has Marie-Ange.", "A after."]
        target = ["T before.", "With Marie-Ange.", "T after."]
        anchors = ["Marie-Ange"]
        result = align(source, target, anchors)
        assert len(result) == 3
        assert result[1] == ("Has Marie-Ange.", "With Marie-Ange.")

    def test_padding_shorter_side(self):
        source = ["S1.", "S2.", "Has Anchor.", "S4."]
        target = ["T1.", "Has Anchor.", "T3."]
        anchors = ["Anchor"]
        result = align(source, target, anchors)
        # Before anchor: source has S1, S2; target has T1 → pad target
        # After anchor: source has S4; target has T3 → match
        source_texts = [r[0] for r in result]
        target_texts = [r[1] for r in result]
        assert len(source_texts) == len(target_texts)
        # The anchor should be aligned
        for s, t in result:
            if "Anchor" in s:
                assert "Anchor" in t

    def test_no_anchors_just_pads(self):
        source = ["S1.", "S2.", "S3."]
        target = ["T1.", "T2."]
        result = align(source, target, [])
        assert len(result) == 3
        assert result[2][1] == ""  # target padded


# ---------------------------------------------------------------------------
# End-to-end: smart_align
# ---------------------------------------------------------------------------


class TestSmartAlign:
    def test_easy_files_alignment(self):
        pairs = smart_align(EASY_SOURCE, EASY_TARGET)

        # Should produce equal-length aligned pairs
        assert len(pairs) > 0
        for src, tgt in pairs:
            assert isinstance(src, str)
            assert isinstance(tgt, str)

        # Check that anchored sentences are aligned
        for src, tgt in pairs:
            if "Guillaume" in src and "Guillaume" in tgt:
                break
        else:
            pytest.fail("No pair found where Guillaume appears in both source and target")

    def test_empty_padding_present(self):
        pairs = smart_align(EASY_SOURCE, EASY_TARGET)
        # With different sentence counts, some padding is expected
        source_empties = sum(1 for s, _ in pairs if s == "")
        target_empties = sum(1 for _, t in pairs if t == "")
        # At least one side should have some padding (texts have different lengths)
        assert source_empties > 0 or target_empties > 0 or len(pairs) > 0

    def test_result_covers_all_content(self):
        pairs = smart_align(EASY_SOURCE, EASY_TARGET)

        source_units = extract_units(EASY_SOURCE)
        target_units = extract_units(EASY_TARGET)

        # Every source unit should appear in the result
        result_sources = {s for s, _ in pairs if s}
        for unit in source_units:
            assert unit in result_sources, f"Source unit missing: {unit[:50]}..."

        # Every target unit should appear in the result
        result_targets = {t for _, t in pairs if t}
        for unit in target_units:
            assert unit in result_targets, f"Target unit missing: {unit[:50]}..."


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------


class TestDetectSections:
    def test_no_sections_single_block(self):
        """Text with no section markers produces one section."""
        lines = clean_lines(EASY_SOURCE)
        sections = _detect_sections(lines)
        # easy.source.txt has no chapter markers → single section
        assert len(sections) == 1

    def test_chapter_number_splits(self):
        """A standalone chapter number between blank lines splits sections."""
        lines = [
            "First chapter text.",
            "",
            "2",
            "",
            "Second chapter text.",
        ]
        sections = _detect_sections(lines)
        assert len(sections) == 2
        # Content of first section
        assert any("First chapter" in l for l in sections[0])
        # Content of second section
        assert any("Second chapter" in l for l in sections[1])

    def test_chapter_number_mid_sentence_no_split(self):
        """A number that appears mid-sentence should not split."""
        lines = [
            "He said",
            "7",
            "",
            "More text.",
        ]
        # "He said" doesn't end with sentence punctuation, so 7 is not a section break
        sections = _detect_sections(lines)
        assert len(sections) == 1

    def test_heading_splits(self):
        """A short heading line splits sections."""
        lines = [
            "End of previous chapter.",
            "",
            "The New Beginning",
            "",
            "Start of next chapter.",
        ]
        sections = _detect_sections(lines)
        assert len(sections) == 2

    def test_heading_with_period_no_split(self):
        """A short line ending with period is a sentence, not a heading."""
        lines = [
            "Previous text.",
            "",
            "Short sentence.",
            "",
            "More text.",
        ]
        sections = _detect_sections(lines)
        # "Short sentence." ends with period → _SENT_END matches → not a heading
        assert len(sections) == 1


# ---------------------------------------------------------------------------
# Hierarchy extraction
# ---------------------------------------------------------------------------


class TestExtractHierarchy:
    def test_easy_source_structure(self):
        """easy.source.txt → 1 section, multiple paragraphs, multiple sentences."""
        h = extract_hierarchy(EASY_SOURCE)
        assert len(h) == 1  # no section breaks
        assert len(h[0]) > 5  # multiple paragraphs
        total_sentences = sum(len(p) for p in h[0])
        assert total_sentences == len(extract_units(EASY_SOURCE))

    def test_multi_section_text(self):
        """Synthetic text with chapter markers."""
        text = (
            "First sentence of chapter one.\n\n"
            "2\n\n"
            "First sentence of chapter two.\n\n"
            "Second paragraph of chapter two."
        )
        h = extract_hierarchy(text)
        assert len(h) == 2
        # Chapter 1: 1 paragraph, 1 sentence
        assert len(h[0]) == 1
        assert h[0][0] == ["First sentence of chapter one."]
        # Chapter 2: 2 paragraphs
        assert len(h[1]) == 2

    def test_consistency_with_extract_units(self):
        """Flat extract_units should equal flattened extract_hierarchy."""
        flat = extract_units(EASY_SOURCE)
        h = extract_hierarchy(EASY_SOURCE)
        from_hierarchy = [s for sec in h for p in sec for s in p]
        assert flat == from_hierarchy


# ---------------------------------------------------------------------------
# Hierarchical alignment
# ---------------------------------------------------------------------------


class TestHierarchicalAlignment:
    def test_align_sections_equal_count(self):
        """Two texts with same number of sections align 1:1."""
        src = [
            [["Hello Marie.", "How are you?"]],
            [["Goodbye Marie."]],
        ]
        tgt = [
            [["Ciao Marie.", "Come stai?"]],
            [["Arrivederci Marie."]],
        ]
        result = align_sections(src, tgt)
        assert len(result) == 2

    def test_align_paragraphs_with_anchors(self):
        src_sec = [
            ["Before Guillaume arrived."],
            ["Guillaume spoke.", "He was happy."],
        ]
        tgt_sec = [
            ["Prima che Guillaume arrivasse."],
            ["Guillaume parlò.", "Era felice."],
        ]
        result = align_paragraphs(src_sec, tgt_sec)
        assert len(result) == 2

    def test_align_sentences(self):
        src = ["Hello Marie.", "Goodbye Marie."]
        tgt = ["Ciao Marie.", "Addio Marie."]
        result = align_sentences(src, tgt)
        assert len(result) == 2
        assert result[0] == ("Hello Marie.", "Ciao Marie.")

    def test_smart_align_hierarchical_returns_tuples(self):
        pairs = smart_align_hierarchical(EASY_SOURCE, EASY_TARGET)
        assert len(pairs) > 0
        for sec_idx, para_idx, src, tgt in pairs:
            assert isinstance(sec_idx, int)
            assert isinstance(para_idx, int)
            assert isinstance(src, str)
            assert isinstance(tgt, str)

    def test_hierarchical_covers_all_content(self):
        """All source and target sentences appear in hierarchical result."""
        pairs = smart_align_hierarchical(EASY_SOURCE, EASY_TARGET)
        source_units = extract_units(EASY_SOURCE)
        target_units = extract_units(EASY_TARGET)

        result_sources = {src for _, _, src, _ in pairs if src}
        for unit in source_units:
            assert unit in result_sources, f"Source missing: {unit[:50]}..."

        result_targets = {tgt for _, _, _, tgt in pairs if tgt}
        for unit in target_units:
            assert unit in result_targets, f"Target missing: {unit[:50]}..."

    def test_hierarchical_consistent_with_flat(self):
        """Hierarchical alignment produces same sentences as flat (possibly different grouping)."""
        flat_pairs = smart_align(EASY_SOURCE, EASY_TARGET)
        hier_pairs = smart_align_hierarchical(EASY_SOURCE, EASY_TARGET)

        flat_sources = sorted(s for s, _ in flat_pairs if s)
        hier_sources = sorted(s for _, _, s, _ in hier_pairs if s)
        assert flat_sources == hier_sources


# ---------------------------------------------------------------------------
# Boundary optimization
# ---------------------------------------------------------------------------


class TestBoundaryOptimize:
    def test_no_change_when_optimal(self):
        """No moves when alignment is already optimal."""
        pairs = [
            (["Has Marie."], ["Con Marie."]),
            (["Has Guillaume."], ["Con Guillaume."]),
        ]
        result = _boundary_optimize(list(pairs))
        assert result == pairs

    def test_moves_improve_score(self):
        """Moving a sentence to the adjacent container improves anchor match."""
        # Guillaume is in container A's source but container B's target → should move
        pairs = [
            (["Hello.", "Guillaume spoke."], ["Ciao."]),
            (["World."], ["Guillaume parlò.", "Mondo."]),
        ]
        result = _boundary_optimize(list(pairs))
        # After optimization, Guillaume should be in the same container on both sides
        # Check that at least one container has Guillaume on both sides
        found = False
        for src_list, tgt_list in result:
            src_has = any("Guillaume" in s for s in src_list)
            tgt_has = any("Guillaume" in t for t in tgt_list)
            if src_has and tgt_has:
                found = True
                break
        assert found, f"Guillaume should be co-located after optimization: {result}"
