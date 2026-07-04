"""Repo lifecycle, membership/tokens, schema versions, subject registry."""

import hashlib
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ctxvcs.config import settings
from ctxvcs.core.default_schema import DEFAULT_ENTRY_TYPES
from ctxvcs.store.models import EntryRow, MasterEntry, Member, Ref, Repo, SchemaVersion


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token() -> str:
    return secrets.token_urlsafe(settings().token_bytes)


def create_repo(session: Session, name: str, owner: str) -> tuple[Repo, str]:
    repo = Repo(id=uuid.uuid4(), name=name, owner=owner)
    session.add(repo)
    session.flush()  # child rows below FK-reference the repo; no relationships mapped
    token = issue_token()
    session.add(Member(repo_id=repo.id, principal=owner, role="owner", api_token_hash=hash_token(token)))
    session.add(SchemaVersion(repo_id=repo.id, version=1, entry_types=DEFAULT_ENTRY_TYPES))
    session.add(Ref(repo_id=repo.id, name="master", commit_hash=None, protected=True))
    session.flush()
    return repo, token


def add_member(session: Session, repo_id: uuid.UUID, principal: str, role: str) -> str:
    token = issue_token()
    existing = session.get(Member, (repo_id, principal))
    if existing:
        existing.role = role
        existing.api_token_hash = hash_token(token)
    else:
        session.add(Member(repo_id=repo_id, principal=principal, role=role, api_token_hash=hash_token(token)))
    session.flush()
    return token


def member_by_token(session: Session, repo_id: uuid.UUID, token: str) -> Member | None:
    return session.execute(
        select(Member).where(Member.repo_id == repo_id, Member.api_token_hash == hash_token(token))
    ).scalar_one_or_none()


def current_schema(session: Session, repo_id: uuid.UUID) -> SchemaVersion:
    return session.execute(
        select(SchemaVersion)
        .where(SchemaVersion.repo_id == repo_id)
        .order_by(SchemaVersion.version.desc())
        .limit(1)
    ).scalar_one()


def add_schema_version(session: Session, repo_id: uuid.UUID, entry_types: dict) -> int:
    cur = current_schema(session, repo_id)
    merged = {**cur.entry_types, **entry_types}  # extend-or-override semantics (§3)
    v = cur.version + 1
    session.add(SchemaVersion(repo_id=repo_id, version=v, entry_types=merged))
    session.flush()
    return v


def subject_registry(session: Session, repo_id: uuid.UUID) -> list[dict]:
    """Distinct subject_key over master_entries with entry counts (§9).
    The skill consults this before naming subjects — reuse makes reconciliation fire."""
    rows = session.execute(
        select(EntryRow.subject_key, func.count().label("n"))
        .select_from(MasterEntry)
        .join(EntryRow, EntryRow.content_hash == MasterEntry.content_hash)
        .where(MasterEntry.repo_id == repo_id)
        .group_by(EntryRow.subject_key)
        .order_by(func.count().desc(), EntryRow.subject_key)
    ).all()
    return [{"subject_key": r.subject_key, "entries": r.n} for r in rows]
