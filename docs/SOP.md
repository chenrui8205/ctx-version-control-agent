# Context VCS — Standard Operating Procedure

The mental model in one paragraph: **a push is a session, an entry is the unit of
versioning, and master is the team's canonical working state.** You never edit pages —
you push entries; the platform reconciles them against master (dedup / supersede /
contradiction), and a compiler regenerates the readable wiki. Contradictions never
merge silently: they open a Merge Request that a human resolves in the UI.

---

## 1. Start the platform (after a reboot)

```bash
cd ~/Projects/ctx-version-control-agent
docker compose up -d                                   # Postgres (:5433)
set -a; source .env; set +a                            # loads ANTHROPIC/OPENAI keys
uv run uvicorn ctxvcs.api.main:app --port 8000 &       # API
cd web && npm run dev &                                # UI on http://localhost:3000
```

Sanity check: `curl localhost:8000/healthz` → `{"ok":true}`.

## 2. One-time setup per team

```bash
# create the repo (returns repo_id + your owner token — save both)
curl -s -X POST localhost:8000/repos -H 'content-type: application/json' \
  -d '{"name":"team-context","owner":"you@example.com"}'

# add a teammate (owner token required; returns THEIR token — send it to them privately)
curl -s -X POST localhost:8000/repos/<repo_id>/members \
  -H "Authorization: Bearer <owner_token>" -H 'content-type: application/json' \
  -d '{"principal":"teammate@example.com","role":"member"}'
```

Everyone: open http://localhost:3000 → **Settings** → paste API URL, repo id, your
token. Everyone also sets the skill env in their agent sessions:

```bash
export CTXVCS_URL=http://localhost:8000
export CTXVCS_REPO=<repo_id>
export CTXVCS_TOKEN=<your_token>
```

## 3. Daily developer loop

### Session START — pull context (~30 seconds)

Ask your agent to load team context, or run it yourself:

```bash
python skill/ctxvcs_cli.py page open-threads     # what's open — the landing view
python skill/ctxvcs_cli.py journal --last 3      # what the last sessions did
python skill/ctxvcs_cli.py page <subject>        # deep-dive a subject as needed
python skill/ctxvcs_cli.py search "timeout"      # keyword lookup
```

Your agent now knows the current state and what's next — no human hand-off needed.

### Session END — push (2–5 minutes)

Tell your agent: **"push context"** (it follows `skill/SKILL.md`). What it does, and
what you should watch for:

1. It fetches the **subject registry** and reuses existing subject names. If you see it
   inventing a subject that's really an existing one renamed — correct it. Subject
   reuse is what makes conflict detection work.
2. It distills the session into entries: decisions / findings / state changes /
   opened & closed questions / next steps. Each tagged `origin: human` (you said it)
   or `agent` (it researched it).
3. It **stages** — a dry run; nothing touches master — and shows you the preview:
   - `new` — a genuinely new entry
   - `supersede` — updates/replaces an existing entry (the normal case: refinements,
     status closes, "changed X from A to B")
   - `drop` — duplicate of something already on master
   - `kept-both` — same subject, different facet; both stand
   - `conflict` — contradicts something on master → needs a human
4. **Clean preview → it auto-commits.** Done; the wiki updates within seconds.
   **Conflicts → it stops** and tells you to resolve in the UI. Never bypass this.

Rules of thumb that keep pushes clean:
- Closing a step/question = pushing a new version with `status: closed` — never ask
  for deletion.
- If a value changed this session, phrase it as a change ("raised TTL 15m → 30m after
  cache-miss spike"), not a bare claim ("TTL is 30m"). The first is a clean supersede;
  the second reads as a second source of truth and may open a conflict.

## 4. Resolving conflicts (review queue)

UI → **Review**. Open the merge request. For each conflict you see both sides —
current-on-master vs incoming — with the classifier's rationale, confidence, the
exact conflicting fields highlighted, and each side's **origin + timestamp** (a human
decision from yesterday usually beats an agent inference from last week).

- **Accept incoming** — the new entry supersedes; master advances.
- **Keep existing** — the incoming entry is discarded.
- **Edit…** — write the correct merged version yourself, then resolve.

When the last conflict is decided, the commit executes automatically and the pages
recompile. The journal records what was contested and how it was resolved.

## 5. Reading the wiki

- **Open threads** (landing tab) — every open question and next step, grouped by
  subject, newest first. This is "what should I pick up?"
- **Journal** — the session ledger, newest first: who pushed what, what each session
  decided/found/changed/closed.
- **Subject pages** — Facts table (current structured values), entries by type with
  provenance, History (version chains). A red banner on top = contested entries
  awaiting review; the banner links to the MR.
- Frontmatter `as_of_commit` tells you how fresh a page is. Pages lag commits by
  seconds. Search is keyword (FTS), not semantic — search the words that would appear
  on a page.

## 6. When something looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| Commit rejected `StaleParentError` | someone pushed since you staged | re-stage (the skill re-runs the preview against new master) |
| Commit rejected "empty commit" | everything you pushed already exists | nothing to do — that's dedup working |
| Preview shows a conflict you think is a clean update | body phrased as a bare present-tense claim | reject incoming, re-push with change language; if the classifier was genuinely wrong, **add the pair to `evals/fixtures/reconcile_seed.jsonl` before touching the prompt** (§12.6.4) |
| Page looks stale/odd | compile job hiccup | `POST /repos/<r>/wiki/rebuild` (owner) — always safe, pages are a cache |
| `GET /jobs/<id>` → `error` | see `result.error` traceback | fix cause, re-stage; jobs are disposable |
| Wrong entry on master, no conflict fired | silent misclassification | fixture first, then fix; then push a correcting entry (supersede) |

## 7. Owner/admin tasks

- **Rotate a token:** re-POST the same principal to `/members` — issues a fresh token.
- **Add an entry type:** `POST /repos/<r>/schema` with `{entry_types: {...}}` (JSON
  Schema + `x-subject-key`/`x-embed-fields`/`x-collision-exempt`). No UI in M0.
- **Never** hand-edit `wiki_pages`, `master_entries`, or `entries` rows. All change
  enters through pushes; pages are regenerable.

## 8. Quality loop (when changing prompts/thresholds/models)

Binding contract — see `CLAUDE.md` and spec §12.6:

```bash
uv run pytest                                            # every change
EVAL_LIVE=1 uv run python evals/run_reconcile.py --live  # classifier gates
EVAL_LIVE=1 uv run python evals/run_scenarios.py --mode live
EVAL_LIVE=1 uv run python evals/run_skill.py --mode live
```

Every misclassification found in real use becomes a fixture **before** it's fixed;
every live report gets committed under `evals/reports/`.
