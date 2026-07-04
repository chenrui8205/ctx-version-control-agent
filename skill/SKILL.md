---
name: ctxvcs-push
description: Distill this working session into structured context entries and push them to the team's Context VCS. Use at the end of a working session (or when the user says "push context", "save session", "ctxvcs push"). Also use at session START to load team context ("pull context", "what's the current state?").
---

# Context VCS — session push & read skill

You are the write path of the team's context version-control system. The platform runs
no extraction — **you** introspect the session and produce already-structured entries.
Talk to the API with `python skill/ctxvcs_cli.py …` (env: `CTXVCS_URL`, `CTXVCS_REPO`,
`CTXVCS_TOKEN`).

## Read flow — session start

1. `python skill/ctxvcs_cli.py page open-threads` — what's open. This is the landing view.
2. `python skill/ctxvcs_cli.py journal --last 3` — the last few sessions.
3. Open subject pages as needed: `page <slug>` or `page <slug> --section facts`.
4. Keyword lookup: `search "<query>"`. Never fetch raw entries as the default read.

## Write flow — session end

### 0. Consult the subject registry FIRST (mandatory)

```
python skill/ctxvcs_cli.py subjects
```

**REUSE existing subjects; invent a new one only when nothing fits.** Subject reuse is
what makes reconciliation fire — a renamed subject silently forks the team's context.
Match by meaning, not string: if the registry has `ban-service-consumer` and you worked
on the ban service's RocketMQ consumer, that IS your subject. New subjects: short,
kebab-case, component-scoped (`dlq-replay-runbook`), never person- or session-scoped.

### 1. Fetch the schema

```
python skill/ctxvcs_cli.py schema
```

Entry types (M0 defaults): `decision` (chosen, alternatives) · `finding` (sources,
confidence) · `state_change` (what_changed, where) · `open_question` (status, blocking)
· `next_step` (status, owner) · `constraint` (kind, hard). All take `subject`, freeform
`body`, and optional extra structured fields — put load-bearing scalars (timeouts,
TTLs, versions, choices) into structured fields, because field collisions drive
conflict detection.

### 2. Introspect the session

Walk the session and collect: decisions made · findings researched · state actually
changed · questions opened or answered · next steps. Rules:

- **Entries, not narration.** One claim per entry. Skip process chatter, dead ends
  that taught nothing, and anything the repo/git history already records.
- **Closing something is a push, not a delete**: closing an open_question/next_step
  means pushing a new version with `status: closed` and a body saying what closed it.
- **Describe changes as changes.** If a value changed this session, write change
  language ("changed X from 60s to 30s after load test"), not a bare present-tense
  claim — that's the difference between a clean refine and a false conflict.
- **origin tagging (mandatory):** `provenance.origin = "human"` when the user said or
  decided it; `"agent"` when you researched or inferred it. Set `provenance.ts` to
  today's date.
- Only report a `decision` the user actually made or explicitly ratified. Never invent
  decisions from your own suggestions.

### 3. Write the session summary

1–3 sentences: what this session did to the working state. It becomes the commit
message in the team's journal.

### 4. Stage (dry-run — writes nothing to master)

Write the entries to a JSON file and:

```
python skill/ctxvcs_cli.py stage entries.json --summary "…" [--parent <commit>]
python skill/ctxvcs_cli.py job <job_id> --wait
```

### 5. Present the preview to the developer

Summarize the proposed actions: `N new · M refine/supersede · D dropped as duplicates
· K conflicts`. Show each conflict: both sides, the classifier's rationale, origins
and timestamps.

### 6. Finalize

- **Clean (no conflicts):** `python skill/ctxvcs_cli.py commit <staging_id>` — auto-finalize.
- **Conflicts:** do NOT auto-commit. Tell the developer to resolve in the review queue
  (web UI → Review), or — only if they decide in-session — pass resolutions:
  `python skill/ctxvcs_cli.py commit <staging_id> --resolutions res.json`.

## Entry JSON shape

```json
{
  "type": "state_change",
  "subject": "ban-service-consumer",
  "fields": {"consumer_timeout_seconds": 30, "what_changed": "timeout 60s -> 30s", "where": "ban-service"},
  "body": "Load test led us to change the ban-service consumer timeout from 60s to 30s.",
  "provenance": {"origin": "human", "ts": "2026-07-04"}
}
```
