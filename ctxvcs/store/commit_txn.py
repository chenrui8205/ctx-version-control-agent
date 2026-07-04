"""§4.3 — a commit is exactly one Postgres transaction under the per-(repo, branch)
advisory lock. The ref/master_entries update is the durable commit point. Page
compilation is enqueued by the caller AFTER this transaction, never inside it.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from ctxvcs.dag.trees import compute_commit_hash, master_tree
from ctxvcs.store.models import (
    Commit,
    CommitEntry,
    CommitParent,
    Conflict,
    MergeRequest,
    Ref,
    StagedEntries,
)


class CommitError(Exception):
    pass


class StaleParentError(CommitError):
    """Master advanced since staging; M0 is linear — the session must re-stage."""


class ConflictsUnresolvedError(CommitError):
    def __init__(self, merge_request_id: uuid.UUID, open_conflicts: list[uuid.UUID]):
        self.merge_request_id = merge_request_id
        self.open_conflicts = open_conflicts
        super().__init__("unresolved contradicts block auto-merge (§ Core 8)")


@dataclass
class CommitResult:
    commit_hash: str
    changed_entry_ids: list[uuid.UUID] = field(default_factory=list)


def _acquire_branch_lock(session: Session, repo_id: uuid.UUID, branch: str = "master") -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:r), hashtext(:b))"),
        {"r": str(repo_id), "b": branch},
    )


def _upsert_entry(session: Session, e: dict, entry_id: uuid.UUID, repo_id: uuid.UUID) -> None:
    """Content-hash upsert (identical content ⇒ identical hash ⇒ stored once, §4.1)."""
    session.execute(
        text(
            """
            INSERT INTO entries (content_hash, repo_id, entry_id, type, fields, body,
                                 subject_key, embedding, access_labels, provenance)
            VALUES (:ch, :repo, :eid, :type, :fields, :body, :sk, :emb, :labels, :prov)
            ON CONFLICT (content_hash) DO NOTHING
            """
        ),
        {
            "ch": e["content_hash"],
            "repo": str(repo_id),
            "eid": str(entry_id),
            "type": e["type"],
            "fields": _json(e["fields"]),
            "body": e["body"],
            "sk": e["subject_key"],
            "emb": str(e["embedding"]) if e.get("embedding") else None,
            "labels": e.get("access_labels", []),
            "prov": _json(e.get("provenance", {})),
        },
    )


def _json(obj) -> str:
    import json

    return json.dumps(obj)


def _mark_superseded(session: Session, old_hash: str, new_hash: str, commit_hash: str) -> None:
    session.execute(
        text(
            """
            UPDATE entries SET provenance = provenance ||
              jsonb_build_object('superseded_by',
                jsonb_build_object('content_hash', CAST(:new AS text), 'commit', CAST(:commit AS text)))
            WHERE content_hash = :old
            """
        ),
        {"new": new_hash, "commit": commit_hash, "old": old_hash},
    )


def commit_staged(
    session: Session,
    staged: StagedEntries,
    resolutions: dict[str, dict] | None = None,
    failpoint: Callable[[str], None] | None = None,
) -> CommitResult:
    """Execute the routing-table actions recorded at stage time as one transaction.

    resolutions: {conflict_id: {"action": "keep_incoming"|"keep_existing"|"edit",
                                "edited": {fields, body}?}}
    failpoint: test hook, called with a step name before each step.
    """
    resolutions = resolutions or {}
    repo_id = staged.repo_id
    fp = failpoint or (lambda _step: None)

    if session.in_transaction():
        session.rollback()  # discard any autobegun read-only state; §4.3 owns the txn

    with session.begin():
        _acquire_branch_lock(session, repo_id)

        ref = session.execute(
            select(Ref).where(Ref.repo_id == repo_id, Ref.name == "master").with_for_update()
        ).scalar_one()
        if (staged.parent_commit or None) != (ref.commit_hash or None):
            raise StaleParentError(f"staged against {staged.parent_commit}, HEAD is {ref.commit_hash}")

        # resolve conflicts recorded at stage time
        mr = session.execute(
            select(MergeRequest).where(MergeRequest.staging_id == staged.id)
        ).scalar_one_or_none()
        conflict_rows: list[Conflict] = []
        if mr is not None:
            conflict_rows = list(
                session.execute(select(Conflict).where(Conflict.merge_request_id == mr.id)).scalars()
            )
        by_temp: dict[str, Conflict] = {}
        unresolved: list[uuid.UUID] = []
        for c in conflict_rows:
            temp_id = (c.incoming or {}).get("id")
            if temp_id:
                by_temp[temp_id] = c
            stored = (c.proposed_resolution or {}).get("decision")
            if c.status == "open" and str(c.id) not in resolutions and not stored:
                unresolved.append(c.id)
        if unresolved:
            raise ConflictsUnresolvedError(mr.id, unresolved)

        entries_by_id = {e["id"]: e for e in staged.entries}
        old_tree = master_tree(session, repo_id)
        new_tree = dict(old_tree)
        inserts: list[tuple[dict, uuid.UUID]] = []  # (entry json, permanent id)
        supersessions: list[tuple[str, str]] = []  # (old_hash, new_hash)
        changed: list[uuid.UUID] = []

        for action in staged.proposed_actions or []:
            e = entries_by_id.get(action["temp_id"])
            act = action["action"]
            if act == "conflict":
                c = by_temp.get(action["temp_id"])
                res = None
                if c is not None:
                    res = resolutions.get(str(c.id)) or (c.proposed_resolution or {}).get("decision")
                decision = (res or {}).get("action", "keep_existing")
                if c is not None:
                    c.status = "resolved"
                    c.proposed_resolution = {**(c.proposed_resolution or {}), "decided": decision}
                if decision == "keep_existing":
                    continue
                if decision == "edit" and res and res.get("edited"):
                    from ctxvcs.core.canonical import content_hash as chash

                    e = dict(e)
                    e["fields"] = res["edited"].get("fields", e["fields"])
                    e["body"] = res["edited"].get("body", e["body"])
                    e["content_hash"] = chash(e["type"], e["fields"], e["body"])
                act = "supersede"  # keep_incoming/edit ⇒ supersede the existing entry
            if e is None:
                continue

            if act in ("new", "keep"):
                # unrelated/complementary ⇒ fresh permanent id (adopts the transient id, § Core 9)
                eid = uuid.UUID(e["id"])
                new_tree[eid] = e["content_hash"]
                inserts.append((e, eid))
                changed.append(eid)
            elif act == "supersede":
                eid = uuid.UUID(action["target_entry_id"])  # adopts the existing entry_id
                old_hash = new_tree.get(eid)
                if old_hash == e["content_hash"]:
                    continue  # no-op version
                new_tree[eid] = e["content_hash"]
                inserts.append((e, eid))
                if old_hash:
                    supersessions.append((old_hash, e["content_hash"]))
                changed.append(eid)
            elif act == "drop":
                continue

        if not changed:
            raise CommitError("empty commit: no entries would change master")

        created_at = datetime.now(UTC)
        commit_hash = compute_commit_hash(
            repo_id, ref.commit_hash, new_tree, staged.session_summary or "", staged.author,
            staged.id, created_at,
        )

        fp("entries")
        # 1. content-hash upsert of new entry versions
        for e, eid in inserts:
            prov = dict(e.get("provenance") or {})
            prov.setdefault("author", staged.author)
            prov.setdefault("session_id", str(staged.id))
            e = {**e, "provenance": prov}
            _upsert_entry(session, e, eid, repo_id)
        for old_hash, new_hash in supersessions:
            _mark_superseded(session, old_hash, new_hash, commit_hash)

        fp("commit_row")
        # 2. commit row + parent edge
        session.add(
            Commit(
                hash=commit_hash, repo_id=repo_id, author=staged.author,
                message=staged.session_summary or "", session_id=staged.id, created_at=created_at,
            )
        )
        session.flush()
        if ref.commit_hash:
            session.add(CommitParent(commit_hash=commit_hash, parent_hash=ref.commit_hash))

        fp("tree")
        # 3. full commit_entries tree
        session.bulk_save_objects(
            [CommitEntry(commit_hash=commit_hash, entry_id=k, content_hash=v) for k, v in new_tree.items()]
        )

        fp("master_entries")
        # 4. replace affected master_entries rows
        for eid in changed:
            session.execute(
                text(
                    """
                    INSERT INTO master_entries (repo_id, entry_id, content_hash)
                    VALUES (:r, :e, :c)
                    ON CONFLICT (repo_id, entry_id) DO UPDATE SET content_hash = EXCLUDED.content_hash
                    """
                ),
                {"r": str(repo_id), "e": str(eid), "c": new_tree[eid]},
            )

        fp("ref")
        # 5. advance the ref — the durable commit point
        session.execute(
            update(Ref)
            .where(Ref.repo_id == repo_id, Ref.name == "master")
            .values(commit_hash=commit_hash)
        )

        staged.status = "committed"
        if mr is not None:
            mr.status = "merged"

    return CommitResult(commit_hash=commit_hash, changed_entry_ids=changed)
