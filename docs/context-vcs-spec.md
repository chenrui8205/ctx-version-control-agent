# Context VCS — Build Spec

Build a centralized, Git-like version control system for a team's **agent working context**. The unit of value is a working session: a developer spends hours with their agent, and the session produces decisions, research findings, state changes, open questions, and next steps. The platform lets each person push a distilled session, reconciles it against the team's current context (dedup, supersede, detect contradictions), maintains a canonical master, and compiles a readable working-state (journal, open threads, subject pages) so any teammate — or their agent — can pick up the work. This is **not** a general knowledge base or encyclopedia: pages exist only for subjects the team is actively working on, recency and supersession dominate, and the landing view is "what's open," not "what do we know."

Deliver **M0 first as a complete, running end-to-end platform** the team uses daily; M1 and M2 deepen it. Every section below tags milestone scope. Flag before deviating from any Core Decision.

## Core decisions

1. The unit of versioning is an **entry**, not a file. The store maps `entry_id → content_hash`, the way Git maps `filename → blob`.
2. **A push is a session.** `staging_id` identifies the session; the commit message is the skill-written session summary; every entry's provenance carries `session_id` and `origin: human | agent`. The commit DAG doubles as the team's session ledger.
3. Centralized, single canonical master. Client-server, no peer-to-peer, no CRDT. M0 history is **linear** (staging is the branch; the advisory lock makes every commit a fast-forward); branches/LCA arrive in M2 without schema changes.
4. Conflicts are semantic, not textual. Never line-diff to detect conflicts.
5. Dedup, merge, and conflict detection are **one relation classifier** (`reconcile_vs_master`), not separate passes. See §6.
6. The write path is a **skill that runs in the developer's agent session**. The platform never runs extraction; it receives already-structured candidate entries. The skill must consult the **subject registry** before naming subjects — subject reuse is what makes reconciliation fire. See §8.
7. Push is two-phase: `stage` (dry-run, writes nothing to master) then `commit` (finalize). The skill stages; a human commits from the UI (or the skill auto-commits when clean).
8. The system detects and *proposes*; a human decides every `contradicts` on master. Contradictions block auto-merge and open a Merge Request.
9. Entry identity (`entry_id`) is immutable. Staged entries carry transient ids and adopt an existing `entry_id` when reconciled to one; only `unrelated` entries get a fresh permanent id. Never alias one existing id to another.
10. **CQRS split.** Entries + the commit DAG are the only write model. The read model is a compiled set of markdown pages — **index, open-threads, journal, subject pages** — derived from master. M0 pages are fully deterministic; the single LLM synthesis section is M1.
11. **Nobody edits pages.** Pages are pure functions of `(master tree, template version)`. All change enters through entries. Full rebuild is always safe — pages are a regenerable cache.
12. The compiler is an **incremental build system**: dirty-tracking by `entry_id`, memoization by input hash, bounded recompiles.
13. The primary agent read path is **navigational**: index → open-threads / journal → subject page → section. Search over pages is Postgres FTS. pgvector is used only on the write path (reconciliation candidate retrieval), never as the consumption interface.
14. Permissions: M0 is **repo membership + per-user API tokens**. The `access_labels` column exists from day one; M1 turns on label-based Postgres RLS with no data migration. RLS (not app-layer filtering) is the target enforcement.
15. **Lint** (M1) is a periodic whole-corpus pass (master-vs-master) using the same reconcile classifier; findings open Merge Requests. Lint never auto-fixes.
16. A commit is **one Postgres transaction**: entries, commit row, tree, materialized HEAD, ref advance — atomic under a per-(repo, branch) advisory lock. The ref update is the durable commit point. Page compilation runs *after* and *outside* this transaction.

## 1. Stack

- Python 3.12, FastAPI + Pydantic v2; Next.js (App Router) for the UI.
- Postgres 16 + pgvector (HNSW) + FTS (`tsvector` + GIN). One database.
- **M0 jobs:** a Postgres `jobs` table + FastAPI background tasks (single worker process is sufficient for session-sized pushes of ~20–80 LLM calls). **M1:** Celery + Redis when lint and the synthesis compiler add scheduled/parallel load.
- LangGraph for the write-pipeline state machine.
- Anthropic API (Claude) for `reconcile` (M0), `merge_body` + `specificity` + `synthesize_page` (M1). Structured (tool/JSON) outputs wherever the output is machine-consumed.
- Embeddings behind an `Embedder` interface (default OpenAI `text-embedding-3-small`, 1536-dim); no vendor hardcoded at call sites.
- Repo layout:
  ```
  ctxvcs/
    api/        FastAPI routers + Pydantic models
    core/       entry/commit domain objects, hashing, canonicalization
    dag/        tree ops, diff (LCA/merge-base lands M2)
    pipeline/   LangGraph graph + node implementations (write path)
    compiler/   page compiler: dirty tracking, templates, assembly
    llm/        Claude clients (reconcile; M1: merge_body, specificity, synthesize_page)
    store/      SQLAlchemy models, repositories, auth/session mgmt
    embed/      Embedder interface + providers
    tasks/      job runner (M0: pg-backed; M1: Celery)
    tests/
    migrations/ Alembic
  evals/        fixtures (JSONL) · eval runners · committed reports — §12
  skill/        context-extraction skill (SKILL.md + thin CLI wrapper)
  web/          Next.js UI
  ```

## 2. System shape

```
WRITE:  agent session + skill --stage--> [validate → embed → reconcile_vs_master →
        apply_actions → router]
        router: clean --commit txn--> master   |   contradicts --> Merge Request --> UI review --> commit txn

STORE:  Postgres = source of truth: entries · commits/DAG · commit_entries ·
        master_entries (materialized HEAD) · refs · conflicts · staged · members

READ:   master advance --async--> page compiler (dirty pages only, memoized)
        --> pages: index · open-threads · journal · subject pages (markdown; derived cache)
        --> served: /wiki/index → open-threads/journal → page?section= → /wiki/search (FTS)
        agents read at session start; conflict banners joined at serve time

LINT (M1):  nightly master-vs-master reconcile sweep + invariants --> MRs in the review queue
```

## 3. Default schema — the working-context starter pack (M0)

M0 ships these built-in entry types; `POST /schema` can extend or override them, but there is **no schema-editor UI in M0**. All types share: `subject` (string, `x-subject-key`), optional structured fields, `body` (freeform), and provenance `{author, session_id, ts, origin: human|agent, note}`.

- **decision** — fields: `chosen` (string), `alternatives` (list), `rationale` in body. A human decision that shapes the work.
- **finding** — fields: `sources` (list of URLs/refs), `confidence` (low|med|high). Agent research output.
- **state_change** — fields: `what_changed` (string), `where` (string, e.g. repo/path/service). What was actually done this session.
- **open_question** — fields: `status` (open|closed), `blocking` (bool).
- **next_step** — fields: `status` (open|closed), `owner` (string, optional).
- **constraint** — fields: `kind` (technical|legal|product), `hard` (bool). Standing constraints and gotchas.

Lifecycle rule: closing an `open_question`/`next_step` is a **refines** push (new version with `status: closed`, superseding the open one) — no separate close endpoint or machinery.

Schema extensions per type: `x-subject-key`, `x-access-default` (labels; recorded in M0, enforced in M1), `x-embed-fields`. Push-time validation is JSON Schema per entry; hard failure ⇒ 422 with violations. No LLM.

## 4. Data model

### 4.1 Entry (domain object)
```python
class Entry:
    id: UUID                 # stable identity; transient until committed, then permanent
    content_hash: str        # sha256(canonicalize(type, fields, body)); version identity
    type: str
    fields: dict             # validated against the entry-type's JSON Schema
    body: str
    subject_key: str         # normalized (lower, trimmed) from x-subject-key
    embedding: list[float]
    access_labels: list[str] # recorded M0, enforced M1
    provenance: dict         # {author, session_id, ts, origin: human|agent, note}
```
`content_hash` is computed over a canonical JSON serialization (sorted keys, normalized whitespace; excludes provenance and embedding). Identical content ⇒ identical hash ⇒ stored once.

### 4.2 Postgres schema (write the Alembic migration; everything below is M0 DDL unless noted)
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE repos (id UUID PRIMARY KEY, name TEXT, owner TEXT, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE members (repo_id UUID REFERENCES repos(id), principal TEXT, role TEXT, api_token_hash TEXT,
                      PRIMARY KEY (repo_id, principal));   -- M0 auth: membership + token
-- M1 adds: grants(read_labels, write_labels) and RLS policies on entries.

CREATE TABLE schema_versions (
  repo_id UUID REFERENCES repos(id), version INT,
  entry_types JSONB NOT NULL,        -- defaults seeded from §3
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
  author TEXT, message TEXT NOT NULL,       -- message = session summary
  session_id UUID, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE commit_parents (commit_hash TEXT REFERENCES commits(hash), parent_hash TEXT REFERENCES commits(hash),
                             PRIMARY KEY (commit_hash, parent_hash));   -- linear in M0; table shape ready for M2
CREATE TABLE commit_entries (commit_hash TEXT REFERENCES commits(hash), entry_id UUID, content_hash TEXT REFERENCES entries(content_hash),
                             PRIMARY KEY (commit_hash, entry_id));

-- materialized HEAD tree. Retrieval, the compiler, and the subject registry join
-- entries ⋈ master_entries instead of reconstructing the tree per query.
-- Never put an is_current flag on entries — "current" is branch-relative.
CREATE TABLE master_entries (
  repo_id UUID REFERENCES repos(id), entry_id UUID NOT NULL,
  content_hash TEXT NOT NULL REFERENCES entries(content_hash),
  PRIMARY KEY (repo_id, entry_id)
);

CREATE TABLE refs (repo_id UUID REFERENCES repos(id), name TEXT, commit_hash TEXT REFERENCES commits(hash),
                   protected BOOLEAN DEFAULT false, PRIMARY KEY (repo_id, name));

CREATE TABLE jobs (id UUID PRIMARY KEY, kind TEXT, payload JSONB, status TEXT DEFAULT 'queued',
                   result JSONB, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ);  -- M0 job runner

CREATE TABLE staged_entries (
  id UUID PRIMARY KEY,                      -- the session id
  repo_id UUID REFERENCES repos(id), author TEXT,
  parent_commit TEXT, entries JSONB NOT NULL, proposed_actions JSONB,
  session_summary TEXT,
  status TEXT DEFAULT 'pending',            -- pending | committed | discarded
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE merge_requests (
  id UUID PRIMARY KEY, repo_id UUID REFERENCES repos(id), staging_id UUID REFERENCES staged_entries(id),
  origin TEXT DEFAULT 'push',               -- push | lint (M1)
  status TEXT DEFAULT 'open', created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE conflicts (
  id UUID PRIMARY KEY, repo_id UUID REFERENCES repos(id), merge_request_id UUID REFERENCES merge_requests(id),
  subject_key TEXT NOT NULL,
  existing_content_hash TEXT REFERENCES entries(content_hash), incoming JSONB,
  existing_commit TEXT, relation TEXT NOT NULL,   -- 'contradicts'
  confidence REAL, conflicting_fields TEXT[], proposed_resolution JSONB, status TEXT DEFAULT 'open'
);

-- ===== compiled read model (derived cache; regenerable) =====
CREATE TABLE wiki_pages (
  page_id UUID PRIMARY KEY, repo_id UUID NOT NULL REFERENCES repos(id),
  kind TEXT NOT NULL,                  -- index | open_threads | journal | subject
  slug TEXT NOT NULL, subject_key TEXT,
  source_commit TEXT NOT NULL,
  input_hash TEXT NOT NULL,            -- sha256(sorted input content_hashes + template_version)
  content TEXT NOT NULL,
  sections JSONB NOT NULL,             -- [{id, title, start, end}] header-anchored spans
  outbound_links TEXT[] NOT NULL DEFAULT '{}',
  fts tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  compiled_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (repo_id, slug)               -- M1 adds view_labels to the key for per-view pages
);
CREATE INDEX ON wiki_pages USING gin (fts);
CREATE INDEX ON wiki_pages (repo_id, subject_key);

CREATE TABLE page_inputs (             -- dirty tracking; key on entry_id, not content_hash
  page_id UUID REFERENCES wiki_pages(page_id) ON DELETE CASCADE,
  entry_id UUID NOT NULL, PRIMARY KEY (page_id, entry_id)
);
CREATE INDEX ON page_inputs (entry_id);

-- M1: wiki_page_versions (append-only audit), wiki_redlinks (coverage-gap queue)
```

### 4.3 Commit transaction boundary (M0)
A commit is exactly one Postgres transaction, executed while holding the advisory lock on `(repo_id, 'master')`:
1. Insert any new `entries` rows (content-hash upsert).
2. Insert the `commits` row (+ `commit_parents` row to the previous HEAD).
3. Insert the full `commit_entries` tree.
4. Replace the affected `master_entries` rows.
5. Advance `refs`.

The ref/`master_entries` update is the durable commit point. A failure before step 5 leaves at most orphaned content-addressed `entries` rows — harmless and invisible. Page compilation is enqueued after the transaction commits, never inside it.

## 5. Write pipeline (LangGraph) — M0 nodes

State: `repo_id, parent_commit, incoming_entries[], proposed_actions[], conflicts[], merge_status, mode('stage'|'commit')`.

1. **validate** — JSON Schema per entry; failure ⇒ terminal error. Exact content-hash duplicates within the batch collapse for free.
2. **embed** — embeddings for new entries.
3. **reconcile_vs_master** — §6.
4. **apply_actions** — execute the routing table. In `mode='stage'` simulated into `proposed_actions`; in `mode='commit'` writes via §4.3.
5. **router** — any unresolved `contradicts` ⇒ `needs_review`, persist Merge Request + conflicts, do not advance master; else auto-merge and enqueue `compile_dirty_pages(commit)`.

M1 adds: **intra_push_dedup** (semantic, within batch), **rate** (hygiene gate before router). Commits serialize per repo via the advisory lock.

## 6. Reconciliation classifier — the write-side centerpiece (M0)

One structured call per candidate pair. Retrieve-then-classify.

```
for incoming in incoming_entries:
    candidates = entries ⋈ master_entries WHERE repo_id=:r
                 AND ( subject_key = :incoming.subject_key
                       OR (embedding <=> :incoming.embedding) < (1 - TAU_CONF) )
    # DETERMINISTIC FIELD-COLLISION PREFILTER (no LLM, no NLP): same subject_key +
    # same structured field name + different scalar value — a dict diff over `fields`.
    # A collision does NOT auto-classify: "changed timeout from 60 to 30" (refines)
    # and "timeout is 30" vs "timeout is 60" (contradicts) produce the identical
    # field diff; only prose and temporal framing distinguish them. A collision
    # FORCES LLM adjudication constrained to {refines, subsumes, contradicts}, with
    # conflicting_fields pre-filled. Fail-closed: any other relation returned for a
    # collided pair is overridden to contradicts.
    for c in remaining:
        r = reconcile(incoming, c)     # inputs include BOTH sides' provenance ts + origin;
                                       # prompt encodes the prior: session work usually REFINES
                                       # (newer supersedes older) — reserve `contradicts` for
                                       # entries that both claim to be current with no ordering.
        # r.relation ∈ { duplicate | subsumed_by | subsumes | complementary | refines | contradicts | unrelated }
```

Routing table (relation → action; identity rule in parentheses):
- **duplicate** → drop incoming, reference `c.entry_id`.
- **subsumed_by** → drop incoming.
- **subsumes** → supersede `c` with incoming (adopts `c.entry_id`; old marked `superseded_by` in provenance).
- **refines** → clean update: supersede, same identity rule. The dominant session pattern — including status closes (§3). No human review.
- **complementary** → **M0: keep both** (both entries live under their own ids). M1: deterministic field union + `llm/merge_body` + schema revalidation; same-scalar collision promotes to `contradicts`; the LLM never picks a scalar.
- **contradicts** → conflict: persist under a Merge Request; a human decides. Default proposal `{"action":"supersede","winner":"incoming"}` — proposal only. Review UI shows each side's `origin` (human vs agent) and timestamps.
- **unrelated** → new entry, fresh permanent `entry_id`.

`reconcile` returns strict JSON via tool output: `{relation, confidence, rationale, conflicting_fields[]}`. Config: `TAU_CONF` 0.82, `CONF_MIN` 0.6 (below it, downgrade `contradicts` per config). No literals in code. Granularity is entry-level; leave an `llm/claim_extractor` seam, do not implement.

## 7. Compiled read model (M0: fully deterministic)

Pages are pure functions of `(master tree, template version)`. No LLM anywhere in the M0 compiler.

**Page kinds (M0):**
- **index** — one line per page: slug + one-line summary + `as_of_commit`. The agent's routing file. Links open-threads and journal at the top.
- **open_threads** — every `open_question` and `next_step` with `status=open`, grouped by subject, newest first, each with owner/blocking flags and a link to its subject page. **This is the landing page for picking up work.**
- **journal** — sessions newest first: commit summary, author, timestamp, then the session's entries grouped by type (decisions / findings / state changes / opened / closed). The team's ledger; replaces hub/overview pages entirely.
- **subject** — per active `subject_key`: frontmatter (`subject, as_of_commit, sections`), a **Facts** table rendered from structured fields (stable field-name ordering; byte-stable across recompiles), entry bodies grouped by type with provenance footnotes (`author · origin · session · ts`), **Open conflicts** (serve-time overlay from `conflicts`, never compiled in), Related (`[[subject]]` links resolved by exact match against the subject registry; unresolved render as plain text in M0, redlink queue in M1), History (superseded-chain pointers).

**Compiler:** on master advance — `diff_entry_ids(parent, HEAD)` → `page_inputs` join → dirty subject pages; recompile those, then open_threads, journal (append-mostly), index. Memoize by `input_hash`; skip on match. Runs as a job after the commit transaction. `POST /wiki/rebuild` recompiles everything and is always safe. Eventual consistency is seconds; frontmatter `as_of_commit` exposes the lag.

**M1 additions:** the single LLM `## Current understanding` synthesis section per subject page, regenerated only when fact inputs change (prior text passed to damp churn), recorded in `wiki_page_versions`; `wiki_redlinks`; per-view (label-partitioned) compilation.

## 8. Context-extraction skill (M0)

`skill/SKILL.md` + a thin CLI. Runs inside the developer's agent session; the platform runs no extraction. Plain REST with the user's API token; no MCP dependency.

Write flow:
```
0. GET  /repos/{r}/subjects                        -> the subject registry. REUSE existing
                                                      subjects; invent a new one only when
                                                      nothing fits. Subject reuse is what makes
                                                      reconciliation fire.
1. GET  /repos/{r}/schema                          -> entry-types + fields
2. introspect the session                          -> decisions made, findings researched,
                                                      state changed, questions opened/closed,
                                                      next steps
3. map onto entry-types; tag each entry's provenance.origin as human (user said/decided it)
   or agent (model researched/inferred it); write a 1–3 sentence session_summary
4. POST /repos/{r}/stage {parent_commit, entries[], session_summary}   -> {job_id}
5. poll GET /jobs/{id}                             -> {staging_id, proposed_actions, conflicts}
6. present the preview                             -> "N new · M refine/supersede · K conflict"
7. clean (no conflicts)  -> POST /staging/{id}/commit   (auto-finalize)
   conflicts             -> tell the developer to resolve in the review queue
```

Read flow (session start): `GET /wiki/page/open-threads` and the last few journal sessions; open subject pages/sections as needed via `?section=`; `GET /wiki/search?q=` for keyword lookup. Never fetch raw entries as the default read.

## 9. API surface (M0 unless tagged)

```
POST   /repos                                       -> {repo_id}   (seeds default schema §3, creates index/journal/open-threads pages)
POST   /repos/{r}/members        (owner)             -> membership + token issuance
GET    /repos/{r}/schema
POST   /repos/{r}/schema                              -> {version}  (API only; no editor UI in M0)
GET    /repos/{r}/subjects                            -> distinct subject_key over master_entries, with entry counts

POST   /repos/{r}/stage          body {parent_commit, entries[], session_summary}  -> {job_id}
GET    /jobs/{id}                                     -> {status, staging_id?, proposed_actions?, conflicts?}
GET    /repos/{r}/staging/{id}                         -> staged preview
POST   /repos/{r}/staging/{id}/commit  body {resolutions[]}  -> {commit_hash?, merge_request_id?}

GET    /repos/{r}/commits?since=                      -> session ledger (hash, author, summary, ts)
GET    /repos/{r}/commits/{hash}                       -> {commit, tree}
GET    /repos/{r}/diff?from=&to=                       -> {added[], removed[], modified[]}  (map symmetric difference)
GET    /repos/{r}/entries/{id}/history                 -> superseded chain for a stable entry_id

GET    /repos/{r}/merge-requests/{id}
POST   /repos/{r}/merge-requests/{id}/resolve  body {conflict_id, decision}  -> advances master, enqueues compile

GET    /repos/{r}/wiki/index
GET    /repos/{r}/wiki/page/{slug}?section={id}        -> full page or one header-anchored section
GET    /repos/{r}/wiki/search?q=&k=                     -> FTS; [{slug, section_id, snippet, rank}]
POST   /repos/{r}/wiki/rebuild    (owner)

# M1: /grants + RLS enforcement · /wiki/redlinks · /context one-shot bundle · lint report endpoints
# M2: /branches/* · LCA/merge-base · MCP server surface
```

## 10. UI (Next.js) — M0 screens only

- **Review / merge queue (hero).** Staging preview: incoming entries tagged new / refine / supersede / kept-both / dropped / conflict. Conflicts render current vs incoming side by side with the classifier's rationale, confidence, conflicting fields, and **each side's origin (human/agent) + session + timestamp**. Accept / edit / reject map to `commit` resolutions. Build this first and best.
- **Wiki browser.** Open-threads as the default landing tab; journal; index navigation; subject pages with the serve-time conflict overlay; a search box over `/wiki/search`.

M1 screens: grants admin, lint reports, redlink queue. M2: schema editor.

## 11. Milestones

### M0 — running platform (the team dogfoods it end to end)
Scope: default schema seeding; membership + API tokens; pg-jobs runner; pipeline (validate → embed → reconcile → apply → router); classifier with all 7 relations, field-collision prefilter (§6), complementary = keep-both; two-phase stage/commit; §4.3 commit transaction on linear master; deterministic compiler + index/open-threads/journal/subject pages + FTS; skill (registry → extract → stage → preview → commit, origin tagging, session summary); review queue + wiki browser UI; **the §12 eval harness with seed fixtures, built before the classifier — the classifier is developed against it**.

Acceptance (scripted end-to-end, then a week of real use):
- Run the skill in a real coding session ⇒ schema-valid entries staged; preview shows per-entry relations; a clean session auto-commits.
- Plant a contradiction (incoming `finding` sets `consumer_timeout_seconds=30` while master says `60`, both current, no change language) ⇒ field collision forces constrained adjudication, classifier returns `contradicts`, master not advanced, MR opened; resolving in the UI supersedes and advances master; the subject page's Facts row updates on the next compile. The same field diff phrased as an explicit update ("changed 60s → 30s after load test") ⇒ `refines`, clean supersede, no MR.
- Close a `next_step` via a `refines` push ⇒ it disappears from open-threads, appears under "closed" in that session's journal block.
- A second teammate's agent reads open-threads + the last journal sessions and produces a correct "current state + what's next" summary without any human hand-off.
- Identical entry pushed twice ⇒ zero new rows; `master_entries` ≡ HEAD tree after every commit; forced failure before ref advance leaves `refs`/`master_entries` untouched.
- A push touching k entries recompiles exactly the dirty subject pages (all other `input_hash` unchanged) + open-threads + journal + index; `rebuild` reproduces byte-identical pages.
- All §12 eval gates pass: reconcile seed-set action-level gates (zero missed conflicts, zero false conflicts on supersede-expected pairs, zero false drops, ≥18/21 action accuracy, ≤3 non-unanimous pairs), golden scenarios S1/S2 green in both fake and live modes, skill extraction metrics at threshold, fixture set grown to ≥40 pairs. Reports committed under `evals/reports/`.

### M1 — trust and depth
Label RLS enforcement (dedicated RLS-subject app role; compiler/lint under a privileged service role; verify enforcement by querying as the app role directly) · complementary merge (deterministic field union, `llm/merge_body`, revalidate, scalar collision ⇒ `contradicts`) · rating gate (`schema_completeness`, `provenance_present`, `specificity`, redundancy penalty; below threshold ⇒ review) · semantic intra-push dedup · nightly lint (master-vs-master sweep within subject clusters + budgeted near-neighbor pairs ⇒ `origin='lint'` MRs; invariants: input_hash recompute, `master_entries` ≡ HEAD, page lag bound) · `## Current understanding` synthesis with input-hash gating + `wiki_page_versions` · redlinks · Celery/Redis swap-in · eval expansion per §12: grow the fixture set to ≥60 pairs, add model-version regression tracking and per-relation trend reports in CI; `contradicts` recall and `refines`-vs-`contradicts` separation remain the headline metrics.

### M2 — scale and reach
Branches + LCA/merge-base + branch-aware diff · per-view (label-partitioned) page compilation, baseline eager / restricted lazy · MCP server exposing search/read/stage · schema-editor UI · multi-repo/team hardening · wiki export (Obsidian-browsable tree) · claim-level decomposition seam activation if entry-level precision proves insufficient.

## 12. Eval strategy (M0) — the coding agent's development loop

Deterministic components are verified by invariant/property tests (§14). LLM-bearing components are verified by **fixture-based evals with hard gates**, runnable by one command, producing a scored report the coding agent reads and iterates against. Evals are built **before** the components they gate.

### 12.1 Layout and run modes
```
evals/
  fixtures/reconcile_seed.jsonl     # provided — copy verbatim; grow it (§12.6)
  fixtures/scenarios/               # S1, S2 golden scenario definitions
  fixtures/skill/                   # T1–T3 transcripts + expected_items + seeded registry
  run_reconcile.py                  # classifier eval (live model)
  run_scenarios.py                  # pipeline evals (--mode fake | live)
  run_skill.py                      # extraction eval (live + pinned judge)
  reports/                          # timestamped markdown reports, committed to the repo
```
Live-model runs are gated by `EVAL_LIVE=1` and print an estimated call count + cost before executing. Fake-mode runs use the deterministic `llm/` fakes and run in CI on every change.

### 12.2 Reconcile classifier eval — the gatekeeper
Fixture schema (JSONL, one pair per line):
```json
{"id":"R06","expected":"refines","path":"collision",
 "existing":{"type":"finding","subject":"ban-service-consumer","fields":{"consumer_timeout_seconds":60},
             "body":"...","ts":"2026-06-18","origin":"agent"},
 "incoming":{...},
 "fields_hint":["consumer_timeout_seconds"],
 "note":"collision fires but change-language ⇒ refines; forbids auto-conflict-on-collision"}
```
`expected` may be replaced by `expected_any: [...]` where two relations map to the same action and either is acceptable. `path` marks whether the pair should enter constrained collision adjudication (`collision`) or the open classifier (`llm`).

Protocol: for each pair, call the real `llm/reconcile` **3 times**; majority vote is the prediction; report the flip rate and list every non-unanimous pair with all three outputs. Seed set = 21 pairs (provided), covering all seven relations, both collision-path cases, the refines-vs-contradicts boundary trap (R06), a cross-subject embedding trap (R20), and `expected_any` pairs where `refines`/`subsumes` are interchangeable.

Scoring at two levels:
- **Relation-level** (diagnostic): full 7×7 confusion matrix in the report.
- **Action-level** (gated): relations collapse to what M0 does — `drop` {duplicate, subsumed_by} · `supersede` {refines, subsumes} · `keep` {complementary, unrelated} · `conflict` {contradicts}.

Gates on the seed set (absolute counts — honest at N=21):
| Gate | Threshold | Why |
|---|---|---|
| Missed conflicts (expected `conflict`, predicted anything else) | 0 | silent corruption of master is the worst failure |
| False conflicts on supersede-expected pairs | 0 | review noise kills adoption (R06 is the guard) |
| False drops (expected keep/supersede/conflict, predicted `drop`) | 0 | data loss |
| Action-level accuracy (majority vote) | ≥ 18/21 | overall competence |
| Non-unanimous pairs across 3 trials | ≤ 3; none may cross action groups on conflict-expected pairs | stability |

### 12.3 Golden scenario evals — the pipeline
Scenarios assert end-state, not just outputs. Both run in `--mode fake` (scripted relations keyed by fixture id; CI on every change — tests pipeline, transaction, and compiler logic independent of model quality) and `--mode live` (real classifier; on demand and nightly).

**S1 — mixed second session.** Seed commit C0 with four entries (a timeout `finding`, a RocketMQ `constraint`, an open `next_step`, a `decision`). Push a session containing: an exact-paraphrase duplicate of the constraint, an explicit-update refine of the timeout, a both-current collision conflict against the decision, and two new entries. Assert: preview actions per entry are exactly {drop, supersede, conflict, new, new}; master unmoved; one MR with one conflict carrying `conflicting_fields`. Resolve keep-incoming. Assert: HEAD tree contents exact; superseded entry keeps its `entry_id` with `superseded_by` provenance; recompiled pages are exactly the touched subjects + open-threads + journal + index (all other `input_hash` unchanged); the journal's newest session block lists the decision conflict as resolved.

**S2 — close the loop.** Master holds an open `next_step`. Push a session with its `status: closed` refine plus one new `open_question`. Assert: open-threads no longer lists the step, lists the new question; the journal session block shows it under "closed"; `GET /entries/{id}/history` returns the two-version chain.

### 12.4 Skill extraction eval
Three synthetic transcripts in `fixtures/skill/`, each a condensed session log with an annotated `expected_items` list and, for T3, a pre-seeded subject registry:
- **T1** — ban-lifecycle implementation session: contains one human decision (transactional half-messages), two agent findings (at-least-once semantics; DLQ behavior), one opened next_step.
- **T2** — age-verification vendor evaluation: one human decision with alternatives, one constraint (AU U16 deadline), one open_question (fallback when estimation confidence is low).
- **T3** — a follow-up session whose content maps onto **existing** registry subjects (`ban-service-consumer`, `dlq-replay-runbook`); tests reuse, not invention.

Metrics and gates: schema-validity **100%** (deterministic); subject reuse ≥ **4/5** reusable slots on T3 (the anti-sprawl gate); expected-item recall ≥ **80%** across T1–T3; hallucinated decisions = **0**, graded by an LLM judge that checks each extracted `decision` is grounded in the transcript. Judge discipline: judge model + rubric are pinned files in `evals/`; the human spot-checks the judge's first 20 verdicts before its scores are trusted; judges are used only where no ground-truth label exists (never in §12.2).

### 12.5 What is *not* an eval
The compiler, DAG, transaction boundary, and prefilter dict-diff are deterministic — they get invariant tests (§14), not fixtures. Do not put an LLM judge on anything a byte-comparison can verify.

### 12.6 Development-loop contract (binding on the coding agent)
1. Build `evals/` scaffolding and copy the seed fixtures **before** implementing `llm/reconcile`. Develop the classifier against `run_reconcile.py`.
2. Prompts are versioned code (`llm/prompts/reconcile.md`, `llm/prompts/extract.md`). Every prompt, model, or threshold change reruns the relevant live eval; the report is committed with the change.
3. Fake-mode tests run on every change. Live evals run at chunk completion and on prompt/model/threshold changes, never silently (cost printed, `EVAL_LIVE=1`).
4. Every misclassification or bug found in any later testing is converted into a fixture **before** it is fixed. The fixture set must reach ≥ 40 pairs before M0 exit.
5. An M0 chunk is not complete until its §12 gates pass; failures are analyzed in the report (confusion matrix + per-failure model rationale dump), not just retried.
6. All reports live under `evals/reports/` in the repo — progress must be auditable from git history alone.

## 13. Out of scope (all milestones)
Code-source binding / code-change staleness; distributed/p2p; CRDTs; delta-compressed trees + gc; concurrent field-level 3-way merge; longitudinal trust scoring; retrieval logs/audit; PII/secret auto-labeling; LLM-maintained freeform pages or any direct page editing; embedding-based consumption retrieval (RRF/MMR packing).

## 14. Testing / quality bar
- All LLM calls behind `llm/` interfaces with deterministic fakes; unit tests never hit the real API. Live-model evaluation is governed by §12 (`EVAL_LIVE`-gated runners, committed reports).
- Invariant tests: content-hash canonicalization stability; `master_entries` ≡ HEAD tree after every commit; commit-transaction atomicity under injected failure; identity rules (supersede keeps `entry_id`; nothing ever aliases two existing ids).
- Compiler: deterministic pages byte-stable across recompiles; memoization verified (unchanged input hash ⇒ zero writes); rebuild-from-scratch equivalence.
- All thresholds/weights in a typed config object; no magic numbers in logic.
