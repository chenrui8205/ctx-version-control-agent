import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ctxvcs.api.deps import require_member
from ctxvcs.dag.trees import commit_tree, diff_trees, entry_history, walk_history
from ctxvcs.store.db import get_session
from ctxvcs.store.models import Commit, Member

router = APIRouter()


@router.get("/repos/{r}/commits")
def list_commits(r: uuid.UUID, since: str | None = None,
                 session: Session = Depends(get_session), _m: Member = Depends(require_member)):
    """The session ledger (§ Core 2): the commit DAG doubles as who-did-what."""
    commits = walk_history(session, r)
    out = []
    for c in commits:
        ts = c.created_at.isoformat() if c.created_at else None
        if since and ts and ts < since:
            break
        out.append({"hash": c.hash, "author": c.author, "summary": c.message,
                    "session_id": str(c.session_id) if c.session_id else None, "ts": ts})
    return {"commits": out}


@router.get("/repos/{r}/commits/{commit_hash}")
def get_commit(r: uuid.UUID, commit_hash: str, session: Session = Depends(get_session),
               _m: Member = Depends(require_member)):
    c = session.get(Commit, commit_hash)
    if c is None or c.repo_id != r:
        raise HTTPException(404, "no such commit")
    tree = commit_tree(session, commit_hash)
    return {
        "commit": {"hash": c.hash, "author": c.author, "message": c.message,
                   "session_id": str(c.session_id) if c.session_id else None,
                   "ts": c.created_at.isoformat() if c.created_at else None},
        "tree": {str(k): v for k, v in tree.items()},
    }


@router.get("/repos/{r}/diff")
def get_diff(r: uuid.UUID, from_: str = Query(alias="from"), to: str = Query(...),
             session: Session = Depends(get_session), _m: Member = Depends(require_member)):
    a = commit_tree(session, from_) if from_ != "genesis" else {}
    b = commit_tree(session, to)
    d = diff_trees(a, b)
    return {k: [str(x) for x in v] for k, v in d.items()}


@router.get("/repos/{r}/entries/{entry_id}/history")
def get_history(r: uuid.UUID, entry_id: uuid.UUID, session: Session = Depends(get_session),
                _m: Member = Depends(require_member)):
    chain = entry_history(session, r, entry_id)
    if not chain:
        raise HTTPException(404, "unknown entry_id on this branch")
    # attach content for each version
    from ctxvcs.store.models import EntryRow

    for v in chain:
        row = session.get(EntryRow, v["content_hash"])
        if row is not None:
            v["type"] = row.type
            v["fields"] = row.fields
            v["body"] = row.body
            v["provenance"] = row.provenance
    return {"entry_id": str(entry_id), "versions": chain}


@router.get("/repos/{r}/entries/{entry_id}/blame")
def get_blame(r: uuid.UUID, entry_id: uuid.UUID, session: Session = Depends(get_session),
              _m: Member = Depends(require_member)):
    """M1 溯源 (§9): who says so, in what capacity, and was it ever contested —
    version chain + how each version landed + conflict challenges + per-field origin."""
    from ctxvcs.dag.blame import blame_entry

    out = blame_entry(session, r, entry_id)
    if out is None:
        raise HTTPException(404, "unknown entry_id on this branch")
    return out
