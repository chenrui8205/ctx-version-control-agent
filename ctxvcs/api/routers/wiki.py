import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ctxvcs.api.deps import require_member, require_owner
from ctxvcs.compiler.build import search_pages, serve_page
from ctxvcs.store.db import get_session
from ctxvcs.store.models import Member
from ctxvcs.tasks import runner

router = APIRouter()


@router.get("/repos/{r}/wiki/index")
def wiki_index(r: uuid.UUID, session: Session = Depends(get_session),
               _m: Member = Depends(require_member)):
    page = serve_page(session, r, "index")
    if page is None:
        raise HTTPException(404, "index not compiled yet")
    return page


@router.get("/repos/{r}/wiki/page/{slug}")
def wiki_page(r: uuid.UUID, slug: str, section: str | None = None,
              session: Session = Depends(get_session), _m: Member = Depends(require_member)):
    page = serve_page(session, r, slug, section)
    if page is None:
        raise HTTPException(404, "no such page or section")
    return page


@router.get("/repos/{r}/wiki/search")
def wiki_search(r: uuid.UUID, q: str, k: int = 10,
                session: Session = Depends(get_session), _m: Member = Depends(require_member)):
    return {"results": search_pages(session, r, q, k)}


@router.post("/repos/{r}/wiki/rebuild")
def wiki_rebuild(r: uuid.UUID, background: BackgroundTasks,
                 session: Session = Depends(get_session), _owner: Member = Depends(require_owner)):
    """Full rebuild is always safe — pages are a regenerable cache (§ Core 11)."""
    job_id = runner.enqueue(session, "rebuild", {"repo_id": str(r)})
    background.add_task(runner.execute, job_id)
    return {"job_id": str(job_id)}
