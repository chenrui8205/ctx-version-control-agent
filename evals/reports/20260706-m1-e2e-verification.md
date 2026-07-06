# M1 end-to-end verification — 2026-07-06

Run before first cloud deployment. All software gates green; deploy (user-provisioned VM) is
the only outstanding M1 item.

## Automated
- pytest: 48/48 · ruff clean · fake scenarios S1/S2/S3 PASS
- Fresh-DB first-boot (the prod path): empty database → alembic upgrade head → app boot →
  default-repo bootstrap → owner signup → compiled pages served. PASS

## Live evals (fresh runs, reports committed alongside)
- reconcile (25 pairs, Sonnet): PASS 25/25, all 7 gates, all unanimous
- golden scenarios --mode live: S1 / S2 / S3 PASS
- extraction (T1-T3 + N1-N2 notes): PASS 19/19 recall, T3 reuse 7/7, both notes gates
- model posture: Sonnet retained (Haiku 4.5 rejected 2026-07-05 — missed R01 conflict;
  report 20260705-221703)

## Friend's-first-day e2e (scripted, real platform, real classifier)
1. signup xiaoming@example.com with invite code → member, display name 小明 ✓
2. `ctxvcs login` in isolated HOME (piped credentials) → config written ✓
3. `ctxvcs push --stdin` with a stale decision claim ("demo project is a todo app") + one
   legit finding → collision on `chosen` ⇒ CONFLICT, master frozen, review URL printed,
   staging pending ✓ ; conflict carried NO machine-proposed winner (DF-3 fix live) ✓
4. admin resolve keep_existing (with note) → commit c0d44276 ✓
5. post-resolution: decision unchanged on master with original provenance ✓ ; the friend's
   clean finding landed in the same commit (held entries released) ✓
6. `ctxvcs blame chip-in-v2-demo-project chosen` tells the whole story:
   set by chenrui (human) · challenged by xiaoming with 'todo app' → keep_existing by chenrui ✓
7. `ctxvcs pull` bundle served ✓ (session start path)

## Verdict
M1 software: READY. Remaining for M1 exit: VM deployment + DNS (user), restore-from-backup
drill on the deployed instance, then the two-week friend-team dogfood per §11 acceptance.
