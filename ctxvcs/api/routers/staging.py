import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ctxvcs.api.deps import require_member
from ctxvcs.store.db import get_session
from ctxvcs.store.models import Conflict, Job, Member, MergeRequest, StagedEntries
from ctxvcs.store.repo_ops import current_schema
from ctxvcs.tasks import runner

router = APIRouter()


class StageBody(BaseModel):
    parent_commit: str | None = None
    entries: list[dict]
    session_summary: str = ""


class CommitBody(BaseModel):
    resolutions: list[dict] = []  # [{conflict_id, decision: {action, edited?}}]


@router.post("/repos/{r}/stage")
def post_stage(
    r: uuid.UUID,
    body: StageBody,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    member: Member = Depends(require_member),
):
    """Two-phase push, phase 1 (§ Core 7): dry-run — writes nothing to master."""
    if not body.entries:
        raise HTTPException(422, "entries must be non-empty")
    job_id = runner.enqueue(
        session,
        "stage",
        {
            "repo_id": str(r),
            "author": member.principal,
            "raw_entries": body.entries,
            "session_summary": body.session_summary,
            "parent_commit": body.parent_commit,
        },
    )
    background.add_task(runner.execute, job_id)
    return {"job_id": str(job_id)}


@router.get("/jobs/{job_id}")
def get_job(
    job_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    # jobs are repo-scoped through their payload; membership is checked against it
    repo_id = uuid.UUID((job.payload or {})["repo_id"])
    from ctxvcs.api.deps import _token
    from ctxvcs.store.repo_ops import member_by_token

    if member_by_token(session, repo_id, _token(authorization)) is None:
        raise HTTPException(403, "not a member of this job's repo")
    return {
        "status": job.status,
        "kind": job.kind,
        **{k: (job.result or {}).get(k) for k in
           ("staging_id", "merge_status", "proposed_actions", "conflicts", "merge_request_id",
            "commit_hash", "written", "error")},
    }


def _staged_or_404(session: Session, r: uuid.UUID, staging_id: uuid.UUID) -> StagedEntries:
    staged = session.get(StagedEntries, staging_id)
    if staged is None or staged.repo_id != r:
        raise HTTPException(404, "no such staging")
    return staged


@router.get("/repos/{r}/staging")
def list_staging(r: uuid.UUID, session: Session = Depends(get_session),
                 _m: Member = Depends(require_member)):
    rows = session.execute(
        select(StagedEntries).where(StagedEntries.repo_id == r)
        .order_by(StagedEntries.created_at.desc()).limit(50)
    ).scalars()
    return {
        "staging": [
            {
                "staging_id": str(s.id), "author": s.author, "status": s.status,
                "session_summary": s.session_summary, "parent_commit": s.parent_commit,
                "n_entries": len(s.entries or []),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ]
    }


@router.get("/repos/{r}/staging/{staging_id}")
def get_staging(r: uuid.UUID, staging_id: uuid.UUID, session: Session = Depends(get_session),
                _m: Member = Depends(require_member)):
    staged = _staged_or_404(session, r, staging_id)
    mr = session.execute(
        select(MergeRequest).where(MergeRequest.staging_id == staged.id)
    ).scalar_one_or_none()
    conflicts = []
    if mr is not None:
        conflicts = [
            _conflict_json(session, c)
            for c in session.execute(
                select(Conflict).where(Conflict.merge_request_id == mr.id)
            ).scalars()
        ]
    return {
        "staging_id": str(staged.id),
        "author": staged.author,
        "status": staged.status,
        "parent_commit": staged.parent_commit,
        "session_summary": staged.session_summary,
        "entries": [{k: v for k, v in e.items() if k != "embedding"} for e in staged.entries],
        "proposed_actions": staged.proposed_actions,
        "merge_request_id": str(mr.id) if mr else None,
        "conflicts": conflicts,
    }


def _conflict_json(session: Session, c: Conflict) -> dict:
    from ctxvcs.store.models import EntryRow

    existing = session.get(EntryRow, c.existing_content_hash) if c.existing_content_hash else None
    return {
        "conflict_id": str(c.id),
        "subject_key": c.subject_key,
        "relation": c.relation,
        "confidence": c.confidence,
        "conflicting_fields": c.conflicting_fields or [],
        "proposed_resolution": c.proposed_resolution,
        "status": c.status,
        "existing_commit": c.existing_commit,
        "existing": None if existing is None else {
            "content_hash": existing.content_hash, "type": existing.type,
            "fields": existing.fields, "body": existing.body,
            "provenance": existing.provenance,
        },
        "incoming": None if c.incoming is None else
        {k: v for k, v in c.incoming.items() if k != "embedding"},
    }


@router.post("/repos/{r}/staging/{staging_id}/commit")
def post_commit(
    r: uuid.UUID,
    staging_id: uuid.UUID,
    body: CommitBody,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    member: Member = Depends(require_member),
):
    """Two-phase push, phase 2 (§ Core 7): finalize via the §4.3 transaction."""
    staged = _staged_or_404(session, r, staging_id)
    if staged.status != "pending":
        raise HTTPException(409, f"staging is {staged.status}")
    resolutions = {res["conflict_id"]: res["decision"] for res in body.resolutions}
    state = _commit_and_compile(session, background, r, staging_id, resolutions)
    return state


def _commit_and_compile(session: Session, background: BackgroundTasks, r: uuid.UUID,
                        staging_id: uuid.UUID, resolutions: dict) -> dict:
    from ctxvcs.pipeline.graph import PipelineContext, run_commit

    changed_box: list = []
    ctx = PipelineContext(
        session=session,
        embedder=None,  # commit path never re-embeds
        reconciler=None,  # commit path never re-classifies
        entry_types=current_schema(session, r).entry_types,
        after_commit=lambda commit_hash, changed: changed_box.append((commit_hash, changed)),
    )
    state = run_commit(ctx, staging_id, resolutions)
    if state.get("merge_status") == "committed" and changed_box:
        commit_hash, changed = changed_box[0]
        job_id = runner.enqueue(session, "compile",
                                {"repo_id": str(r), "changed": [str(x) for x in changed]})
        background.add_task(runner.execute, job_id)
    if state.get("merge_status") == "error":
        raise HTTPException(409, state.get("error") or {"detail": "commit failed"})
    return {
        "merge_status": state.get("merge_status"),
        "commit_hash": state.get("commit_hash"),
        "merge_request_id": state.get("merge_request_id"),
    }
