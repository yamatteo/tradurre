"""Front and back matter: a conservative rule run on every extraction (PLAN.md, "Front and back matter").

Only paragraphs at the very start (before chapter 1) or the very end (after the last long paragraph) of an edition
are re-kinded, and only when a publishing marker (ISBN, ©, "Finito di stampare", …) shows where the matter is. No
marker, no exclusion: the rule leaves junk in rather than hide text, and the translator can range-exclude the rest.
"""

from dataclasses import replace

from tradurre.services.extract import _CHAPTER_NUMBER, ExtractedBlock

MARKERS = (
    "ISBN", "©", "Copyright", "Dépôt légal", "Achevé d", "Imprimé", "Du même auteur", "Dello stesso autore",
    "Titre original", "Titolo originale", "Traduit de", "Traduzione di", "Traduzione dal", "Finito di stampare",
    "Tous droits", "Tutti i diritti", "www.", "Éditions", "Edizioni", "Editore",
)
_LONG = 60  # words: a paragraph this long is body text


def _marked(block: ExtractedBlock) -> bool:
    return any(marker in block.text for marker in MARKERS)


def _long_paragraph(block: ExtractedBlock) -> bool:
    return block.kind == "paragraph" and len(block.text.split()) >= _LONG


def _chapter_number(block: ExtractedBlock) -> bool:
    return block.kind == "heading" and bool(_CHAPTER_NUMBER.match(block.text))


def mark_matter(blocks: list[ExtractedBlock]) -> list[ExtractedBlock]:
    """A copy of `blocks` in which the paragraphs of the marked front and back runs become `front_matter` and
    `back_matter`. Other kinds, headings included, never change."""
    kinds = [block.kind for block in blocks]

    body_start = next((k for k, b in enumerate(blocks) if _chapter_number(b) or _long_paragraph(b)), None)
    if body_start is not None:
        last_mark = max((k for k in range(body_start) if _marked(blocks[k])), default=None)
        if last_mark is not None:
            region = set(range(last_mark + 1))
            page = blocks[last_mark].page
            if page is not None:
                region |= {k for k in range(last_mark + 1, body_start) if blocks[k].page == page}
            for k in region:
                if kinds[k] == "paragraph":
                    kinds[k] = "front_matter"

    body_end = max((k for k, b in enumerate(blocks) if _long_paragraph(b)), default=None)
    if body_end is not None:
        first_mark = next((k for k in range(body_end + 1, len(blocks)) if _marked(blocks[k])), None)
        if first_mark is not None:
            region = set(range(first_mark, len(blocks)))
            page = blocks[first_mark].page
            if page is not None:
                region |= {k for k in range(body_end + 1, first_mark) if blocks[k].page == page}
            for k in region:
                if kinds[k] == "paragraph":
                    kinds[k] = "back_matter"

    return [block if block.kind == kind else replace(block, kind=kind) for block, kind in zip(blocks, kinds)]
