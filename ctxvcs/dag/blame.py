"""M1 context blame (溯源, §9): for any entry on master — who says so, in what
capacity, and was it ever contested?

Pure read composition over records the write path already keeps: entry provenance
(author/origin/session), the commit_entries version chain, staged routing actions
(how each version landed), and conflict rows (challenges + who decided). No schema
change; deterministic (§12.5 — invariant tests, never an LLM judge).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ctxvcs.dag.trees import entry_history
from ctxvcs.store.models import Conflict, EntryRow, MergeRequest, StagedEntries


def blame_entry(session: Session, repo_id: uuid.UUID, entry_id: uuid.UUID) -> dict | None:
    chain = entry_history(session, repo_id, entry_id)  # newest version first
    if not chain:
        return None

    versions: list[dict] = []
    for link in chain:
        row = session.get(EntryRow, link["content_hash"])
        prov = row.provenance or {}
        v = {
            "content_hash": link["content_hash"],
            "commit": link["commit"],
            "committed_at": link["ts"],
            "type": row.type,
            "subject_key": row.subject_key,
            "fields": {k: val for k, val in (row.fields or {}).items() if k != "subject"},
            "body": row.body,
            "author": prov.get("author"),
            "origin": prov.get("origin"),
            "session_id": prov.get("session_id"),
            "ts": prov.get("ts"),
            "landed": _how_landed(session, repo_id, prov.get("session_id"), entry_id),
            "challenges": _challenges(session, repo_id, link["content_hash"]),
        }
        versions.append(v)

    current = versions[0]
    fields = {}
    for name, value in current["fields"].items():
        introduced = current
        for v in versions[1:]:  # walk back while the value is unchanged
            if v["fields"].get(name) != value:
                break
            introduced = v
        fields[name] = {
            "value": value,
            "introduced_in": {k: introduced[k] for k in
                              ("commit", "committed_at", "author", "origin", "session_id")},
        }

    return {
        "entry_id": str(entry_id),
        "subject_key": current["subject_key"],
        "type": current["type"],
        "versions": versions,
        "fields": fields,
    }


def _how_landed(session: Session, repo_id: uuid.UUID, session_id: str | None,
                entry_id: uuid.UUID) -> dict:
    """Recover the routing action that put this version on master, from the staged
    push (session_id == staging id) that carried it.

    Caveat: `entries` is a GLOBAL content-addressed store — identical content pushed
    first in another repo shares one row, whose provenance names that repo's staging.
    Within a repo this can't mislead (an identical re-push drops as duplicate), but
    across repos we must detect the foreign staging and degrade to `unknown` instead
    of attributing someone else's session."""
    if not session_id:
        return {"via": "unknown"}
    try:
        staged = session.get(StagedEntries, uuid.UUID(session_id))
    except ValueError:
        return {"via": "unknown"}
    if staged is None or staged.repo_id != repo_id:
        return {"via": "unknown", "note": "provenance recorded by another repo's push"} \
            if staged is not None else {"via": "unknown"}

    for a in staged.proposed_actions or []:
        is_adopting = a.get("target_entry_id") == str(entry_id)  # supersede/conflict adopt the target id
        is_fresh = a.get("action") in ("new", "keep") and a.get("temp_id") == str(entry_id)
        if not (is_adopting or is_fresh):
            continue
        if a["action"] == "conflict":
            c = _conflict_for(session, staged.id, a.get("temp_id"))
            out = {"via": "conflict_resolution", "relation": a.get("relation"),
                   "confidence": a.get("confidence")}
            if c is not None:
                pr = c.proposed_resolution or {}
                decision = pr.get("decision") or {}
                out |= {
                    "decided": pr.get("decided"),
                    "decided_by": decision.get("decided_by"),
                    "decision_note": decision.get("note"),
                    "conflicting_fields": c.conflicting_fields,
                    "rejected": _entry_brief(session, c.existing_content_hash),
                }
            return out
        if a["action"] == "supersede":
            return {"via": "supersede", "relation": a.get("relation"),
                    "confidence": a.get("confidence"), "rationale": a.get("rationale")}
        out = {"via": "new"}
        if a.get("downgraded_from"):
            out |= {"downgraded_from": a["downgraded_from"],
                    "kept_alongside": a.get("target_entry_id")}
        return out
    return {"via": "unknown"}


def _challenges(session: Session, repo_id: uuid.UUID, content_hash: str) -> list[dict]:
    """Conflicts in which this exact version was the EXISTING side — i.e. someone
    pushed a contradicting claim against it. Surviving a challenge is trust signal."""
    rows = session.execute(
        select(Conflict).where(Conflict.repo_id == repo_id,
                               Conflict.existing_content_hash == content_hash)
    ).scalars().all()
    out = []
    for c in rows:
        pr = c.proposed_resolution or {}
        decision = pr.get("decision") or {}
        incoming = c.incoming or {}
        prov = incoming.get("provenance") or {}
        challenger = prov.get("author")
        if not challenger and prov.get("session_id"):
            # per-entry author is stamped at commit; a rejected incoming never commits,
            # so recover the author from its staging row
            try:
                staged = session.get(StagedEntries, uuid.UUID(prov["session_id"]))
                challenger = staged.author if staged else None
            except ValueError:
                challenger = None
        out.append({
            "relation": c.relation,
            "status": c.status,
            "conflicting_fields": c.conflicting_fields,
            "challenger": challenger,
            "challenger_origin": prov.get("origin"),
            "challenged_fields": {k: v for k, v in (incoming.get("fields") or {}).items()
                                  if k in (c.conflicting_fields or [])},
            "decided": pr.get("decided"),
            "decided_by": decision.get("decided_by"),
            "decision_note": decision.get("note"),
        })
    return out


def _conflict_for(session: Session, staging_id: uuid.UUID, temp_id: str | None) -> Conflict | None:
    mr = session.execute(
        select(MergeRequest).where(MergeRequest.staging_id == staging_id)
    ).scalar_one_or_none()
    if mr is None:
        return None
    for c in session.execute(
        select(Conflict).where(Conflict.merge_request_id == mr.id)
    ).scalars():
        if (c.incoming or {}).get("id") == temp_id:
            return c
    return None


def _entry_brief(session: Session, content_hash: str | None) -> dict | None:
    if not content_hash:
        return None
    row = session.get(EntryRow, content_hash)
    if row is None:
        return None
    prov = row.provenance or {}
    return {"content_hash": content_hash, "type": row.type,
            "fields": {k: v for k, v in (row.fields or {}).items() if k != "subject"},
            "author": prov.get("author"), "origin": prov.get("origin"), "ts": prov.get("ts")}
