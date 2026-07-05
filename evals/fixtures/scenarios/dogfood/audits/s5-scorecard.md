# S5 scorecard (Sam: settle-up view + stale fragment)
- FRAGMENT TRAP: no resurrection-as-new, no false conflict, no dup proliferation => outcome acceptable.
  Mechanism dubious: finding SUBSUMED the closed question (conf .82) under stable id 5009cb69 =>
  ENTRY TYPE MUTATED open_question->finding on master. DF-4 (same root as DF-2: cross-type supersede).
  Cascade note: ideal target (Riley's decision) was already lost by DF-1b — classifier picked the only
  content holder left. Cascades are real.
- state_change settle-up-ui: new ✓ (reasonable new subject) ; next_step demo-seed-data: new ✓ and correctly
  discriminated from chipin-demo-deploy despite thematic overlap
- action accuracy 2/3 vs ideal-world GT (fragment should drop vs decision / keep vs closed question)
- extraction recall 3/3 ; origin tagging: agent for code-derived finding (correct per skill; skill rule gap
  for agent-executed human-directed changes logged)
- open set after S5: {receipt-photo-uploads, chipin-demo-deploy, demo-seed-data} (settle-up-algorithm still
  missing due to DF-2) ; master≡HEAD ✓
- UX: raw REST paths undocumented in skill; registry needs --describe for cheap reuse decisions; job_id
  response should hint the poll command; supersede rationale text = best part of preview (surface in UI)
