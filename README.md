# ctx-version-control-agent

Semantic version control for your agent's working context — a centralized, Git-like
platform where the unit of versioning is a context **entry** and a push is a
**session**. Full design: [docs/context-vcs-spec.md](docs/context-vcs-spec.md).

- **Write path:** a skill running in your agent session distills decisions / findings /
  state changes / questions / next steps, stages them, and the platform reconciles them
  against master with one relation classifier (dedup · supersede · contradiction detection).
- **Read path:** a deterministic compiler builds markdown pages — index, **open-threads**
  (the landing view), journal (session ledger), subject pages — served over REST with FTS.
- Contradictions never auto-merge: they open a Merge Request a human resolves in the UI.

## Quickstart (M0)

```bash
docker compose up -d                       # Postgres 16 + pgvector on :5433
uv sync
uv run alembic upgrade head
export ANTHROPIC_API_KEY=…  OPENAI_API_KEY=…   # reconcile classifier · embeddings
uv run uvicorn ctxvcs.api.main:app --port 8000
cd web && npm install && npm run dev       # UI on :3000
```

Create a repo and connect:

```bash
curl -s -X POST localhost:8000/repos -H 'content-type: application/json' \
  -d '{"name":"team-context","owner":"you@example.com"}'
# → {repo_id, token}  → paste into the web UI (Settings) and into the skill env
```

Skill (runs inside your agent session — see [skill/SKILL.md](skill/SKILL.md)):

```bash
export CTXVCS_URL=http://localhost:8000 CTXVCS_REPO=<repo_id> CTXVCS_TOKEN=<token>
python skill/ctxvcs_cli.py page open-threads     # session start: what's open
python skill/ctxvcs_cli.py stage entries.json --summary "…"   # session end: push
```

## Development loop

```bash
uv run pytest                                   # invariants + golden scenarios (fake LLM)
uv run python evals/run_reconcile.py            # classifier eval harness, fake plumbing check
EVAL_LIVE=1 uv run python evals/run_reconcile.py --live    # §12.2 gates (real model)
uv run python evals/run_scenarios.py --mode fake           # S1/S2 end-state asserts
EVAL_LIVE=1 uv run python evals/run_skill.py --mode live   # extraction eval (pinned judge)
uv run python scripts/smoke_http.py             # scripted end-to-end over HTTP
```

Evals are built before the components they gate; every prompt/threshold change reruns
the relevant live eval and the report is committed under `evals/reports/`
(spec §12.6 — binding).

## Layout

`ctxvcs/` FastAPI + pipeline + compiler + store · `evals/` fixtures, runners, reports ·
`skill/` SKILL.md + CLI · `web/` Next.js review queue + wiki browser.
