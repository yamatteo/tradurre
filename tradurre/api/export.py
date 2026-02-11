from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from tradurre.services.exporter import export_docx, export_txt

router = APIRouter(tags=["export"])


@router.get("/projects/{project_id}/export")
def export_project(
    project_id: str,
    request: Request,
    format: str = Query(..., pattern="^(docx|txt)$"),
    mode: str = Query("target", pattern="^(source|target|parallel)$"),
):
    db = request.app.state.db
    proj = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    pairs = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM pairs WHERE project_id = ? ORDER BY position",
            (project_id,),
        ).fetchall()
    ]

    title = proj["title"].replace(" ", "_")

    if format == "docx":
        content = export_docx(pairs, mode)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{title}_{mode}.docx"'},
        )
    else:
        content = export_txt(pairs, mode)
        return Response(
            content=content.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{title}_{mode}.txt"'},
        )
