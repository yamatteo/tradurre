from typing import Literal

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    title: str
    source_lang: str
    target_lang: str


class ProjectUpdate(BaseModel):
    title: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None


class ProjectResponse(BaseModel):
    id: str
    title: str
    source_lang: str
    target_lang: str
    created_at: str
    updated_at: str
    pair_count: int = 0


class PairCreate(BaseModel):
    source_html: str
    target_html: str = ""
    source_text: str
    target_text: str = ""
    position: int | None = None
    section: int = 0
    paragraph: int = 0


class PairUpdate(BaseModel):
    source_html: str | None = None
    target_html: str | None = None
    status: str | None = None


class PairResponse(BaseModel):
    id: str
    project_id: str
    position: int
    section: int = 0
    paragraph: int = 0
    source_html: str
    target_html: str
    source_text: str
    target_text: str
    status: str
    created_at: str
    updated_at: str


class SearchResult(BaseModel):
    pair_id: str
    project_id: str
    project_title: str
    source_snippet: str
    target_snippet: str
    position: int


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


class PairSplitRequest(BaseModel):
    source_html_before: str
    source_html_after: str
    target_html_before: str
    target_html_after: str


class ImportParagraph(BaseModel):
    html: str
    text: str
    section: int = 0
    paragraph: int = 0


class ImportPreview(BaseModel):
    source_paragraphs: list[ImportParagraph]
    target_paragraphs: list[ImportParagraph]


class ImportUnit(BaseModel):
    html: str
    text: str
    index: int = 0
    section: int = 0
    paragraph: int = 0
    confidence: float = 1.0
    method: str = "anchor"
    flags: list[str] = []


class ImportSectionsResponse(BaseModel):
    source_sections: list[ImportUnit]
    target_sections: list[ImportUnit]


class ImportParagraphsRequest(BaseModel):
    sections: list[dict]  # [{source_text, target_text}]


class ImportParagraphsResponse(BaseModel):
    source_paragraphs: list[ImportUnit]
    target_paragraphs: list[ImportUnit]


class ImportSentencesRequest(BaseModel):
    paragraphs: list[dict]  # [{source_text, target_text, section}]


class ImportSentencesResponse(BaseModel):
    source_sentences: list[ImportUnit]
    target_sentences: list[ImportUnit]


class ResplitRequest(BaseModel):
    pair_ids: list[str]
    target_html: str


class ResplitResponse(BaseModel):
    pairs: list[PairResponse]


# ---------------------------------------------------------------------------
# Aligned artifact interchange format (produced by the external/Colab pipeline,
# consumed by /import/artifact). See tradurre/services/pipeline.py and
# tradurre/services/artifact_io.py.
# ---------------------------------------------------------------------------

class ArtifactSentence(BaseModel):
    source_text: str
    target_text: str
    confidence: float = 1.0
    method: str = "anchor"  # anchor | embedding | llm | fallback | manual
    flags: list[str] = []


class ArtifactParagraph(BaseModel):
    sentences: list[ArtifactSentence]


class ArtifactSection(BaseModel):
    paragraphs: list[ArtifactParagraph]


class AlignedArtifact(BaseModel):
    format: Literal["tradurre-aligned-bitext"]
    version: int = 1
    title: str = ""
    source_lang: str
    target_lang: str
    generated_at: str
    generator: dict = {}
    sections: list[ArtifactSection]
    warnings: list[str] = []
    stats: dict = {}


class ImportArtifactResponse(BaseModel):
    title: str
    source_lang: str
    target_lang: str
    source_sentences: list[ImportUnit]
    target_sentences: list[ImportUnit]
    warnings: list[str] = []
    stats: dict = {}


# Books: projects in the new model (/api/v2; PLAN.md, "Book API: import and read")


class BookImportResponse(BaseModel):
    id: str
    title: str
    bead_count: int
    warnings: list[str]


class BookSummary(BaseModel):
    id: str
    title: str
    source_lang: str
    target_lang: str
    bead_count: int
    reviewed_count: int


class BookSegment(BaseModel):
    segment_id: int
    block_id: int
    block_kind: str
    text: str
    original: str | None  # the extracted text, only when it differs from `text` (the sentence is edited)


class BookBead(BaseModel):
    id: int
    confidence: float
    method: str
    reviewed: bool
    source: list[BookSegment]
    target: list[BookSegment]


class BookExcludedSegment(BaseModel):
    segment_id: int
    text: str


class BookExcludedBlock(BaseModel):
    block_id: int
    side: Literal["source", "target"]
    kind: str
    page: int | None
    segments: list[BookExcludedSegment]
    after_bead_id: int | None


class BookResponse(BaseModel):
    id: str
    title: str
    source_lang: str
    target_lang: str
    beads: list[BookBead]
    excluded: list[BookExcludedBlock]
    can_undo: bool
    can_redo: bool


class BookRunWarning(BaseModel):
    side: Literal["source", "target"] | None
    message: str


class BookRun(BaseModel):
    id: int
    kind: str
    created_at: str
    app_version: str
    stats: dict
    warnings: list[BookRunWarning]


class BookMoveRequest(BaseModel):
    side: Literal["source", "target"]
    to: Literal["previous", "next"]


class BookSplitBeadRequest(BaseModel):
    source_at: int | None = None
    target_at: int | None = None


class BookReviewedRequest(BaseModel):
    bead_ids: list[int]
    reviewed: bool


class BookRealignRequest(BaseModel):
    first_bead_id: int
    last_bead_id: int


class BookRangeRequest(BaseModel):
    bead_id: int
    side: Literal["source", "target"]
    to: Literal["start", "end"]


class BookEditRequest(BaseModel):
    text: str


class BookSplitSegmentRequest(BaseModel):
    offset: int


class BookSearchSpan(BaseModel):
    text: str
    match: bool


class BookSearchResult(BaseModel):
    bead_id: int
    book_id: str
    title: str
    position: int  # 1-based, in the book
    source: list[BookSearchSpan]
    target: list[BookSearchSpan]
    reviewed: bool


class ContextBead(BaseModel):
    bead_id: int
    position: int  # 1-based, in the book
    source: str
    target: str
    reviewed: bool
