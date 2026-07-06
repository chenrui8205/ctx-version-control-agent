"""SQLAlchemy models mirroring the §4.2 DDL. The Alembic migration owns the DDL
(including the HNSW index and generated tsvector column); these models exist for ORM access.

Caveats encoded here:
- `entries` is a global content-addressed store keyed by content_hash. Within a repo,
  entry identity is always resolved via master_entries / commit_entries, never via
  entries.entry_id (which records the first writer only).
- Never put an is_current flag on entries — "current" is branch-relative (§4.2).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ctxvcs.config import settings


class Base(DeclarativeBase):
    pass


def _uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Repo(Base):
    __tablename__ = "repos"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class Member(Base):
    __tablename__ = "members"
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"), primary_key=True)
    principal: Mapped[str] = mapped_column(Text, primary_key=True)
    role: Mapped[str | None] = mapped_column(Text)
    api_token_hash: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)  # M1 self-serve accounts
    display_name: Mapped[str | None] = mapped_column(Text)


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_types: Mapped[dict] = mapped_column(JSONB, nullable=False)
    page_templates: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class EntryRow(Base):
    __tablename__ = "entries"
    content_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(Vector(settings().embed_dim))
    access_labels: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Commit(Base):
    __tablename__ = "commits"
    hash: Mapped[str] = mapped_column(Text, primary_key=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"))
    author: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)  # message = session summary
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class CommitParent(Base):
    __tablename__ = "commit_parents"
    commit_hash: Mapped[str] = mapped_column(Text, ForeignKey("commits.hash"), primary_key=True)
    parent_hash: Mapped[str] = mapped_column(Text, ForeignKey("commits.hash"), primary_key=True)


class CommitEntry(Base):
    __tablename__ = "commit_entries"
    commit_hash: Mapped[str] = mapped_column(Text, ForeignKey("commits.hash"), primary_key=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    content_hash: Mapped[str] = mapped_column(Text, ForeignKey("entries.content_hash"), nullable=False)


class MasterEntry(Base):
    __tablename__ = "master_entries"
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"), primary_key=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    content_hash: Mapped[str] = mapped_column(Text, ForeignKey("entries.content_hash"), nullable=False)


class Ref(Base):
    __tablename__ = "refs"
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    commit_hash: Mapped[str | None] = mapped_column(Text, ForeignKey("commits.hash"))
    protected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class StagedEntries(Base):
    __tablename__ = "staged_entries"
    id: Mapped[uuid.UUID] = _uuid_pk()  # the session id
    repo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"))
    author: Mapped[str | None] = mapped_column(Text)
    parent_commit: Mapped[str | None] = mapped_column(Text)
    entries: Mapped[list] = mapped_column(JSONB, nullable=False)
    proposed_actions: Mapped[list | None] = mapped_column(JSONB)
    session_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))  # pending|committed|discarded
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class MergeRequest(Base):
    __tablename__ = "merge_requests"
    id: Mapped[uuid.UUID] = _uuid_pk()
    repo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"))
    staging_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("staged_entries.id"))
    origin: Mapped[str] = mapped_column(Text, server_default=text("'push'"))  # push | lint (M1)
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class Conflict(Base):
    __tablename__ = "conflicts"
    id: Mapped[uuid.UUID] = _uuid_pk()
    repo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"))
    merge_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merge_requests.id")
    )
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    existing_content_hash: Mapped[str | None] = mapped_column(Text, ForeignKey("entries.content_hash"))
    incoming: Mapped[dict | None] = mapped_column(JSONB)
    existing_commit: Mapped[str | None] = mapped_column(Text)
    relation: Mapped[str] = mapped_column(Text, nullable=False)  # 'contradicts'
    confidence: Mapped[float | None] = mapped_column(Float)
    conflicting_fields: Mapped[list | None] = mapped_column(ARRAY(Text))
    proposed_resolution: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))


class WikiPage(Base):
    __tablename__ = "wiki_pages"
    page_id: Mapped[uuid.UUID] = _uuid_pk()
    repo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # index|open_threads|journal|subject
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    subject_key: Mapped[str | None] = mapped_column(Text)
    source_commit: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[list] = mapped_column(JSONB, nullable=False)
    outbound_links: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'"))
    # fts is a generated column (migration DDL); not mapped for ORM writes
    compiled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))


class PageInput(Base):
    __tablename__ = "page_inputs"
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_pages.page_id", ondelete="CASCADE"), primary_key=True
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
