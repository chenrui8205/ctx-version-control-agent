# Working in this repo

The build spec is [docs/context-vcs-spec.md](docs/context-vcs-spec.md). Its Core
Decisions are binding — flag before deviating. §12.6 (development-loop contract) is
binding on coding agents:

1. Evals are built **before** the components they gate. The reconcile classifier is
   developed against `evals/run_reconcile.py`, never freehand.
2. Prompts are versioned code (`ctxvcs/llm/prompts/*.md`). Any prompt, model, or
   threshold change → rerun the relevant live eval (`EVAL_LIVE=1`) and **commit the
   report** under `evals/reports/`.
3. Every misclassification/bug found later becomes a fixture in
   `evals/fixtures/reconcile_seed.jsonl` **before** it is fixed (target ≥ 40 pairs by M0 exit).
4. Fake-mode tests run on every change: `uv run pytest` (needs `docker compose up -d`).
5. No magic numbers in logic — thresholds live in `ctxvcs/config.py`.

Layout gotchas:
- `entries` is a global content-addressed store; within a repo, identity resolves via
  `master_entries`/`commit_entries`, never `entries.entry_id`.
- Pages are a regenerable cache; nobody edits them. Change templates → bump
  `template_version` in config → rebuild.
- The §4.3 commit transaction owns its Postgres transaction (advisory lock inside);
  don't wrap `commit_staged` in another transaction.
