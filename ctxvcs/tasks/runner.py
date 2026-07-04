"""M0 job runner: Postgres `jobs` table + in-process execution (single worker is
sufficient for session-sized pushes, §1). Celery/Redis swap-in is M1."""

import traceback
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ctxvcs.config import settings
from ctxvcs.pipeline.graph import PipelineContext, run_commit, run_stage
from ctxvcs.store.db import session_factory
from ctxvcs.store.models import Job
from ctxvcs.store.repo_ops import current_schema


def build_context(session: Session, repo_id: uuid.UUID) -> PipelineContext:
    from ctxvcs.embed import get_embedder
    from ctxvcs.llm.claude import ClaudeReconcileClient

    return PipelineContext(
        session=session,
        embedder=get_embedder(),
        reconciler=ClaudeReconcileClient(),
        entry_types=current_schema(session, repo_id).entry_types,
        cfg=settings(),
        after_commit=lambda commit_hash, changed: run_compile(session, repo_id, changed),
    )


def run_compile(session: Session, repo_id: uuid.UUID, changed: list[uuid.UUID] | None) -> list[str]:
    """Page compilation runs after and outside the commit transaction (§4.3)."""
    from ctxvcs.compiler.build import compile_pages

    return compile_pages(session, repo_id, changed)


def enqueue(session: Session, kind: str, payload: dict) -> uuid.UUID:
    job = Job(id=uuid.uuid4(), kind=kind, payload=payload, status="queued")
    session.add(job)
    session.commit()
    return job.id


def execute(job_id: uuid.UUID) -> None:
    """Runs in a FastAPI background task with its own session."""
    with session_factory()() as session:
        job = session.get(Job, job_id)
        if job is None or job.status not in ("queued",):
            return
        job.status = "running"
        job.updated_at = datetime.now(UTC)
        session.commit()
        try:
            result = _dispatch(session, job)
            job.status = "done"
            job.result = result
        except Exception:
            session.rollback()
            job = session.get(Job, job_id)
            job.status = "error"
            job.result = {"error": traceback.format_exc(limit=8)}
        job.updated_at = datetime.now(UTC)
        session.commit()


def _dispatch(session: Session, job: Job) -> dict:
    p = job.payload or {}
    repo_id = uuid.UUID(p["repo_id"])
    if job.kind == "stage":
        ctx = build_context(session, repo_id)
        state = run_stage(
            ctx, repo_id, p["author"], p["raw_entries"], p.get("session_summary") or "",
            p.get("parent_commit"),
        )
        return {
            "staging_id": state.get("staging_id"),
            "merge_status": state.get("merge_status"),
            "proposed_actions": state.get("proposed_actions"),
            "conflicts": state.get("conflicts"),
            "merge_request_id": state.get("merge_request_id"),
            "error": state.get("error"),
        }
    if job.kind == "commit":
        ctx = build_context(session, repo_id)
        state = run_commit(ctx, uuid.UUID(p["staging_id"]), p.get("resolutions"))
        return {k: state.get(k) for k in ("merge_status", "commit_hash", "merge_request_id", "error")}
    if job.kind == "compile":
        changed = [uuid.UUID(x) for x in p.get("changed") or []] or None
        written = run_compile(session, repo_id, changed)
        return {"written": written}
    if job.kind == "rebuild":
        written = run_compile(session, repo_id, None)
        return {"written": written}
    raise ValueError(f"unknown job kind {job.kind!r}")
