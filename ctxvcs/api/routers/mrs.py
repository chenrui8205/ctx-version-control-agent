import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ctxvcs.api.deps import require_member
from ctxvcs.api.routers.staging import _commit_and_compile, _conflict_json
from ctxvcs.store.db import get_session
from ctxvcs.store.models import Conflict, Member, MergeRequest, StagedEntries

router = APIRouter()


class ResolveBody(BaseModel):
    conflict_id: uuid.UUID
    decision: dict  # {"action": "keep_incoming"|"keep_existing"|"edit", "edited": {...}?}


@router.get("/repos/{r}/merge-requests")
def list_mrs(r: uuid.UUID, status: str | None = "open", session: Session = Depends(get_session),
             _m: Member = Depends(require_member)):
    q = select(MergeRequest).where(MergeRequest.repo_id == r).order_by(MergeRequest.created_at.desc())
    if status:
        q = q.where(MergeRequest.status == status)
    out = []
    for mr in session.execute(q.limit(50)).scalars():
        staged = session.get(StagedEntries, mr.staging_id)
        n = session.execute(
            select(Conflict).where(Conflict.merge_request_id == mr.id)
        ).scalars().all()
        out.append({
            "merge_request_id": str(mr.id), "staging_id": str(mr.staging_id),
            "origin": mr.origin, "status": mr.status,
            "created_at": mr.created_at.isoformat() if mr.created_at else None,
            "author": staged.author if staged else None,
            "session_summary": staged.session_summary if staged else None,
            "n_conflicts": len(n),
            "n_open": sum(1 for c in n if c.status == "open"),
        })
    return {"merge_requests": out}


@router.get("/repos/{r}/merge-requests/{mr_id}")
def get_mr(r: uuid.UUID, mr_id: uuid.UUID, session: Session = Depends(get_session),
           _m: Member = Depends(require_member)):
    mr = session.get(MergeRequest, mr_id)
    if mr is None or mr.repo_id != r:
        raise HTTPException(404, "no such merge request")
    staged = session.get(StagedEntries, mr.staging_id)
    conflicts = [
        _conflict_json(session, c)
        for c in session.execute(select(Conflict).where(Conflict.merge_request_id == mr.id)).scalars()
    ]
    return {
        "merge_request_id": str(mr.id), "staging_id": str(mr.staging_id),
        "origin": mr.origin, "status": mr.status,
        "author": staged.author if staged else None,
        "session_summary": staged.session_summary if staged else None,
        "parent_commit": staged.parent_commit if staged else None,
        "conflicts": conflicts,
    }


@router.post("/repos/{r}/merge-requests/{mr_id}/resolve")
def resolve(
    r: uuid.UUID,
    mr_id: uuid.UUID,
    body: ResolveBody,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    member: Member = Depends(require_member),
):
    """Record a human decision on one conflict; when every conflict is decided,
    the commit executes and master advances (§9)."""
    mr = session.get(MergeRequest, mr_id)
    if mr is None or mr.repo_id != r:
        raise HTTPException(404, "no such merge request")
    if mr.status != "open":
        raise HTTPException(409, f"merge request is {mr.status}")
    conflict = session.get(Conflict, body.conflict_id)
    if conflict is None or conflict.merge_request_id != mr.id:
        raise HTTPException(404, "no such conflict in this merge request")
    action = body.decision.get("action")
    if action not in ("keep_incoming", "keep_existing", "edit"):
        raise HTTPException(422, "decision.action must be keep_incoming | keep_existing | edit")

    conflict.proposed_resolution = {
        **(conflict.proposed_resolution or {}),
        "decision": {**body.decision, "decided_by": member.principal},
    }
    session.flush()

    undecided = session.execute(
        select(Conflict).where(
            Conflict.merge_request_id == mr.id,
            Conflict.status == "open",
        )
    ).scalars().all()
    undecided = [c for c in undecided if not (c.proposed_resolution or {}).get("decision")]
    if undecided:
        session.commit()
        return {"merge_request_id": str(mr.id), "status": "open",
                "remaining_conflicts": len(undecided)}

    session.commit()
    state = _commit_and_compile(session, background, r, mr.staging_id, {})
    return {"merge_request_id": str(mr.id), **state}
