import re
from typing import Literal

from fastapi import APIRouter, Request

from tradurre.models import SearchResponse, SearchResult

router = APIRouter(tags=["search"])


def _fts5_escape(query: str) -> str:
    """Escape a user query for safe FTS5 MATCH usage.

    Wraps each word in double quotes to prevent FTS5 syntax errors
    from special characters while still allowing multi-word searches.
    """
    words = query.strip().split()
    return " ".join(f'"{w}"' for w in words if w)


@router.get("/search", response_model=SearchResponse)
def search_translation_memory(
    request: Request,
    q: str,
    lang: Literal["source", "target", "both"] = "both",
    project_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    db = request.app.state.db
    escaped = _fts5_escape(q)
    if not escaped:
        return SearchResponse(query=q, total=0, results=[])

    if lang == "source":
        match_expr = f"source_text:{escaped}"
    elif lang == "target":
        match_expr = f"target_text:{escaped}"
    else:
        match_expr = escaped

    # Count query (no snippet calls, simpler)
    count_sql = """
        SELECT COUNT(*)
        FROM translation_memory
        WHERE translation_memory MATCH ?
    """
    count_params: list = [match_expr]
    if project_id:
        count_sql += " AND project_id = ?"
        count_params.append(project_id)
    total = db.execute(count_sql, count_params).fetchone()[0]

    # Results query with snippets
    sql = """
        SELECT
            translation_memory.pair_id,
            translation_memory.project_id,
            p.title as project_title,
            snippet(translation_memory, 0, '<mark>', '</mark>', '...', 16) as source_snippet,
            snippet(translation_memory, 1, '<mark>', '</mark>', '...', 16) as target_snippet,
            pairs.position,
            rank
        FROM translation_memory
        JOIN projects p ON p.id = translation_memory.project_id
        JOIN pairs ON pairs.id = translation_memory.pair_id
        WHERE translation_memory MATCH ?
    """
    params: list = [match_expr]

    if project_id:
        sql += " AND translation_memory.project_id = ?"
        params.append(project_id)

    sql += " ORDER BY rank LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(sql, params).fetchall()
    results = [
        SearchResult(
            pair_id=r["pair_id"],
            project_id=r["project_id"],
            project_title=r["project_title"],
            source_snippet=r["source_snippet"],
            target_snippet=r["target_snippet"],
            position=r["position"],
        )
        for r in rows
    ]

    return SearchResponse(query=q, total=total, results=results)
