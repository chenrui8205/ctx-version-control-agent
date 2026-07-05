# S4 scorecard (Alex: stale assertion => contradiction)
- MISSED-CONFLICT GATE: PASS. Bare present-tense 50 vs master 20 => collision path, contradicts conf .85,
  conflicting field exact, MR 37a8a14a opened, master frozen, skill stopped without committing.
- Classifier rationale explicitly distinguished bare-present-tense from change language. Discrimination held:
  indices state_change = complementary keep (no false conflict), load-test finding + deploy step = new.
- ADMIN LOG: resolved 3b04b3f4 keep_existing (riley's deliberate 50->20 with rationale beats alex's Monday
  memory). Post-resolution: commit f20866b8, Facts=20 riley provenance, stale 50 discarded, 3 clean entries landed.
- DF-3 (product): proposed_resolution defaults to winner:incoming (spec §6 default) => would enshrine the
  stale value on a lazy one-click. Needs change-language/recency-aware proposal or no default at all.
- action accuracy 4/4 ; recall 4/4 ; subject reuse expenses-api + chipin-db ✓ ; field name reused ✓
- UX: conflict card lacks existing side's commit age; job result conflicts block omits conflict_id + bodies;
  subject duplicated between envelope and fields (CLI should inject).
