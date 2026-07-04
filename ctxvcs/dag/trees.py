"""Tree ops + diff over the commit DAG (linear in M0; LCA/merge-base lands M2)."""

import hashlib
import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ctxvcs.store.models import Commit, CommitEntry, CommitParent, MasterEntry, Ref

Tree = dict[uuid.UUID, str]  # entry_id -> content_hash (the git filename->blob map, §Core 1)


def head_commit(session: Session, repo_id: uuid.UUID, ref: str = "master") -> str | None:
    row = session.get(Ref, (repo_id, ref))
    return row.commit_hash if row else None


def master_tree(session: Session, repo_id: uuid.UUID) -> Tree:
    rows = session.execute(
        select(MasterEntry.entry_id, MasterEntry.content_hash).where(MasterEntry.repo_id == repo_id)
    ).all()
    return {r.entry_id: r.content_hash for r in rows}


def commit_tree(session: Session, commit_hash: str) -> Tree:
    rows = session.execute(
        select(CommitEntry.entry_id, CommitEntry.content_hash).where(CommitEntry.commit_hash == commit_hash)
    ).all()
    return {r.entry_id: r.content_hash for r in rows}


def diff_trees(a: Tree, b: Tree) -> dict[str, list[uuid.UUID]]:
    """Map symmetric difference (§9 /diff): a -> b."""
    added = [k for k in b if k not in a]
    removed = [k for k in a if k not in b]
    modified = [k for k in b if k in a and a[k] != b[k]]
    return {"added": added, "removed": removed, "modified": modified}


def compute_commit_hash(
    repo_id: uuid.UUID,
    parent: str | None,
    tree: Tree,
    message: str,
    author: str | None,
    session_id: uuid.UUID | None,
    created_at: datetime,
) -> str:
    payload = json.dumps(
        {
            "repo": str(repo_id),
            "parent": parent,
            "tree": sorted((str(k), v) for k, v in tree.items()),
            "message": message,
            "author": author,
            "session": str(session_id) if session_id else None,
            "ts": created_at.isoformat(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def walk_history(session: Session, repo_id: uuid.UUID, limit: int | None = None) -> list[Commit]:
    """HEAD-back linear walk, newest first."""
    out: list[Commit] = []
    h = head_commit(session, repo_id)
    while h and (limit is None or len(out) < limit):
        c = session.get(Commit, h)
        if c is None:
            break
        out.append(c)
        parent = session.execute(
            select(CommitParent.parent_hash).where(CommitParent.commit_hash == h)
        ).scalar_one_or_none()
        h = parent
    return out


def entry_history(session: Session, repo_id: uuid.UUID, entry_id: uuid.UUID) -> list[dict]:
    """Superseded chain for a stable entry_id (§9), newest version first."""
    chain: list[dict] = []
    for c in walk_history(session, repo_id):
        ch = session.execute(
            select(CommitEntry.content_hash).where(
                CommitEntry.commit_hash == c.hash, CommitEntry.entry_id == entry_id
            )
        ).scalar_one_or_none()
        if ch is None:
            continue
        if not chain or chain[-1]["content_hash"] != ch:
            chain.append(
                {
                    "content_hash": ch,
                    "commit": c.hash,
                    "author": c.author,
                    "ts": c.created_at.isoformat() if c.created_at else None,
                }
            )
        else:
            # same version introduced earlier — update the introducing commit
            chain[-1]["commit"] = c.hash
    return chain
