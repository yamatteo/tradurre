from typing import Literal

from pydantic import BaseModel

ReviewLevel = Literal["sentence", "turn", "paragraph"]  # the finest level a bead was reviewed at

# The books API (/api/v2; PLAN.md, "Book API: import and read")


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
    reviewed: bool  # reviewed at the sentence level
    review_level: ReviewLevel | None  # the finest level it was reviewed at
    turn_end: bool  # a turn ends after this bead
    paragraph_end: bool  # a paragraph ends after this bead
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
    level: ReviewLevel = "sentence"


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


class BookSearchCount(BaseModel):
    book_id: str
    title: str
    count: int


class BookSearchResult(BaseModel):
    bead_id: int
    book_id: str
    title: str
    position: int  # 1-based, in the book
    source: list[BookSearchSpan]
    target: list[BookSearchSpan]
    reviewed: bool
    review_level: ReviewLevel | None


class ContextBead(BaseModel):
    bead_id: int
    position: int  # 1-based, in the book
    source: str
    target: str
    reviewed: bool
    review_level: ReviewLevel | None
