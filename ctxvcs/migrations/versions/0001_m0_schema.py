"""M0 schema — verbatim from spec §4.2 (write model + compiled read model).

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE repos (id UUID PRIMARY KEY, name TEXT, owner TEXT, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE members (repo_id UUID REFERENCES repos(id), principal TEXT, role TEXT, api_token_hash TEXT,
                      PRIMARY KEY (repo_id, principal));

CREATE TABLE schema_versions (
  repo_id UUID REFERENCES repos(id), version INT,
  entry_types JSONB NOT NULL,
  page_templates JSONB,
  created_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (repo_id, version)
);

CREATE TABLE entries (
  content_hash TEXT PRIMARY KEY,
  repo_id UUID NOT NULL REFERENCES repos(id),
  entry_id UUID NOT NULL, type TEXT NOT NULL,
  fields JSONB NOT NULL, body TEXT NOT NULL, subject_key TEXT NOT NULL,
  embedding vector(1536), access_labels TEXT[] NOT NULL DEFAULT '{}', provenance JSONB NOT NULL
);
CREATE INDEX ON entries USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON entries (repo_id, subject_key);
CREATE INDEX ON entries (repo_id, entry_id);

CREATE TABLE commits (
  hash TEXT PRIMARY KEY, repo_id UUID REFERENCES repos(id),
  author TEXT, message TEXT NOT NULL,
  session_id UUID, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE commit_parents (commit_hash TEXT REFERENCES commits(hash), parent_hash TEXT REFERENCES commits(hash),
                             PRIMARY KEY (commit_hash, parent_hash));
CREATE TABLE commit_entries (commit_hash TEXT REFERENCES commits(hash), entry_id UUID, content_hash TEXT REFERENCES entries(content_hash),
                             PRIMARY KEY (commit_hash, entry_id));

CREATE TABLE master_entries (
  repo_id UUID REFERENCES repos(id), entry_id UUID NOT NULL,
  content_hash TEXT NOT NULL REFERENCES entries(content_hash),
  PRIMARY KEY (repo_id, entry_id)
);

CREATE TABLE refs (repo_id UUID REFERENCES repos(id), name TEXT, commit_hash TEXT REFERENCES commits(hash),
                   protected BOOLEAN DEFAULT false, PRIMARY KEY (repo_id, name));

CREATE TABLE jobs (id UUID PRIMARY KEY, kind TEXT, payload JSONB, status TEXT DEFAULT 'queued',
                   result JSONB, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ);

CREATE TABLE staged_entries (
  id UUID PRIMARY KEY,
  repo_id UUID REFERENCES repos(id), author TEXT,
  parent_commit TEXT, entries JSONB NOT NULL, proposed_actions JSONB,
  session_summary TEXT,
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE merge_requests (
  id UUID PRIMARY KEY, repo_id UUID REFERENCES repos(id), staging_id UUID REFERENCES staged_entries(id),
  origin TEXT DEFAULT 'push',
  status TEXT DEFAULT 'open', created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE conflicts (
  id UUID PRIMARY KEY, repo_id UUID REFERENCES repos(id), merge_request_id UUID REFERENCES merge_requests(id),
  subject_key TEXT NOT NULL,
  existing_content_hash TEXT REFERENCES entries(content_hash), incoming JSONB,
  existing_commit TEXT, relation TEXT NOT NULL,
  confidence REAL, conflicting_fields TEXT[], proposed_resolution JSONB, status TEXT DEFAULT 'open'
);

CREATE TABLE wiki_pages (
  page_id UUID PRIMARY KEY, repo_id UUID NOT NULL REFERENCES repos(id),
  kind TEXT NOT NULL,
  slug TEXT NOT NULL, subject_key TEXT,
  source_commit TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  content TEXT NOT NULL,
  sections JSONB NOT NULL,
  outbound_links TEXT[] NOT NULL DEFAULT '{}',
  fts tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  compiled_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (repo_id, slug)
);
CREATE INDEX ON wiki_pages USING gin (fts);
CREATE INDEX ON wiki_pages (repo_id, subject_key);

CREATE TABLE page_inputs (
  page_id UUID REFERENCES wiki_pages(page_id) ON DELETE CASCADE,
  entry_id UUID NOT NULL, PRIMARY KEY (page_id, entry_id)
);
CREATE INDEX ON page_inputs (entry_id);
"""


def upgrade() -> None:
    for stmt in DDL.split(";"):
        if stmt.strip():
            op.execute(stmt)


def downgrade() -> None:
    for tbl in [
        "page_inputs", "wiki_pages", "conflicts", "merge_requests", "staged_entries",
        "jobs", "refs", "master_entries", "commit_entries", "commit_parents", "commits",
        "entries", "schema_versions", "members", "repos",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
