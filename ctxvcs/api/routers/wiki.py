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


@router.get("/repos/{r}/context")
def context_bundle(r: uuid.UUID, session: Session = Depends(get_session),
                   _m: Member = Depends(require_member)):
    """M1 one-shot bundle (`ctxvcs pull`, §9): open-threads + the last few journal
    sessions + the index, as one paste-able markdown document. Same navigational read
    path as a session start (§8), bundled."""
    from ctxvcs.config import settings

    ot = serve_page(session, r, "open-threads")
    journal = serve_page(session, r, "journal")
    index = serve_page(session, r, "index")
    if ot is None or journal is None:
        raise HTTPException(404, "pages not compiled yet")

    # trim the journal to the newest K session blocks (it's newest-first by construction)
    k = settings().context_journal_sessions
    parts = journal["content"].split("\n## ")
    trimmed = parts[0] + "".join(f"\n## {p}" for p in parts[1: 1 + k])

    content = "\n\n---\n\n".join([
        "# Team context bundle\n\nRead open threads first (what to pick up), then the "
        "recent sessions (what just happened). Fetch subject pages for depth.",
        ot["content"],
        trimmed,
        index["content"] if index else "",
    ])
    return {"content": content, "as_of_commit": ot.get("as_of_commit") or ot.get("source_commit")}


@router.get("/repos/{r}/subjects/{subject_key}/entries")
def subject_entries(r: uuid.UUID, subject_key: str, session: Session = Depends(get_session),
                    _m: Member = Depends(require_member)):
    """Current master entries for one subject — the blame panel/CLI's entry picker."""
    from sqlalchemy import text

    rows = session.execute(text(
        """
        SELECT m.entry_id::text AS entry_id, e.type, e.fields, left(e.body, 160) AS gist
        FROM master_entries m JOIN entries e ON e.content_hash = m.content_hash
        WHERE m.repo_id = :r AND e.subject_key = :sk
        ORDER BY e.type
        """), {"r": str(r), "sk": subject_key}).mappings()
    entries = [dict(x) for x in rows]
    if not entries:
        raise HTTPException(404, "no current entries for this subject")
    return {"subject_key": subject_key, "entries": entries}


@router.post("/repos/{r}/wiki/rebuild")
def wiki_rebuild(r: uuid.UUID, background: BackgroundTasks,
                 session: Session = Depends(get_session), _owner: Member = Depends(require_owner)):
    """Full rebuild is always safe — pages are a regenerable cache (§ Core 11)."""
    job_id = runner.enqueue(session, "rebuild", {"repo_id": str(r)})
    background.add_task(runner.execute, job_id)
    return {"job_id": str(job_id)}
