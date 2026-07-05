# Dogfood E2E playbook — "Chip-in" (ground truth; hidden from dev agents during the run)

Project: **Chip-in**, a toy expense-splitting web app (FastAPI + SQLite backend, vanilla JS frontend).
Team: Alex Chen (backend), Sam Rodriguez (frontend), Riley Park (generalist).
Six sessions across one simulated week. Real platform, real classifier, fresh repo.

Planted failure modes: duplicate research (S2), lifecycle close (S2, S3, S6), collision-with-change-language
refines (S3, the R06 pattern), both-current collision contradiction + MR (S4), stale fragment resurrection
attempt (S5), multi-close wrap-up (S6).

---

## Session briefs and expected outcomes

### S1 — Alex, Monday morning: kickoff + backend skeleton
Brief: green-field kickoff. Choose the stack (you want zero-ops: FastAPI + SQLite + vanilla JS over
Flask+Postgres and Express). Decide the data model (single `expenses` table with a participants JSON column
over a normalized junction table — speed for a weekend project). Scaffold the repo, implement POST/GET
/expenses (default page size 50). Research SQLite concurrency (WAL mode: concurrent readers during writes,
still single-writer). Set the money rule: integer cents only, never floats (your call, you feel strongly).
Open question: how to allocate indivisible cents in uneven splits (blocks settle-up). Next steps: Sam builds
the add-expense + balances UI; Alex implements minimal-transfers settle-up.

Expected entries (9): decision chipin-stack · decision expense-data-model · state_change chipin-backend ·
finding expenses-api {default_page_size: 50} · finding sqlite-concurrency · constraint money-arithmetic ·
open_question split-rounding (blocking) · next_step chipin-frontend (owner sam) · next_step
settle-up-algorithm (owner alex).
Expected actions: 9 × new (empty master). Clean push, auto-commit.
Post-state: open = {split-rounding, chipin-frontend, settle-up-algorithm}.

### S2 — Sam, Monday afternoon: frontend + duplicate research
Brief: read team context first; pick up the chipin-frontend thread. Build the add-expense form + balances
view. You independently re-research SQLite concurrency (you didn't scroll far enough in the journal) and
learn the same WAL facts — push it as your own finding (paraphrase of Alex's). You hit CORS: FastAPI needs
CORSMiddleware; wildcard origin breaks credentialed fetch. Close the chipin-frontend next_step (UI shipped).
Open question: do we support receipt photo uploads in v1? (not blocking).

Expected entries (5): finding sqlite-concurrency (paraphrase) · state_change chipin-frontend ·
next_step chipin-frontend {status: closed} · finding chipin-cors · open_question receipt-uploads.
Expected actions: 1 drop (duplicate/subsumed_by) · 1 supersede (lifecycle close) · 3 new. Clean push.
Post-state: open = {split-rounding, settle-up-algorithm, receipt-uploads}.

### S3 — Riley, Wednesday: settle-up + the explicit change (R06 pattern)
Brief: read context. Resolve the rounding question: decide largest-remainder allocation, payer absorbs the
residual cent (alternatives: round-robin extra cent, random assignment) — and close the split-rounding
question. Implement the settle-up endpoint (greedy min-cash-flow, ≤ n-1 transfers; optimal count is NP-hard
— worth a finding). While profiling on mobile you CHANGE the expenses default page size from 50 to 20 —
push it with explicit change language ("changed 50 → 20 after mobile render lag").

Expected entries (5): decision split-rounding · open_question split-rounding {status: closed} ·
state_change expenses-api {default_page_size: 20} (change language) · state_change settle-up ·
finding settle-up.
Expected actions: 2 supersede (question close; collision→refines via change language — MUST NOT conflict)
· 3 new (settle-up pair may complementary-keep — also fine). Clean push, NO merge request.
Post-state: open = {settle-up-algorithm, receipt-uploads}. Facts: expenses-api.default_page_size = 20.

### S4 — Alex, Thursday: the stale assertion (must fire contradicts)
Brief: you skipped reading the journal (busy day). Perf-test session: you add DB indices (state_change),
run a load test (finding: ~200 rps on a laptop), and — working from your Monday memory — you record as a
current fact that GET /expenses returns 50 items per page (bare present tense, {default_page_size: 50}, no
change language; you believe it IS 50). Also: next_step deploy-demo (owner riley) — deploy to fly.io before
the group trip.

Expected entries (4): state_change chipin-backend (indices) · finding load-test · finding expenses-api
{default_page_size: 50} (STALE) · next_step deploy-demo.
Expected actions: 1 conflict (collision, both-current ⇒ contradicts; MR opened; master NOT advanced) ·
3 new (held behind the MR).
ADMIN RESOLUTION (me, logged): keep existing — Riley's 20 is the real current value; Alex's 50 is stale.
Post-resolution state: default_page_size stays 20; the 3 clean entries land; stale 50 discarded.
Post-state: open = {settle-up-algorithm, receipt-uploads, deploy-demo}.

### S5 — Sam, Friday: stale fragment (must drop, not resurrect)
Brief: quick session. You build the settle-up view in the UI. In your notes you restate "we use largest
remainder for splits, payer takes the leftover cent" as a finding (it's a fragment of Riley's richer
decision — should be dropped as subsumed_by/duplicate, NOT kept, NOT conflicting). Open next_step:
demo-data-seed script (owner sam).

Expected entries (3): state_change chipin-frontend (settle-up view) · finding split-rounding (fragment)
· next_step demo-data-seed.
Expected actions: 1 drop · 2 new. Clean push.
Post-state: open = {settle-up-algorithm, receipt-uploads, deploy-demo, demo-data-seed}.

### S6 — Riley, Saturday: wrap-up
Brief: read context; close the week. Settle-up has been implemented since Wednesday but the step is still
open — close it. Deploy to fly.io (state_change with the URL chip-in-demo.fly.dev) and close deploy-demo.
Decide receipts: defer to v2 (chosen "defer to v2", alternatives ["ship minimal upload in v1"]); close the
receipt-uploads question. Open next week's question: do we need real auth before sharing beyond the trip
group? (auth-model, not blocking).

Expected entries (7): next_step settle-up-algorithm {closed} · state_change deploy ·
next_step deploy-demo {closed} · decision receipt-uploads · open_question receipt-uploads {closed} ·
open_question auth-model · (optional next_step or finding — allow 6–8).
Expected actions: 3 supersede (closes) · 3–4 new. Clean push.
FINAL ground-truth open set: next_step demo-data-seed (sam) · open_question auth-model.

---

## Master-state audit checklist (after every commit)
1. open-threads page lists exactly the ground-truth open set (subjects + owners).
2. Facts: expenses-api.default_page_size correct for the epoch (50 after S1; 20 from S3 on, incl. after S4).
3. No duplicate claims on master (sqlite-concurrency has ONE finding entry; split-rounding ONE decision).
4. Journal newest block matches the session (author, closes listed under Closed, S4 conflict shown resolved).
5. master_entries ≡ HEAD tree (invariant endpoint/SQL).

## Per-push gates (same spirit as §12.2, hard counts)
- Missed conflicts = 0 (S4 must open an MR)
- False conflicts = 0 (S3 and S5 must NOT open MRs)
- False drops = 0 (nothing expected-keep may drop; S2/S5 drops are the only allowed drops)
- Action accuracy ≥ 90% overall; extraction recall vs brief ≥ 80%; subject reuse: every planted
  cross-session subject must land on the existing subject_key (else reconciliation can't fire).

---

## Hand-off exam (12 questions + key) — asked of (A) wiki-only agent, (B) raw-transcripts agent
1. What stack did the team choose and why? → FastAPI + SQLite + vanilla JS; zero-ops weekend project
   (alts: Flask+Postgres, Express).
2. What is the CURRENT default page size for GET /expenses? → 20 (trap: 50 asserted later-in-time by Alex
   on Thursday but stale; Riley changed it Wednesday).
3. How are money amounts stored? → integer cents, never floats (hard constraint).
4. What's the rounding policy for uneven splits and where does the leftover cent go? → largest-remainder;
   payer absorbs the residual cent (Riley's decision, Wednesday).
5. What is currently open and who owns it? → demo-data-seed (sam); auth-model question (unassigned).
6. Was the receipts feature decided? What was chosen? → yes: deferred to v2 (Saturday).
7. What does the settle-up algorithm guarantee? → greedy min-cash-flow, ≤ n-1 transfers; true optimal
   count NP-hard.
8. What SQLite mode does the app run and why? → WAL; concurrent readers during writes; still single-writer.
9. What CORS gotcha did the team hit? → wildcard origin breaks credentialed fetch; explicit origins with
   CORSMiddleware.
10. Where is the demo deployed? → chip-in-demo.fly.dev (fly.io).
11. What happened with the page-size disagreement? → Riley changed 50→20 Wed (mobile render lag); Alex's
    Thu assertion of 50 was stale, flagged as a conflict, resolved keep-existing in review.
12. Which threads were closed this week? → chipin-frontend, split-rounding, settle-up-algorithm,
    deploy-demo, receipt-uploads.

Scoring: 1 (correct) / 0.5 (partial) / 0 (wrong or fabricated) per question. Also record tokens/chars of
context each agent consumed. Q2 and Q11 are the discriminators — recency-vs-truth questions where raw
transcripts mislead.
