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


class PairUpdate(BaseModel):
    source_html: str | None = None
    target_html: str | None = None
    status: str | None = None


class PairResponse(BaseModel):
    id: str
    project_id: str
    position: int
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


class ImportPreview(BaseModel):
    source_paragraphs: list[ImportParagraph]
    target_paragraphs: list[ImportParagraph]
